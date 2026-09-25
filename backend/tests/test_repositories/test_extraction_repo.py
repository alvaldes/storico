"""Tests for SQLAlchemyExtractionRepository."""

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from storico.domain.entities import EntityNotFound, Extraction, Project, UserStory
from storico.domain.entities.extraction import ExtractionStatus
from storico.domain.entities.user_story import UserStoryStatus
from storico.infrastructure.database.repositories import (
    SQLAlchemyExtractionRepository,
    SQLAlchemyProjectRepository,
    SQLAlchemyUserStoryRepository,
)
from tests._helpers import create_workspace


@pytest.fixture
def story_id() -> UUID:
    return uuid4()


@pytest_asyncio.fixture
async def workspace_id(db_session: AsyncSession) -> UUID:
    """Seed a Workspace and return its id — Projects need a real FK."""
    ws = await create_workspace(db_session)
    return ws.id


async def _seed_story(db_session: AsyncSession, workspace_id: UUID, name: str) -> UserStory:
    """Save one project and one story in the workspace; return the story.

    Extractions reach their workspace only through
    ``extraction → story → project``, so a workspace-scoped extraction test
    needs the whole chain, not just a story id.
    """
    project = await SQLAlchemyProjectRepository(db_session).save(
        Project(name=name, workspace_id=workspace_id)
    )
    return await SQLAlchemyUserStoryRepository(db_session).save(
        UserStory(
            project_id=project.id,
            actor="user",
            feature=f"{name} feature",
            benefit="value",
            raw_text=f"As a user, I want the {name} feature so that value",
        )
    )


def _extraction(story_id: UUID, model_used: str, **kwargs) -> Extraction:
    """Build an extraction with a distinct model name so assertions can name rows."""
    return Extraction(
        user_story_id=story_id, model_used=model_used, raw_response="1. summary: s", **kwargs
    )


@pytest.mark.asyncio
async def test_save_with_nullable_fields(db_session: AsyncSession, story_id: UUID) -> None:
    """Save an extraction with nullable confidence_score and prompt_config."""
    repo = SQLAlchemyExtractionRepository(db_session)
    extraction = Extraction(
        user_story_id=story_id,
        model_used="llama3.2",
        raw_response="1. summary: Task one\ndescription: Do something",
        prompt_config={"temperature": 0.1, "max_tokens": 2048},
        confidence_score=0.85,
    )

    saved = await repo.save(extraction)
    assert saved == extraction

    found = await repo.find_by_id(extraction.id)
    assert found is not None
    assert found.model_used == "llama3.2"
    assert found.prompt_config == {"temperature": 0.1, "max_tokens": 2048}
    assert found.confidence_score == 0.85
    assert found.raw_response.startswith("1. summary")


@pytest.mark.asyncio
async def test_save_with_null_fields(db_session: AsyncSession, story_id: UUID) -> None:
    """Save an extraction without optional fields (prompt_config, confidence_score)."""
    repo = SQLAlchemyExtractionRepository(db_session)
    extraction = Extraction(
        user_story_id=story_id,
        model_used="mistral",
        raw_response="1. summary: Task one\ndescription: Do something",
    )

    await repo.save(extraction)
    found = await repo.find_by_id(extraction.id)
    assert found is not None
    assert found.prompt_config is None
    assert found.confidence_score is None


@pytest.mark.asyncio
async def test_find_by_id_returns_none(db_session: AsyncSession) -> None:
    """find_by_id returns None for a non-existent extraction."""
    repo = SQLAlchemyExtractionRepository(db_session)
    result = await repo.find_by_id(uuid4())
    assert result is None


