"""Tests for SQLAlchemyExtractionRepository."""

import sqlite3
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from sqlalchemy import event
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from storico.domain.entities import Extraction, Project, UserStory
from storico.domain.entities.extraction import ExtractionStatus
from storico.domain.entities.user_story import UserStoryStatus
from storico.domain.ports import ExtractionRepository
from storico.infrastructure.database.repositories import (
    SQLAlchemyExtractionRepository,
    SQLAlchemyProjectRepository,
    SQLAlchemyUserStoryRepository,
)
from tests._helpers import create_workspace, seed_extraction


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


async def _seed_extraction(
    db_session: AsyncSession, story_id: UUID, model_used: str, **kwargs
) -> Extraction:
    """Seed one extraction through the birth path, with a distinct model name.

    Wraps the shared ``seed_extraction`` builder (task 1.16): revision ``0028`` made
    the birth path the only way a row exists, so the paging and round-trip seeds below
    allocate a version instead of ``save()``-ing a hand-built row.
    """
    return await seed_extraction(db_session, story_id, model_used=model_used, **kwargs)


@pytest.mark.asyncio
async def test_birth_round_trips_nullable_fields(db_session: AsyncSession, story_id: UUID) -> None:
    """An extraction born with nullable confidence_score and prompt_config reads them back.

    The seed goes through ``create_next_version``: ``0028`` left ``save()`` able only to
    update existing rows — its INSERT names ``version_number`` NULL and the column is
    ``NOT NULL`` — so the nullable round-trip rides the birth path. ``version_number``
    on the returned entity is the minted number, not the None a hand-built entity
    carries, which is why the old ``saved == extraction`` equality became a field read.
    """
    repo = SQLAlchemyExtractionRepository(db_session)
    created = await _seed_extraction(
        db_session,
        story_id,
        "llama3.2",
        raw_response="1. summary: Task one\ndescription: Do something",
        prompt_config={"temperature": 0.1, "max_tokens": 2048},
        confidence_score=0.85,
    )

    found = await repo.find_by_id(created.id)
    assert found is not None
    assert found.model_used == "llama3.2"
    assert found.prompt_config == {"temperature": 0.1, "max_tokens": 2048}
    assert found.confidence_score == 0.85
    assert found.raw_response.startswith("1. summary")


@pytest.mark.asyncio
async def test_birth_without_optional_fields_reads_them_as_none(
    db_session: AsyncSession, story_id: UUID
) -> None:
    """An extraction born without optional fields (prompt_config, confidence_score) reads them as None."""
    repo = SQLAlchemyExtractionRepository(db_session)
    created = await _seed_extraction(
        db_session,
        story_id,
        "mistral",
        raw_response="1. summary: Task one\ndescription: Do something",
    )

    found = await repo.find_by_id(created.id)
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

    await _seed_extraction(db_session, mine.id, "mine-1")
    await _seed_extraction(db_session, mine.id, "mine-2")
    await _seed_extraction(db_session, other.id, "other-1")

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
        await _seed_extraction(
            db_session, story.id, model, created_at=datetime(2026, 1, day, tzinfo=UTC)
        )

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
        await _seed_extraction(db_session, story.id, model)

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
    await _seed_extraction(db_session, alpha_story.id, "alpha-extraction")
    await _seed_extraction(db_session, beta_story.id, "beta-extraction")

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
    await _seed_extraction(db_session, story.id, "only")

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
    await _seed_extraction(db_session, story_id, "m1")
    await _seed_extraction(db_session, story_id, "m2")

    extractions = await repo.list()
    assert len(extractions) == 2


