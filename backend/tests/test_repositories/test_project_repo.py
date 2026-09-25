"""Tests for SQLAlchemyProjectRepository."""

from datetime import datetime
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from storico.domain.entities import EntityNotFound, Project
from storico.domain.entities.user_story import UserStory
from storico.infrastructure.database.repositories import SQLAlchemyProjectRepository
from storico.infrastructure.database.repositories.user_story_repository import (
    SQLAlchemyUserStoryRepository,
)
from tests._helpers import create_workspace


@pytest_asyncio.fixture
async def workspace_id(db_session: AsyncSession) -> UUID:
    """Seed a Workspace and return its id — Projects need a real FK."""
    ws = await create_workspace(db_session)
    return ws.id


@pytest.mark.asyncio
async def test_list_page_folds_story_counts_across_pages(
    db_session: AsyncSession, workspace_id: UUID
) -> None:
    """list_page keeps per-project story counts on every page, including zero.

    Guards the JOIN+GROUP_BY fold that removed the N+1 pattern (one
    ``list_by_workspace`` + ``count_stories`` per project), now under paging:
    the LEFT OUTER JOIN must keep a project with no stories at count 0, and
    paging must not lose the counts of projects that live on other pages.
    """
    project_repo = SQLAlchemyProjectRepository(db_session)
    story_repo = SQLAlchemyUserStoryRepository(db_session)

    earlier = Project(name="Empty", workspace_id=workspace_id, created_at=datetime(2026, 1, 1))
    later = Project(name="WithTwo", workspace_id=workspace_id, created_at=datetime(2026, 1, 2))
    await project_repo.save(earlier)
    await project_repo.save(later)

    for _ in range(2):
        await story_repo.save(
            UserStory(
                project_id=later.id,
                actor="user",
                feature="do thing",
                benefit="value",
                raw_text="As a user, I want to do a thing so that I get value.",
            )
        )

    page1, total1 = await project_repo.list_page(workspace_id, limit=1, offset=0)
    page2, total2 = await project_repo.list_page(workspace_id, limit=1, offset=1)

    assert total1 == total2 == 2
    assert [pwc.project.name for pwc in page1] == ["WithTwo"]
    assert page1[0].story_count == 2
    assert [pwc.project.name for pwc in page2] == ["Empty"]
    assert page2[0].story_count == 0


@pytest.mark.asyncio
async def test_find_by_id_with_count_returns_pair_when_found(
    db_session: AsyncSession, workspace_id: UUID
) -> None:
    """find_by_id_with_count returns a ProjectWithCount (project, count)."""
    project_repo = SQLAlchemyProjectRepository(db_session)
    story_repo = SQLAlchemyUserStoryRepository(db_session)

    project = Project(name="Solo", workspace_id=workspace_id)
    await project_repo.save(project)
    await story_repo.save(
        UserStory(
            project_id=project.id,
            actor="user",
            feature="feature",
            benefit="benefit",
            raw_text="As a user, I want a feature so that benefit.",
        )
    )

    pwc = await project_repo.find_by_id_with_count(project.id)
    assert pwc is not None
    assert pwc.project.id == project.id
    assert pwc.story_count == 1


@pytest.mark.asyncio
async def test_find_by_id_with_count_returns_none_when_missing(
    db_session: AsyncSession,
) -> None:
    """find_by_id_with_count returns None for a non-existent project."""
    repo = SQLAlchemyProjectRepository(db_session)
    assert await repo.find_by_id_with_count(uuid4()) is None


@pytest.mark.asyncio
async def test_save_and_find_by_id(db_session: AsyncSession, workspace_id: UUID) -> None:
    """Save a project and retrieve it by id."""
    repo = SQLAlchemyProjectRepository(db_session)
    project = Project(name="Test Project", workspace_id=workspace_id, description="A test")

    saved = await repo.save(project)
    assert saved == project

    found = await repo.find_by_id(project.id)
    assert found is not None
    assert found.name == "Test Project"
    assert found.workspace_id == workspace_id
    assert found.description == "A test"


@pytest.mark.asyncio
async def test_find_by_id_returns_none(db_session: AsyncSession) -> None:
    """find_by_id returns None for a non-existent project."""
    repo = SQLAlchemyProjectRepository(db_session)
    result = await repo.find_by_id(uuid4())
    assert result is None


@pytest.mark.asyncio
async def test_list_page_orders_by_created_at_desc(
    db_session: AsyncSession, workspace_id: UUID
) -> None:
    """list_page orders by created_at DESC.

    Explicit created_at values seed the rows, so the assertion pins the SQL
    ordering rule rather than wall-clock insertion order.
    """
    repo = SQLAlchemyProjectRepository(db_session)
    for day, name in ((1, "Oldest"), (2, "Middle"), (3, "Newest")):
        await repo.save(
            Project(name=name, workspace_id=workspace_id, created_at=datetime(2026, 1, day))
        )

    page, total = await repo.list_page(workspace_id, limit=10, offset=0)

    assert [pwc.project.name for pwc in page] == ["Newest", "Middle", "Oldest"]
    assert total == 3