@pytest.mark.asyncio
async def test_list_page_by_story_excludes_another_storys_extractions(
    db_session: AsyncSession, workspace_id: UUID
) -> None:
    """list_page(user_story_id=...) returns only that story's extractions, total scoped to it.

    The second story's extractions must be excluded from both the page and the
    total: a total that counted the whole table would break paging arithmetic
    even when the page itself is filtered correctly.
    """
    repo = SQLAlchemyExtractionRepository(db_session)
    mine = await _seed_story(db_session, workspace_id, "Mine")
    other = await _seed_story(db_session, workspace_id, "Other")

    await repo.save(_extraction(mine.id, "mine-1"))
    await repo.save(_extraction(mine.id, "mine-2"))
    await repo.save(_extraction(other.id, "other-1"))

    page, total = await repo.list_page(user_story_id=mine.id, limit=10, offset=0)

    assert total == 2
    assert {e.model_used for e in page} == {"mine-1", "mine-2"}
    assert all(e.user_story_id == mine.id for e in page)


@pytest.mark.asyncio
async def test_list_page_by_story_empty(db_session: AsyncSession) -> None:
    """list_page for a story with no extractions returns an empty page and total 0."""
    repo = SQLAlchemyExtractionRepository(db_session)

    page, total = await repo.list_page(user_story_id=uuid4(), limit=10, offset=0)

    assert page == []
    assert total == 0


@pytest.mark.asyncio
async def test_list_page_mid_page_carries_the_full_total(
    db_session: AsyncSession, workspace_id: UUID
) -> None:
    """limit=2 over three extractions: both mid pages report the full total of 3.

    The total comes from ``count(*) OVER ()`` on the rows' own statement, so
    every page — including the short last one — reports how many rows match,
    not how many the page holds.
    """
    repo = SQLAlchemyExtractionRepository(db_session)
    story = await _seed_story(db_session, workspace_id, "Paged")
    for day, model in ((1, "oldest"), (2, "middle"), (3, "newest")):
        await repo.save(_extraction(story.id, model, created_at=datetime(2026, 1, day, tzinfo=UTC)))

    page1, total1 = await repo.list_page(user_story_id=story.id, limit=2, offset=0)
    page2, total2 = await repo.list_page(user_story_id=story.id, limit=2, offset=2)

    assert total1 == total2 == 3
    assert [e.model_used for e in page1] == ["newest", "middle"]
    assert [e.model_used for e in page2] == ["oldest"]


@pytest.mark.asyncio
async def test_list_page_past_the_end_returns_empty_page_and_real_total(
    db_session: AsyncSession, workspace_id: UUID
) -> None:
    """A page past the end returns ([], 3): the real total, not a page count.

    This is the fallback path in ``fetch_page`` — no row comes back to carry
    the window count, so the caller must still learn the real total.
    """
    repo = SQLAlchemyExtractionRepository(db_session)
    story = await _seed_story(db_session, workspace_id, "Paged")
    for model in ("s1", "s2", "s3"):
        await repo.save(_extraction(story.id, model))

    page, total = await repo.list_page(user_story_id=story.id, limit=2, offset=4)

    assert page == []
    assert total == 3


@pytest.mark.asyncio
async def test_list_page_by_workspace_returns_only_that_workspaces_extractions(
    db_session: AsyncSession,
) -> None:
    """list_page(workspace_id=...) returns only that workspace's extractions.

    Extractions have no workspace column: the scope walks
    ``extraction → story → project`` and filters on the project's workspace,
    the same two joins the unpaginated read used.
    """
    repo = SQLAlchemyExtractionRepository(db_session)
    alpha_ws = await create_workspace(db_session, name="Alpha", slug="alpha-extraction-list-page")
    beta_ws = await create_workspace(db_session, name="Beta", slug="beta-extraction-list-page")
    alpha_story = await _seed_story(db_session, alpha_ws.id, "Alpha project")
    beta_story = await _seed_story(db_session, beta_ws.id, "Beta project")
    await repo.save(_extraction(alpha_story.id, "alpha-extraction"))
    await repo.save(_extraction(beta_story.id, "beta-extraction"))

    page, total = await repo.list_page(workspace_id=alpha_ws.id, limit=10, offset=0)

    assert total == 1
    assert [e.model_used for e in page] == ["alpha-extraction"]