@pytest.mark.asyncio
async def test_a_completed_extraction_round_trips_its_end_time(
    db_session: AsyncSession, story_id: UUID
) -> None:
    """``completed_at`` is stored and read back, which is the whole point of the column."""
    repo = SQLAlchemyExtractionRepository(db_session)
    finished = datetime(2026, 9, 19, 12, 30, tzinfo=UTC)
    created = await _seed_extraction(
        db_session,
        story_id,
        "llama3.2",
        raw_response="r",
        status=ExtractionStatus.COMPLETED,
        user_story_status=UserStoryStatus.EXTRACTED,
        completed_at=finished,
    )

    found = await repo.find_by_id(created.id)
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
    created = await _seed_extraction(db_session, story_id, "m")

    found = await repo.find_by_id(created.id)
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
    historical = await _seed_extraction(
        db_session,
        story_id,
        "m",
        status=ExtractionStatus.COMPLETED,
        user_story_status=UserStoryStatus.EXTRACTED,
        completed_at=None,
    )

    first = await repo.find_by_id(historical.id)
    second = await repo.find_by_id(historical.id)

    assert first is not None and second is not None
    assert first.completed_at is None
    assert second.completed_at is None


def test_the_port_exposes_no_delete_and_no_whole_row_writer() -> None:
    """The port has no ``delete`` and no whole-row writer: every write is a targeted one.

    Task 1.20 removed the former ``delete`` test together with the method: the story
    cascade is the only deletion path, and nothing in ``backend/src/storico`` calls
    ``extraction_repo.delete``. Task 3.7 removed ``save`` the same way: the port's
    writes are the birth (``create_next_version``) and the targeted marks, so no
    method writes a full row and none can silently null a snapshot column it does
    not own. The exact method list is pinned, so a future re-add fails visibly
    instead of silently widening the surface. Task 3.5 added ``list_versions``: the
    version selector's read, sanctioned by the change's design (one unpaginated
    story-scoped read), not a silent widening.
    """

    abstract_methods = {
        name
        for name, member in vars(ExtractionRepository).items()
        if getattr(member, "__isabstractmethod__", False)
    }
    assert abstract_methods == {
        "create_next_version",
        "record_rendered_prompt",
        "record_usage",
        "mark_completed",
        "mark_failed",
        "find_by_id",
        "find_current_version",
        "list_page",
        "list_versions",
        "list",
        "version_summaries",
    }
    assert not hasattr(ExtractionRepository, "delete")
    assert not hasattr(ExtractionRepository, "save")


# --- Versioning (task 1.1): allocation, derivation, conflict discrimination ---


def _versioned(story_id: UUID, model_used: str, **kwargs) -> Extraction:
    """Build an extraction the way a birth path does: with its run snapshot set.

    ``provider`` and ``temperature`` are required on the entity from ``0028`` on — a row
    cannot be born with a provider nobody configured, and ``NOT NULL`` cannot tell an
    empty string apart from a real value.
    """
    return Extraction(
        user_story_id=story_id,
        model_used=model_used,
        raw_response="",
        provider="ollama",
        temperature=0.1,
        **kwargs,
    )


@pytest.mark.asyncio
async def test_three_runs_on_one_story_are_numbered_1_2_3(
    db_session: AsyncSession, story_id: UUID
) -> None:
    """create_next_version mints the number inside the row's own INSERT: 1, 2, 3."""
    repo = SQLAlchemyExtractionRepository(db_session)

    first = await repo.create_next_version(_versioned(story_id, "m1"))
    second = await repo.create_next_version(_versioned(story_id, "m2"))
    third = await repo.create_next_version(_versioned(story_id, "m3"))

    assert [e.version_number for e in (first, second, third)] == [1, 2, 3]


@pytest.mark.asyncio
async def test_a_burned_version_number_is_never_reused(
    db_session: AsyncSession, story_id: UUID
) -> None:
    """After three consumed numbers the next is 4 — a terminal run never frees its number."""
    repo = SQLAlchemyExtractionRepository(db_session)
    for model in ("m1", "m2", "m3"):
        created = await repo.create_next_version(_versioned(story_id, model))
        await repo.mark_completed(
            created.id, raw_response="r", confidence_score=0.9, completed_at=datetime.now(UTC)
        )

    fourth = await repo.create_next_version(_versioned(story_id, "m4"))

    assert fourth.version_number == 4


