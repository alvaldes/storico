"""Tests for SQLAlchemyUserStoryRepository."""

from datetime import datetime
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from storico.domain.entities import Project, RepositoryError, UserStory
from storico.infrastructure.database.repositories import (
    SQLAlchemyProjectRepository,
    SQLAlchemyUserStoryRepository,
)
from tests._helpers import create_workspace


@pytest_asyncio.fixture
async def workspace_id(db_session: AsyncSession) -> UUID:
    """Seed a Workspace and return its id — Projects need a real FK."""
    ws = await create_workspace(db_session)
    return ws.id


async def _seed_project(db_session: AsyncSession, workspace_id: UUID, name: str) -> Project:
    """Save one project in the workspace and return it."""
    return await SQLAlchemyProjectRepository(db_session).save(
        Project(name=name, workspace_id=workspace_id)
    )


def _story(project_id: UUID, feature: str, **kwargs) -> UserStory:
    """Build a story with a distinct feature so assertions can name rows."""
    return UserStory(
        project_id=project_id,
        actor="user",
        feature=feature,
        benefit="value",
        raw_text=f"As a user, I want {feature} so that value",
        **kwargs,
    )


@pytest.mark.asyncio
async def test_save_and_find_by_id(db_session: AsyncSession, workspace_id: UUID) -> None:
    """Save a user story and retrieve it by id."""
    repo = SQLAlchemyUserStoryRepository(db_session)
    project = await _seed_project(db_session, workspace_id, "Save project")
    story = _story(project.id, "log in")

    saved = await repo.save(story)
    assert saved == story

    found = await repo.find_by_id(story.id)
    assert found is not None
    assert found.project_id == project.id
    assert found.actor == "user"
    assert found.feature == "log in"
    assert found.benefit == "value"
    assert found.raw_text.startswith("As a user")


@pytest.mark.asyncio
async def test_find_by_id_returns_none(db_session: AsyncSession) -> None:
    """find_by_id returns None for a non-existent user story."""
    repo = SQLAlchemyUserStoryRepository(db_session)
    result = await repo.find_by_id(uuid4())
    assert result is None


@pytest.mark.asyncio
async def test_list_page_by_project_returns_only_that_projects_stories(
    db_session: AsyncSession, workspace_id: UUID
) -> None:
    """list_page(project_id=...) returns only that project's stories, total scoped to it.

    The second project's stories must be excluded from both the page and the
    total: a total that counted the whole table would break paging arithmetic
    even when the page itself is filtered correctly.
    """
    repo = SQLAlchemyUserStoryRepository(db_session)
    mine = await _seed_project(db_session, workspace_id, "Mine")
    other = await _seed_project(db_session, workspace_id, "Other")

    for feature in ("mine-1", "mine-2"):
        await repo.save(_story(mine.id, feature))
    for feature in ("other-1", "other-2"):
        await repo.save(_story(other.id, feature))

    page, total = await repo.list_page(project_id=mine.id, limit=10, offset=0)

    assert total == 2
    assert {s.feature for s in page} == {"mine-1", "mine-2"}
    assert all(s.project_id == mine.id for s in page)


@pytest.mark.asyncio
async def test_list_page_by_project_empty(db_session: AsyncSession) -> None:
    """list_page for a project with no stories returns an empty page and total 0."""
    repo = SQLAlchemyUserStoryRepository(db_session)

    page, total = await repo.list_page(project_id=uuid4(), limit=10, offset=0)

    assert page == []
    assert total == 0


@pytest.mark.asyncio
async def test_list_page_mid_page_carries_the_full_total(
    db_session: AsyncSession, workspace_id: UUID
) -> None:
    """limit=2 over three stories: both mid pages report the full total of 3.

    The total comes from ``count(*) OVER ()`` on the rows' own statement, so
    every page — including the short last one — reports how many rows match,
    not how many the page holds.
    """
    repo = SQLAlchemyUserStoryRepository(db_session)
    project = await _seed_project(db_session, workspace_id, "Paged")
    for day, feature in ((1, "oldest"), (2, "middle"), (3, "newest")):
        await repo.save(_story(project.id, feature, created_at=datetime(2026, 1, day)))

    page1, total1 = await repo.list_page(project_id=project.id, limit=2, offset=0)
    page2, total2 = await repo.list_page(project_id=project.id, limit=2, offset=2)

    assert total1 == total2 == 3
    assert [s.feature for s in page1] == ["newest", "middle"]
    assert [s.feature for s in page2] == ["oldest"]


@pytest.mark.asyncio
async def test_list_page_past_the_end_returns_empty_page_and_real_total(
    db_session: AsyncSession, workspace_id: UUID
) -> None:
    """A page past the end returns ([], 3): the real total, not a page count.

    This is the fallback path in ``fetch_page`` — no row comes back to carry
    the window count, so the caller must still learn the real total.
    """
    repo = SQLAlchemyUserStoryRepository(db_session)
    project = await _seed_project(db_session, workspace_id, "Paged")
    for feature in ("s1", "s2", "s3"):
        await repo.save(_story(project.id, feature))

    page, total = await repo.list_page(project_id=project.id, limit=2, offset=4)

    assert page == []
    assert total == 3