@pytest.mark.asyncio
async def test_list_page_with_empty_workspace_ids_skips_the_database(
    db_session: AsyncSession, test_engine: AsyncEngine
) -> None:
    """An empty ``workspace_ids`` returns ([], 0) without issuing any statement.

    No memberships means no rows, not ``IN ()``: against the dev pooler where
    a statement costs ~2s, an unasked statement is pure latency. Statements
    are counted on the real engine, following ``ReadsOf`` in
    ``tests/test_api/test_unfiltered_list_queries.py``.
    """
    statements: list[str] = []

    def record(_conn, _cursor, statement, _params, _context, _executemany) -> None:
        statements.append(statement)

    repo = SQLAlchemyExtractionRepository(db_session)

    event.listen(test_engine.sync_engine, "before_cursor_execute", record)
    try:
        page, total = await repo.list_page(workspace_ids=[], limit=10, offset=0)
    finally:
        event.remove(test_engine.sync_engine, "before_cursor_execute", record)

    assert page == []
    assert total == 0
    assert statements == [], statements


@pytest.mark.asyncio
async def test_list_page_requires_a_scope(db_session: AsyncSession) -> None:
    """Calling list_page with none of the three scope arguments raises ValueError."""
    repo = SQLAlchemyExtractionRepository(db_session)

    with pytest.raises(ValueError):
        await repo.list_page(limit=10, offset=0)


@pytest.mark.asyncio
async def test_list_page_refuses_two_scopes(db_session: AsyncSession, workspace_id: UUID) -> None:
    """Two scopes raise instead of silently resolving to one of them.

    An ``if``/``elif`` chain answers a two-scope call with whichever branch
    happens to come first in the chain. That is a wrong answer shaped like a
    right one, which is the failure mode this paging change removes — so more
    than one scope has to be loud.
    """
    repo = SQLAlchemyExtractionRepository(db_session)
    story = await _seed_story(db_session, workspace_id, "Scoped")

    with pytest.raises(ValueError):
        await repo.list_page(
            workspace_ids=[workspace_id], user_story_id=story.id, limit=10, offset=0
        )

    with pytest.raises(ValueError):
        await repo.list_page(workspace_id=workspace_id, user_story_id=story.id, limit=10, offset=0)

    with pytest.raises(ValueError):
        await repo.list_page(
            workspace_id=workspace_id,
            user_story_id=story.id,
            workspace_ids=[workspace_id],
            limit=10,
            offset=0,
        )


@pytest.mark.asyncio
async def test_list_page_pins_the_order_rule_in_sql(
    db_session: AsyncSession, test_engine: AsyncEngine, workspace_id: UUID
) -> None:
    """The ordering rule is part of the statement, not of one run's result.

    Result-order assertions can pass by accident on a different query plan.
    What paging actually depends on is a property of the SQL: without a total
    order a row can repeat on page 2 or vanish between pages. So the rule is
    asserted on the statement the database received.

    Statement capture follows ``ReadsOf`` in
    ``tests/test_api/test_unfiltered_list_queries.py``: a listener on the real
    engine, not a mock the repository would call once.
    """
    statements: list[str] = []

    def record(_conn, _cursor, statement, _params, _context, _executemany) -> None:
        statements.append(statement)

    repo = SQLAlchemyExtractionRepository(db_session)
    story = await _seed_story(db_session, workspace_id, "Ordered")
    await repo.save(_extraction(story.id, "only"))

    event.listen(test_engine.sync_engine, "before_cursor_execute", record)
    try:
        await repo.list_page(user_story_id=story.id, limit=10, offset=0)
    finally:
        event.remove(test_engine.sync_engine, "before_cursor_execute", record)

    page_queries = [s for s in statements if "FROM extractions" in s]
    assert len(page_queries) == 1, page_queries

    order_by = page_queries[0].split("ORDER BY", 1)[-1]
    assert "extractions.created_at DESC" in order_by, order_by
    assert "extractions.id DESC" in order_by, order_by