@pytest.mark.asyncio
async def test_a_pending_run_leaves_the_previous_current_version_current(
    db_session: AsyncSession, story_id: UUID
) -> None:
    """A pending v3 on top of a completed v2 leaves find_current_version at v2.

    "Current" is derived — the highest completed version — never stored, so a run that
    has not finished cannot steal the title from the version that did.
    """
    repo = SQLAlchemyExtractionRepository(db_session)
    v1 = await repo.create_next_version(_versioned(story_id, "m1"))
    await repo.mark_completed(
        v1.id, raw_response="r", confidence_score=0.9, completed_at=datetime.now(UTC)
    )
    v2 = await repo.create_next_version(_versioned(story_id, "m2"))
    await repo.mark_completed(
        v2.id, raw_response="r", confidence_score=0.9, completed_at=datetime.now(UTC)
    )
    await repo.create_next_version(_versioned(story_id, "m3"))  # v3, still pending

    current = await repo.find_current_version(story_id)

    assert current is not None
    assert current.version_number == 2


@pytest.mark.asyncio
async def test_a_failed_top_version_is_never_current(
    db_session: AsyncSession, story_id: UUID
) -> None:
    """Completed v1 + failed v2: the current version is still v1."""
    repo = SQLAlchemyExtractionRepository(db_session)
    v1 = await repo.create_next_version(_versioned(story_id, "m1"))
    await repo.mark_completed(
        v1.id, raw_response="r", confidence_score=0.9, completed_at=datetime.now(UTC)
    )
    v2 = await repo.create_next_version(_versioned(story_id, "m2"))
    await repo.mark_failed(v2.id, error_info="LLM call failed", completed_at=datetime.now(UTC))

    current = await repo.find_current_version(story_id)

    assert current is not None
    assert current.version_number == 1


@pytest.mark.asyncio
async def test_a_failed_row_keeps_its_version_number(
    db_session: AsyncSession, story_id: UUID
) -> None:
    """Every run that reaches row creation consumes a number — including a failed one."""
    repo = SQLAlchemyExtractionRepository(db_session)
    created = await repo.create_next_version(_versioned(story_id, "m1"))

    await repo.mark_failed(created.id, error_info="LLM call failed", completed_at=datetime.now(UTC))

    found = await repo.find_by_id(created.id)
    assert found is not None
    assert found.status is ExtractionStatus.FAILED
    assert found.version_number == 1


def test_is_version_conflict_knows_both_driver_shapes_and_refuses_others() -> None:
    """The retry must retry exactly the version-conflict violation and nothing else.

    Both arms are pinned because the retry may not depend on an attribute a driver
    version may or may not expose: the asyncpg shape carries ``constraint_name`` on the
    driver error (reachable as ``exc.orig``), the sqlite3 shape reports the violated
    table/column pair in the message. A ``NOT NULL`` violation is not a collision —
    retrying it would burn three attempts and then report a conflict that never happened.
    """
    from storico.infrastructure.database.repositories import (
        extraction_repository as extraction_repo_module,
    )

    class _AsyncpgShapedError(Exception):
        """The fields asyncpg exposes on a unique-violation error."""

        def __init__(self) -> None:
            super().__init__("duplicate key value violates unique constraint")
            self.constraint_name = "uq_extractions_story_version"

    asyncpg_shaped = IntegrityError("INSERT INTO extractions …", None, _AsyncpgShapedError())
    sqlite_shaped = IntegrityError(
        "INSERT INTO extractions …",
        None,
        sqlite3.IntegrityError(
            "UNIQUE constraint failed: extractions.user_story_id, extractions.version_number"
        ),
    )
    not_null = IntegrityError(
        "INSERT INTO extractions …",
        None,
        sqlite3.IntegrityError("NOT NULL constraint failed: extractions.provider"),
    )

    is_version_conflict = extraction_repo_module._is_version_conflict
    assert is_version_conflict(asyncpg_shaped) is True
    assert is_version_conflict(sqlite_shaped) is True
    assert is_version_conflict(not_null) is False