@pytest.mark.asyncio
async def test_list_page_by_workspace_returns_only_that_workspaces_stories(
    db_session: AsyncSession,
) -> None:
    """list_page(workspace_id=...) returns only that workspace's stories."""
    repo = SQLAlchemyUserStoryRepository(db_session)
    alpha_ws = await create_workspace(db_session, name="Alpha", slug="alpha-list-page")
    beta_ws = await create_workspace(db_session, name="Beta", slug="beta-list-page")
    alpha_project = await _seed_project(db_session, alpha_ws.id, "Alpha project")
    beta_project = await _seed_project(db_session, beta_ws.id, "Beta project")
    await repo.save(_story(alpha_project.id, "alpha-feature"))
    await repo.save(_story(beta_project.id, "beta-feature"))

    page, total = await repo.list_page(workspace_id=alpha_ws.id, limit=10, offset=0)

    assert total == 1
    assert [s.feature for s in page] == ["alpha-feature"]


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

    repo = SQLAlchemyUserStoryRepository(db_session)

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
    repo = SQLAlchemyUserStoryRepository(db_session)

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
    repo = SQLAlchemyUserStoryRepository(db_session)

    with pytest.raises(ValueError):
        await repo.list_page(workspace_ids=[workspace_id], project_id=uuid4(), limit=10, offset=0)

    with pytest.raises(ValueError):
        await repo.list_page(workspace_id=workspace_id, project_id=uuid4(), limit=10, offset=0)

    with pytest.raises(ValueError):
        await repo.list_page(
            workspace_id=workspace_id,
            project_id=uuid4(),
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

    repo = SQLAlchemyUserStoryRepository(db_session)
    project = await _seed_project(db_session, workspace_id, "Ordered")
    await repo.save(_story(project.id, "only"))

    event.listen(test_engine.sync_engine, "before_cursor_execute", record)
    try:
        await repo.list_page(project_id=project.id, limit=10, offset=0)
    finally:
        event.remove(test_engine.sync_engine, "before_cursor_execute", record)

    page_queries = [s for s in statements if "FROM user_stories" in s]
    assert len(page_queries) == 1, page_queries

    order_by = page_queries[0].split("ORDER BY", 1)[-1]
    assert "user_stories.created_at DESC" in order_by, order_by
    assert "user_stories.id DESC" in order_by, order_by


@pytest.mark.asyncio
async def test_list_all(db_session: AsyncSession, workspace_id: UUID) -> None:
    """list returns all user stories."""
    repo = SQLAlchemyUserStoryRepository(db_session)
    project = await _seed_project(db_session, workspace_id, "Listed")
    await repo.save(_story(project.id, "f1"))
    await repo.save(_story(project.id, "f2"))

    stories = await repo.list()
    assert len(stories) == 2


@pytest.mark.asyncio
async def test_list_parts_by_project_returns_only_that_projects_parts(
    db_session: AsyncSession, workspace_id: UUID
) -> None:
    """list_parts_by_project returns every row of the project and none of another's.

    The strings come back exactly as stored: the caller's duplicate rule is an
    exact match, so a story whose actor differs only by case (``User`` vs
    ``user``) must survive as two distinct rows — normalising in the repository
    would hide a difference the rule treats as meaningful.
    """
    repo = SQLAlchemyUserStoryRepository(db_session)
    mine = await _seed_project(db_session, workspace_id, "Parts mine")
    other = await _seed_project(db_session, workspace_id, "Parts other")

    await repo.save(
        UserStory(
            project_id=mine.id,
            actor="User",
            feature="log in",
            benefit="value",
            raw_text="As a User, I want log in so that value",
        )
    )
    await repo.save(
        UserStory(
            project_id=mine.id,
            actor="user",
            feature="log in",
            benefit="value",
            raw_text="As a user, I want log in so that value",
        )
    )
    await repo.save(_story(other.id, "other-feature"))

    parts = await repo.list_parts_by_project(mine.id)

    assert len(parts) == 2
    assert {actor for actor, _, _, _ in parts} == {"User", "user"}
    assert all(feature == "log in" and benefit == "value" for _, feature, benefit, _ in parts)
    assert all(story_id is not None for *_, story_id in parts)
    assert all(feature != "other-feature" for _, feature, _, _ in parts)


@pytest.mark.asyncio
async def test_list_parts_by_project_empty_project(db_session: AsyncSession) -> None:
    """A project with no stories returns an empty list."""
    repo = SQLAlchemyUserStoryRepository(db_session)

    parts = await repo.list_parts_by_project(uuid4())

    assert parts == []


@pytest.mark.asyncio
async def test_list_parts_by_project_issues_one_statement(
    db_session: AsyncSession, test_engine: AsyncEngine, workspace_id: UUID
) -> None:
    """The whole project's duplicate candidates arrive in one statement.

    A CSV import compares many rows at once; one query per row would cost one
    round-trip per row before anything was written — the cost this method
    exists to remove. Statement capture follows ``ReadsOf`` in
    ``tests/test_api/test_unfiltered_list_queries.py``.
    """
    statements: list[str] = []

    def record(_conn, _cursor, statement, _params, _context, _executemany) -> None:
        statements.append(statement)

    repo = SQLAlchemyUserStoryRepository(db_session)
    project = await _seed_project(db_session, workspace_id, "Counted parts")
    await repo.save(_story(project.id, "f1"))
    await repo.save(_story(project.id, "f2"))

    event.listen(test_engine.sync_engine, "before_cursor_execute", record)
    try:
        await repo.list_parts_by_project(project.id)
    finally:
        event.remove(test_engine.sync_engine, "before_cursor_execute", record)

    assert len(statements) == 1, statements


@pytest.mark.asyncio
async def test_save_many_persists_all_rows(db_session: AsyncSession, workspace_id: UUID) -> None:
    """save_many returns the saved entities and every row is readable afterwards."""
    repo = SQLAlchemyUserStoryRepository(db_session)
    project = await _seed_project(db_session, workspace_id, "Bulk saved")
    stories = [
        _story(project.id, "import-1"),
        _story(project.id, "import-2"),
        _story(project.id, "import-3"),
    ]

    saved = await repo.save_many(stories)

    assert len(saved) == 3
    assert len({s.id for s in saved}) == 3
    assert all(s.id is not None for s in saved)
    assert all(s.created_at is not None for s in saved)
    for story in saved:
        found = await repo.find_by_id(story.id)
        assert found is not None
        assert found.feature == story.feature


@pytest.mark.asyncio
async def test_save_many_empty_returns_empty_without_statements(
    db_session: AsyncSession, test_engine: AsyncEngine
) -> None:
    """An empty batch returns [] without issuing any statement.

    No rows means no work, not a round-trip — the same rule ``list_page``
    follows for an empty ``workspace_ids``.
    """
    statements: list[str] = []

    def record(_conn, _cursor, statement, _params, _context, _executemany) -> None:
        statements.append(statement)

    repo = SQLAlchemyUserStoryRepository(db_session)

    event.listen(test_engine.sync_engine, "before_cursor_execute", record)
    try:
        saved = await repo.save_many([])
    finally:
        event.remove(test_engine.sync_engine, "before_cursor_execute", record)

    assert saved == []
    assert statements == [], statements


@pytest.mark.asyncio
async def test_save_many_is_atomic_on_duplicate_primary_key(
    db_session: AsyncSession, workspace_id: UUID
) -> None:
    """A failure mid-batch leaves the table empty — the batch commits as one.

    Two stories share an explicit id, so the commit violates the primary key.
    With per-row commits the first story would already be persisted; with one
    transaction the rollback undoes the batch and the table stays empty. The
    primary key is the lever because sqlite does not enforce foreign keys by
    default here, so it is the only constraint the failure can trip.
    """
    repo = SQLAlchemyUserStoryRepository(db_session)
    project = await _seed_project(db_session, workspace_id, "Atomic batch")
    first = _story(project.id, "import-first")
    second = _story(project.id, "import-second", id=first.id)

    with pytest.raises(RepositoryError):  # wraps sqlite's IntegrityError
        await repo.save_many([first, second])

    assert await repo.list() == []


@pytest.mark.asyncio
async def test_save_many_commits_once_for_three_rows(
    db_session: AsyncSession, test_engine: AsyncEngine, workspace_id: UUID
) -> None:
    """Three rows cost one statement, the same as one row.

    The count does not scale with the number of rows: the batch flush issues a
    single INSERT (SQLAlchemy batches the three rows into one statement via
    insertmanyvalues) and the single commit issues no counted statement. Three
    separate ``save`` calls would show three INSERTs plus their commits.
    Statement capture follows ``ReadsOf`` in
    ``tests/test_api/test_unfiltered_list_queries.py``.
    """
    statements: list[str] = []

    def record(_conn, _cursor, statement, _params, _context, _executemany) -> None:
        statements.append(statement)

    repo = SQLAlchemyUserStoryRepository(db_session)
    project = await _seed_project(db_session, workspace_id, "Counted batch")

    event.listen(test_engine.sync_engine, "before_cursor_execute", record)
    try:
        await repo.save_many([_story(project.id, "only-one")])
        one_row_count = len(statements)
        statements.clear()
        await repo.save_many(
            [
                _story(project.id, "bulk-1"),
                _story(project.id, "bulk-2"),
                _story(project.id, "bulk-3"),
            ]
        )
        three_row_count = len(statements)
    finally:
        event.remove(test_engine.sync_engine, "before_cursor_execute", record)

    assert one_row_count == 1, one_row_count
    assert three_row_count == one_row_count, (three_row_count, one_row_count)