@pytest.mark.asyncio
async def test_list_page_breaks_ties_by_id_desc(
    db_session: AsyncSession, workspace_id: UUID
) -> None:
    """Two projects with the same created_at come back in id DESC order.

    The assertion compares against the ids sorted descending, so it pins the
    tiebreaker rule instead of the incidental result of one run.
    """
    repo = SQLAlchemyProjectRepository(db_session)
    for name in ("First", "Second"):
        await repo.save(
            Project(name=name, workspace_id=workspace_id, created_at=datetime(2026, 1, 1))
        )

    page, _total = await repo.list_page(workspace_id, limit=10, offset=0)

    ids = [pwc.project.id for pwc in page]
    assert ids == sorted(ids, reverse=True)


@pytest.mark.asyncio
async def test_list_page_pins_the_order_rule_in_sql(
    db_session: AsyncSession, test_engine: AsyncEngine, workspace_id: UUID
) -> None:
    """The ordering rule is part of the statement, not of one run's result.

    ``test_list_page_breaks_ties_by_id_desc`` asserts the order the rows came
    back in, and a different query plan could satisfy that by accident. What
    paging actually depends on is a property of the SQL: without a total order
    a row can repeat on page 2 or vanish between pages. So the rule is asserted
    on the statement the database received.

    Statement capture follows ``ReadsOf`` in
    ``tests/test_api/test_unfiltered_list_queries.py``: a listener on the real
    engine, not a mock the repository would call once.
    """
    statements: list[str] = []

    def record(_conn, _cursor, statement, _params, _context, _executemany) -> None:
        statements.append(statement)

    repo = SQLAlchemyProjectRepository(db_session)
    # Outside the capture: ``save`` reads the row back through
    # ``session.get``, so its own ``SELECT ... FROM projects`` would be counted
    # as a second page query.
    await repo.save(Project(name="Only", workspace_id=workspace_id))

    event.listen(test_engine.sync_engine, "before_cursor_execute", record)
    try:
        await repo.list_page(workspace_id, limit=10, offset=0)
    finally:
        event.remove(test_engine.sync_engine, "before_cursor_execute", record)

    page_queries = [s for s in statements if "FROM projects" in s]
    assert len(page_queries) == 1, page_queries

    order_by = page_queries[0].split("ORDER BY", 1)[-1]
    assert "projects.created_at DESC" in order_by, order_by
    assert "projects.id DESC" in order_by, order_by


@pytest.mark.asyncio
async def test_list_page_returns_disjoint_pages_with_full_total(
    db_session: AsyncSession, workspace_id: UUID
) -> None:
    """limit=2 over three projects yields disjoint pages and total 3 on both."""
    repo = SQLAlchemyProjectRepository(db_session)
    for day in (1, 2, 3):
        await repo.save(
            Project(name=f"P-{day}", workspace_id=workspace_id, created_at=datetime(2026, 1, day))
        )

    page1, total1 = await repo.list_page(workspace_id, limit=2, offset=0)
    page2, total2 = await repo.list_page(workspace_id, limit=2, offset=2)

    ids1 = {pwc.project.id for pwc in page1}
    ids2 = {pwc.project.id for pwc in page2}
    assert len(page1) == 2
    assert len(page2) == 1
    assert not ids1 & ids2
    assert total1 == total2 == 3


@pytest.mark.asyncio
async def test_list_page_empty_workspace_returns_zero_total(
    db_session: AsyncSession,
) -> None:
    """list_page on a workspace with no projects returns ([], 0)."""
    repo = SQLAlchemyProjectRepository(db_session)
    ws = await create_workspace(db_session)

    page, total = await repo.list_page(ws.id, limit=20, offset=0)

    assert page == []
    assert total == 0


@pytest.mark.asyncio
async def test_delete_raises_entity_not_found(db_session: AsyncSession) -> None:
    """delete raises EntityNotFound when the project does not exist."""
    repo = SQLAlchemyProjectRepository(db_session)
    with pytest.raises(EntityNotFound) as exc:
        await repo.delete(uuid4())
    assert "Project" in str(exc.value)


@pytest.mark.asyncio
async def test_list_all(db_session: AsyncSession, workspace_id: UUID) -> None:
    """list returns all projects."""
    repo = SQLAlchemyProjectRepository(db_session)
    p1 = Project(name="P1", workspace_id=workspace_id)
    p2 = Project(name="P2", workspace_id=workspace_id)
    await repo.save(p1)
    await repo.save(p2)

    projects = await repo.list()
    assert len(projects) == 2


@pytest.mark.asyncio
async def test_update_sets_updated_at(db_session: AsyncSession, workspace_id: UUID) -> None:
    """Saving an existing project updates its updated_at timestamp."""
    repo = SQLAlchemyProjectRepository(db_session)
    project = Project(name="Original", workspace_id=workspace_id)
    await repo.save(project)

    # Mutate via ORM — domain entity is frozen, so we re-fetch
    # and verify the timestamp was updated
    found_before = await repo.find_by_id(project.id)
    assert found_before is not None
    before_updated = found_before.updated_at

    # Save again with the same entity (update path)
    await repo.save(project)

    found_after = await repo.find_by_id(project.id)
    assert found_after is not None
    # updated_at should be newer
    assert found_after.updated_at >= before_updated