@pytest.mark.asyncio
async def test_an_allocation_that_never_wins_fails_loudly_after_three_attempts(
    db_session: AsyncSession, story_id: UUID, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A conflict on every attempt stops at the bound of 3 and raises a distinct error.

    The retry lives in the adapter, so the port never learns the word "retry". The bound
    and the distinct exception type are what slice (b) needs to map the failure to an
    HTTP status instead of leaving it silent.
    """
    from storico.domain.entities.exceptions import VersionAllocationConflictError

    attempts = 0

    async def always_conflict(*args: object, **kwargs: object) -> None:
        nonlocal attempts
        attempts += 1
        raise IntegrityError(
            "INSERT INTO extractions …",
            None,
            sqlite3.IntegrityError(
                "UNIQUE constraint failed: extractions.user_story_id, extractions.version_number"
            ),
        )

    monkeypatch.setattr(db_session, "execute", always_conflict)
    repo = SQLAlchemyExtractionRepository(db_session)

    with pytest.raises(VersionAllocationConflictError):
        await repo.create_next_version(_versioned(story_id, "m1"))

    assert attempts == 3


# --- Version listing (task 3.2): the selector's read and its agreement pin ---


@pytest.mark.asyncio
async def test_list_versions_returns_every_version_newest_first_with_no_page_window(
    db_session: AsyncSession, test_engine: AsyncEngine, workspace_id: UUID
) -> None:
    """list_versions returns every version of the story, ordered version_number DESC.

    The version selector must show the story's whole history — including a pending
    and a failed run — because a user has to be able to see that run 3 failed and go
    back to reading run 2. The read is therefore deliberately unbounded: the version
    list is the pagination *input*, not a paginated resource, and the paginator's
    window would truncate a long history silently. Both the ordering and the absence
    of a LIMIT are asserted on the statement the database received, following the
    statement-capture style of ``test_list_page_pins_the_order_rule_in_sql`` —
    result-order assertions alone can pass by accident on a different query plan.
    """
    statements: list[str] = []

    def record(_conn, _cursor, statement, _params, _context, _executemany) -> None:
        statements.append(statement)

    repo = SQLAlchemyExtractionRepository(db_session)
    story = await _seed_story(db_session, workspace_id, "Versioned")
    other = await _seed_story(db_session, workspace_id, "Other story")

    v1 = await repo.create_next_version(_versioned(story.id, "v1-completed"))
    await repo.mark_completed(
        v1.id, raw_response="r", confidence_score=0.9, completed_at=datetime.now(UTC)
    )
    v2 = await repo.create_next_version(_versioned(story.id, "v2-completed"))
    await repo.mark_completed(
        v2.id, raw_response="r", confidence_score=0.9, completed_at=datetime.now(UTC)
    )
    v3 = await repo.create_next_version(_versioned(story.id, "v3-failed"))
    await repo.mark_failed(v3.id, error_info="LLM call failed", completed_at=datetime.now(UTC))
    await repo.create_next_version(_versioned(story.id, "v4-pending"))  # still pending
    other_run = await repo.create_next_version(_versioned(other.id, "other-story-run"))
    await repo.mark_completed(
        other_run.id, raw_response="r", confidence_score=0.9, completed_at=datetime.now(UTC)
    )

    event.listen(test_engine.sync_engine, "before_cursor_execute", record)
    try:
        versions = await repo.list_versions(story.id)
    finally:
        event.remove(test_engine.sync_engine, "before_cursor_execute", record)

    # Every version, newest first, with no window: four versions seeded, four back.
    assert [e.version_number for e in versions] == [4, 3, 2, 1]
    assert [e.model_used for e in versions] == [
        "v4-pending",
        "v3-failed",
        "v2-completed",
        "v1-completed",
    ]
    statuses = {e.model_used: e.status for e in versions}
    assert statuses["v3-failed"] is ExtractionStatus.FAILED
    assert statuses["v4-pending"] is ExtractionStatus.PENDING
    # A second story's versions never leak in.
    assert "other-story-run" not in {e.model_used for e in versions}
    assert all(e.user_story_id == story.id for e in versions)

    # No page window and the ordering rule in SQL, not in one run's result.
    version_queries = [s for s in statements if "FROM extractions" in s]
    assert len(version_queries) == 1, version_queries
    query = version_queries[0]
    assert "LIMIT" not in query, query
    order_by = query.split("ORDER BY", 1)[-1]
    assert "extractions.version_number DESC" in order_by, order_by


@pytest.mark.asyncio
async def test_find_current_version_agrees_with_list_versions_first_completed(
    db_session: AsyncSession, story_id: UUID
) -> None:
    """The two derivations of "current" agree for a three-version story.

    Currency is derived (status ``completed`` + highest ``version_number``), and it is
    encoded twice: the ``LIMIT 1`` predicate in ``find_current_version`` and the first
    ``completed`` entry of ``list_versions``. This pin is what keeps the board — which
    asks ``find_current_version`` on every task write via the frozen check — and the
    version selector — which derives ``is_current`` from the ordered list — from
    disagreeing about which version is live. It is also the guard on how they are
    *not* unified: ``find_current_version`` must stay a ``LIMIT 1`` statement, never
    this list filtered in Python, because it sits on the hot path of every task write.
    """
    repo = SQLAlchemyExtractionRepository(db_session)
    v1 = await repo.create_next_version(_versioned(story_id, "m1"))
    await repo.mark_completed(
        v1.id, raw_response="r", confidence_score=0.9, completed_at=datetime.now(UTC)
    )
    v2 = await repo.create_next_version(_versioned(story_id, "m2"))
    await repo.mark_failed(v2.id, error_info="LLM call failed", completed_at=datetime.now(UTC))
    v3 = await repo.create_next_version(_versioned(story_id, "m3"))
    await repo.mark_completed(
        v3.id, raw_response="r", confidence_score=0.9, completed_at=datetime.now(UTC)
    )

    current = await repo.find_current_version(story_id)
    versions = await repo.list_versions(story_id)

    first_completed = next(e for e in versions if e.status is ExtractionStatus.COMPLETED)
    assert current is not None
    assert current.id == first_completed.id
    assert current.version_number == first_completed.version_number == 3


# --- Story version summary (versioning-visibility WU1): the story-card batch read ---


@pytest.mark.asyncio
async def test_version_summaries_reports_count_current_and_latest_for_the_batch(
    db_session: AsyncSession, workspace_id: UUID
) -> None:
    """v1 completed + v2 failed + v3 pending: count 3, current v1, latest v3 pending.

    ``current_number`` keeps the ``find_current_version`` derivation — the highest
    *completed* number — while ``latest_number``/``latest_status`` name the newest
    run of any status, so a story whose only run failed can render ``v1 · failed``
    instead of lying with "current". A story with no versions is absent from the
    dict, not a zero-count entry; a second story's rows never leak into another
    story's summary.
    """
    repo = SQLAlchemyExtractionRepository(db_session)
    story = await _seed_story(db_session, workspace_id, "Summarised")
    other = await _seed_story(db_session, workspace_id, "Other summarised")
    empty = await _seed_story(db_session, workspace_id, "No versions")

    v1 = await repo.create_next_version(_versioned(story.id, "v1-completed"))
    await repo.mark_completed(
        v1.id, raw_response="r", confidence_score=0.9, completed_at=datetime.now(UTC)
    )
    v2 = await repo.create_next_version(_versioned(story.id, "v2-failed"))
    await repo.mark_failed(v2.id, error_info="LLM call failed", completed_at=datetime.now(UTC))
    await repo.create_next_version(_versioned(story.id, "v3-pending"))  # still pending

    other_run = await repo.create_next_version(_versioned(other.id, "only-completed"))
    await repo.mark_completed(
        other_run.id, raw_response="r", confidence_score=0.9, completed_at=datetime.now(UTC)
    )

    summaries = await repo.version_summaries([story.id, other.id, empty.id])

    assert set(summaries) == {story.id, other.id}
    first = summaries[story.id]
    assert first.count == 3
    assert first.current_number == 1
    assert first.latest_number == 3
    assert first.latest_status is ExtractionStatus.PENDING
    second = summaries[other.id]
    assert second.count == 1
    assert second.current_number == 1
    assert second.latest_number == 1
    assert second.latest_status is ExtractionStatus.COMPLETED


@pytest.mark.asyncio
async def test_version_summaries_for_a_failed_only_story_names_no_current(
    db_session: AsyncSession, workspace_id: UUID
) -> None:
    """A story whose only run failed: ``current_number`` is None, latest is the failure.

    The badge contract (decision D1) forbids lying with "current" — with no
    completed run there is none, and the newest run is the failed one.
    """
    repo = SQLAlchemyExtractionRepository(db_session)
    story = await _seed_story(db_session, workspace_id, "Failed only")
    run = await repo.create_next_version(_versioned(story.id, "v1-failed"))
    await repo.mark_failed(run.id, error_info="LLM call failed", completed_at=datetime.now(UTC))

    summaries = await repo.version_summaries([story.id])

    summary = summaries[story.id]
    assert summary.count == 1
    assert summary.current_number is None
    assert summary.latest_number == 1
    assert summary.latest_status is ExtractionStatus.FAILED


@pytest.mark.asyncio
async def test_version_summaries_with_empty_input_answers_empty_without_a_statement(
    db_session: AsyncSession, test_engine: AsyncEngine
) -> None:
    """An empty ``story_ids`` returns ``{}`` without issuing any statement.

    An empty page of stories means no rows, not ``IN ()``: against the dev
    pooler where a statement costs ~2s, an unasked statement is pure latency.
    Statement capture follows ``test_list_page_with_empty_workspace_ids``.
    """
    statements: list[str] = []

    def record(_conn, _cursor, statement, _params, _context, _executemany) -> None:
        statements.append(statement)

    repo = SQLAlchemyExtractionRepository(db_session)

    event.listen(test_engine.sync_engine, "before_cursor_execute", record)
    try:
        summaries = await repo.version_summaries([])
    finally:
        event.remove(test_engine.sync_engine, "before_cursor_execute", record)

    assert summaries == {}
    assert statements == [], statements


@pytest.mark.asyncio
async def test_version_summaries_issues_exactly_one_statement_for_the_batch(
    db_session: AsyncSession, test_engine: AsyncEngine, workspace_id: UUID
) -> None:
    """Two stories in one call cost one statement, not one per story.

    The projection is a read model for a list page (decision D2 of feature
    ``versioning-visibility``): its whole point is that 100 cards cost one
    batched read instead of 100. Statement capture follows
    ``test_list_page_with_empty_workspace_ids``.
    """
    statements: list[str] = []

    def record(_conn, _cursor, statement, _params, _context, _executemany) -> None:
        statements.append(statement)

    repo = SQLAlchemyExtractionRepository(db_session)
    first = await _seed_story(db_session, workspace_id, "First")
    second = await _seed_story(db_session, workspace_id, "Second")
    for story in (first, second):
        run = await repo.create_next_version(_versioned(story.id, "completed-run"))
        await repo.mark_completed(
            run.id, raw_response="r", confidence_score=0.9, completed_at=datetime.now(UTC)
        )

    event.listen(test_engine.sync_engine, "before_cursor_execute", record)
    try:
        await repo.version_summaries([first.id, second.id])
    finally:
        event.remove(test_engine.sync_engine, "before_cursor_execute", record)

    summary_queries = [s for s in statements if "FROM extractions" in s]
    assert len(summary_queries) == 1, statements