@pytest.mark.asyncio
async def test_list_all(db_session: AsyncSession, story_id: UUID) -> None:
    """list returns all extractions."""
    repo = SQLAlchemyExtractionRepository(db_session)
    e1 = Extraction(user_story_id=story_id, model_used="m1", raw_response="r1")
    e2 = Extraction(user_story_id=story_id, model_used="m2", raw_response="r2")
    await repo.save(e1)
    await repo.save(e2)

    extractions = await repo.list()
    assert len(extractions) == 2


@pytest.mark.asyncio
async def test_a_completed_extraction_round_trips_its_end_time(
    db_session: AsyncSession, story_id: UUID
) -> None:
    """``completed_at`` is stored and read back, which is the whole point of the column."""
    repo = SQLAlchemyExtractionRepository(db_session)
    finished = datetime(2026, 9, 19, 12, 30, tzinfo=UTC)
    extraction = Extraction(
        user_story_id=story_id,
        model_used="llama3.2",
        raw_response="r",
        status=ExtractionStatus.COMPLETED,
        user_story_status=UserStoryStatus.EXTRACTED,
        completed_at=finished,
    )

    await repo.save(extraction)

    found = await repo.find_by_id(extraction.id)
    assert found is not None
    # The test database is SQLite, which drops ``tzinfo`` on a ``DateTime(timezone=True)`` column,
    # so the read-back value is naive while the written one was aware — the same note as in
    # ``test_custom_provider_repo.py``. The instant is what the column carries; Postgres, which is
    # what production runs, keeps the offset.
    assert found.completed_at is not None
    assert found.completed_at.replace(tzinfo=None) == finished.replace(tzinfo=None)


@pytest.mark.asyncio
async def test_a_pending_extraction_has_no_end_time(
    db_session: AsyncSession, story_id: UUID
) -> None:
    """The invariant is "non-null exactly when terminal", not "not null"."""
    repo = SQLAlchemyExtractionRepository(db_session)
    extraction = Extraction(user_story_id=story_id, model_used="m", raw_response="r")

    await repo.save(extraction)

    found = await repo.find_by_id(extraction.id)
    assert found is not None
    assert found.status is ExtractionStatus.PENDING
    assert found.completed_at is None


@pytest.mark.asyncio
async def test_reading_a_terminal_row_invents_no_end_time(
    db_session: AsyncSession, story_id: UUID
) -> None:
    """A row that finished before the column existed keeps its null, forever.

    This is the decision the design turns on. Deriving ``completed_at`` inside the entity would
    have been tidier at the write sites and wrong here: the repository rebuilds an entity from
    every row it loads, so a derived value would hand this historical row a fresh timestamp on
    each read — a completion time that changes every time it is fetched, and the explicit
    decision not to backfill silently undone.
    """
    repo = SQLAlchemyExtractionRepository(db_session)
    historical = Extraction(
        user_story_id=story_id,
        model_used="m",
        raw_response="r",
        status=ExtractionStatus.COMPLETED,
        user_story_status=UserStoryStatus.EXTRACTED,
        completed_at=None,
    )
    await repo.save(historical)

    first = await repo.find_by_id(historical.id)
    second = await repo.find_by_id(historical.id)

    assert first is not None and second is not None
    assert first.completed_at is None
    assert second.completed_at is None


@pytest.mark.asyncio
async def test_delete_removes_a_row_and_reports_an_absent_one(
    db_session: AsyncSession, story_id: UUID
) -> None:
    """The delete path answers both questions: it removes, and it says when there is nothing."""
    repo = SQLAlchemyExtractionRepository(db_session)
    extraction = Extraction(user_story_id=story_id, model_used="m", raw_response="r")
    await repo.save(extraction)

    await repo.delete(extraction.id)
    assert await repo.find_by_id(extraction.id) is None

    with pytest.raises(EntityNotFound):
        await repo.delete(extraction.id)
