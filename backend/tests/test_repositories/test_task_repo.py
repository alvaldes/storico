"""Tests for SQLAlchemyTaskRepository."""

import inspect
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from storico.domain.entities import Project, Task, UserStory
from storico.domain.entities.extraction import ExtractionStatus
from storico.domain.entities.task import TaskStatus
from storico.domain.entities.task_invalidation import TaskInvalidation
from storico.domain.ports import TaskRepository
from storico.infrastructure.database.repositories import (
    SQLAlchemyProjectRepository,
    SQLAlchemyTaskInvalidationRepository,
    SQLAlchemyTaskRepository,
    SQLAlchemyUserStoryRepository,
)
from tests._helpers import create_workspace, seed_extraction, seed_task


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

    Tasks reach their workspace only through ``task → story → project``, so a
    task test needs the whole chain, not just a story id.
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


async def _seed_task(db_session: AsyncSession, story_id: UUID, title: str, **kwargs) -> Task:
    """Seed one task through the shared builder, with a distinct title.

    ``tasks.extraction_id`` is ``NOT NULL`` from ``0028`` on, so a task seed needs an
    extraction to belong to; ``seed_task`` allocates one through the birth path.
    """
    return await seed_task(db_session, story_id, title, **kwargs)


@pytest.mark.asyncio
async def test_save_with_json_labels_and_deps(db_session: AsyncSession, story_id: UUID) -> None:
    """Save a task with labels and dependencies, then verify they round-trip."""
    repo = SQLAlchemyTaskRepository(db_session)
    extraction = await seed_extraction(db_session, story_id)
    task = Task(
        user_story_id=story_id,
        extraction_id=extraction.id,
        title="Implement login",
        description="Build the login form and validation",
        labels=["frontend", "auth"],
        dependencies=["US-001"],
    )

    saved = await repo.save(task)
    assert saved == task

    found = await repo.find_by_id(task.id)
    assert found is not None
    assert found.title == "Implement login"
    assert found.labels == ["frontend", "auth"]
    assert found.dependencies == ["US-001"]
    assert found.status == "backlog"
    assert found.priority == "medium"


@pytest.mark.asyncio
async def test_find_by_id_returns_none(db_session: AsyncSession) -> None:
    """find_by_id returns None for a non-existent task."""
    repo = SQLAlchemyTaskRepository(db_session)
    result = await repo.find_by_id(uuid4())
    assert result is None


@pytest.mark.asyncio
async def test_list_by_story(db_session: AsyncSession, story_id: UUID) -> None:
    """list_by_story returns only tasks for the given user story."""
    repo = SQLAlchemyTaskRepository(db_session)
    other_id = uuid4()

    await _seed_task(db_session, story_id, "Task 1")
    await _seed_task(db_session, story_id, "Task 2")
    await _seed_task(db_session, other_id, "Other task")

    tasks = await repo.list_by_story(story_id)
    assert len(tasks) == 2
    titles = {t.title for t in tasks}
    assert titles == {"Task 1", "Task 2"}


@pytest.mark.asyncio
async def test_list_by_story_empty(db_session: AsyncSession) -> None:
    """list_by_story returns empty list when no tasks match."""
    repo = SQLAlchemyTaskRepository(db_session)
    result = await repo.list_by_story(uuid4())
    assert result == []


@pytest.mark.asyncio
async def test_update_sets_updated_at(db_session: AsyncSession, story_id: UUID) -> None:
    """Saving an existing task updates its updated_at timestamp."""
    repo = SQLAlchemyTaskRepository(db_session)
    extraction = await seed_extraction(db_session, story_id)
    task = Task(user_story_id=story_id, extraction_id=extraction.id, title="Original")
    await repo.save(task)

    found_before = await repo.find_by_id(task.id)
    assert found_before is not None
    before_updated = found_before.updated_at

    # Save again (update path)
    await repo.save(task)

    found_after = await repo.find_by_id(task.id)
    assert found_after is not None
    assert found_after.updated_at >= before_updated


@pytest.mark.asyncio
async def test_list_page_by_story_excludes_another_storys_tasks(
    db_session: AsyncSession, workspace_id: UUID
) -> None:
    """list_page(user_story_id=...) returns only that story's tasks, total scoped to it.

    The second story's tasks must be excluded from both the page and the
    total: a total that counted the whole table would break paging arithmetic
    even when the page itself is filtered correctly.
    """
    repo = SQLAlchemyTaskRepository(db_session)
    mine = await _seed_story(db_session, workspace_id, "Mine")
    other = await _seed_story(db_session, workspace_id, "Other")

    # Reads answer the current version only (D-a-5 item 2), so each story's
    # tasks hang off one completed version to be visible at all.
    mine_v = await seed_extraction(db_session, mine.id, status=ExtractionStatus.COMPLETED)
    other_v = await seed_extraction(db_session, other.id, status=ExtractionStatus.COMPLETED)
    await _seed_task(db_session, mine.id, "mine-1", extraction=mine_v)
    await _seed_task(db_session, mine.id, "mine-2", extraction=mine_v)
    await _seed_task(db_session, other.id, "other-1", extraction=other_v)

    page, total = await repo.list_page(user_story_id=mine.id, limit=10, offset=0)

    assert total == 2
    assert {t.title for t in page} == {"mine-1", "mine-2"}
    assert all(t.user_story_id == mine.id for t in page)


@pytest.mark.asyncio
async def test_list_page_by_story_empty(db_session: AsyncSession) -> None:
    """list_page for a story with no tasks returns an empty page and total 0."""
    repo = SQLAlchemyTaskRepository(db_session)

    page, total = await repo.list_page(user_story_id=uuid4(), limit=10, offset=0)

    assert page == []
    assert total == 0


@pytest.mark.asyncio
async def test_list_page_mid_page_carries_the_full_total(
    db_session: AsyncSession, workspace_id: UUID
) -> None:
    """limit=2 over three tasks: both mid pages report the full total of 3.

    The total comes from ``count(*) OVER ()`` on the rows' own statement, so
    every page — including the short last one — reports how many rows match,
    not how many the page holds.
    """
    repo = SQLAlchemyTaskRepository(db_session)
    story = await _seed_story(db_session, workspace_id, "Paged")
    # One completed version carries all three tasks: reads answer the current
    # version only (D-a-5 item 2), and three separate versions would leave only
    # the highest one visible.
    version = await seed_extraction(db_session, story.id, status=ExtractionStatus.COMPLETED)
    for day, title in ((1, "oldest"), (2, "middle"), (3, "newest")):
        await _seed_task(
            db_session, story.id, title, extraction=version, created_at=datetime(2026, 1, day)
        )

    page1, total1 = await repo.list_page(user_story_id=story.id, limit=2, offset=0)
    page2, total2 = await repo.list_page(user_story_id=story.id, limit=2, offset=2)

    assert total1 == total2 == 3
    assert [t.title for t in page1] == ["newest", "middle"]
    assert [t.title for t in page2] == ["oldest"]


@pytest.mark.asyncio
async def test_list_page_past_the_end_returns_empty_page_and_real_total(
    db_session: AsyncSession, workspace_id: UUID
) -> None:
    """A page past the end returns ([], 3): the real total, not a page count.

    This is the fallback path in ``fetch_page`` — no row comes back to carry
    the window count, so the caller must still learn the real total.
    """
    repo = SQLAlchemyTaskRepository(db_session)
    story = await _seed_story(db_session, workspace_id, "Paged")
    # One completed version carries all three tasks (see the mid-page test).
    version = await seed_extraction(db_session, story.id, status=ExtractionStatus.COMPLETED)
    for title in ("s1", "s2", "s3"):
        await _seed_task(db_session, story.id, title, extraction=version)

    page, total = await repo.list_page(user_story_id=story.id, limit=2, offset=4)

    assert page == []
    assert total == 3


@pytest.mark.asyncio
async def test_list_page_by_workspace_returns_only_that_workspaces_tasks(
    db_session: AsyncSession,
) -> None:
    """list_page(workspace_id=...) returns only that workspace's tasks.

    Tasks have no workspace column: the scope walks ``task → story → project``
    and filters on the project's workspace, the same two joins the unpaginated
    read used.
    """
    repo = SQLAlchemyTaskRepository(db_session)
    alpha_ws = await create_workspace(db_session, name="Alpha", slug="alpha-task-list-page")
    beta_ws = await create_workspace(db_session, name="Beta", slug="beta-task-list-page")
    alpha_story = await _seed_story(db_session, alpha_ws.id, "Alpha project")
    beta_story = await _seed_story(db_session, beta_ws.id, "Beta project")
    # One completed version per story so the tasks are visible to the read.
    alpha_v = await seed_extraction(db_session, alpha_story.id, status=ExtractionStatus.COMPLETED)
    beta_v = await seed_extraction(db_session, beta_story.id, status=ExtractionStatus.COMPLETED)
    await _seed_task(db_session, alpha_story.id, "alpha-task", extraction=alpha_v)
    await _seed_task(db_session, beta_story.id, "beta-task", extraction=beta_v)

    page, total = await repo.list_page(workspace_id=alpha_ws.id, limit=10, offset=0)

    assert total == 1
    assert [t.title for t in page] == ["alpha-task"]


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

    repo = SQLAlchemyTaskRepository(db_session)

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
    repo = SQLAlchemyTaskRepository(db_session)

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
    repo = SQLAlchemyTaskRepository(db_session)
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

    # The ``project_id`` scope joins the mutual exclusion (versioning-visibility
    # WU2): it refuses every other scope pairwise.
    with pytest.raises(ValueError):
        await repo.list_page(project_id=uuid4(), workspace_id=workspace_id, limit=10, offset=0)

    with pytest.raises(ValueError):
        await repo.list_page(project_id=uuid4(), user_story_id=story.id, limit=10, offset=0)

    with pytest.raises(ValueError):
        await repo.list_page(project_id=uuid4(), workspace_ids=[workspace_id], limit=10, offset=0)


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

    repo = SQLAlchemyTaskRepository(db_session)
    story = await _seed_story(db_session, workspace_id, "Ordered")
    await _seed_task(db_session, story.id, "only")

    event.listen(test_engine.sync_engine, "before_cursor_execute", record)
    try:
        await repo.list_page(user_story_id=story.id, limit=10, offset=0)
    finally:
        event.remove(test_engine.sync_engine, "before_cursor_execute", record)

    page_queries = [s for s in statements if "FROM tasks" in s]
    assert len(page_queries) == 1, page_queries

    order_by = page_queries[0].split("ORDER BY", 1)[-1]
    assert "tasks.created_at DESC" in order_by, order_by
    assert "tasks.id DESC" in order_by, order_by


@pytest.mark.asyncio
async def test_list_all(db_session: AsyncSession, story_id: UUID) -> None:
    """list returns all tasks."""
    repo = SQLAlchemyTaskRepository(db_session)
    await _seed_task(db_session, story_id, "Task 1")
    await _seed_task(db_session, story_id, "Task 2")

    tasks = await repo.list()
    assert len(tasks) == 2


class TestCurrentVersionPredicate:
    """D-a-5 item 2: reads answer the story's current version only.

    Currency is derived — ``status == completed`` plus the highest
    ``version_number`` — never stored (slice (a)'s decision), so every case
    seeds two completed versions and pins which one the read answers. The
    predicate must live on the same ``scope`` clause the page statement and
    its fallback ``count_stmt`` share, or ``total`` keeps counting superseded
    rows: a page of 4 that reports 12 is the failure mode these tests exist
    to prevent.
    """

    @staticmethod
    async def _seed_two_completed_versions(
        db_session: AsyncSession, story: UserStory
    ) -> tuple[Task, Task]:
        """Seed v1 and v2, both completed, four tasks each; return (v1, v2).

        ``seed_extraction`` mints ``version_number`` sequentially per story
        through the birth path, so the second call is strictly the higher
        version — the current one, once both are completed.
        """
        v1 = await seed_extraction(db_session, story.id, status=ExtractionStatus.COMPLETED)
        for i in range(4):
            await _seed_task(db_session, story.id, f"v1-{i}", extraction=v1)
        v2 = await seed_extraction(db_session, story.id, status=ExtractionStatus.COMPLETED)
        for i in range(4):
            await _seed_task(db_session, story.id, f"v2-{i}", extraction=v2)
        return v1, v2

    @pytest.mark.asyncio
    async def test_story_scope_returns_only_the_current_versions_tasks(
        self, db_session: AsyncSession, workspace_id: UUID
    ) -> None:
        """Story scope with v1 and v2 both completed: only v2's 4 tasks, total 4."""
        repo = SQLAlchemyTaskRepository(db_session)
        story = await _seed_story(db_session, workspace_id, "Versioned")
        v1, _v2 = await self._seed_two_completed_versions(db_session, story)

        page, total = await repo.list_page(user_story_id=story.id, limit=10, offset=0)

        assert total == 4
        assert len(page) == 4
        assert all(t.extraction_id != v1.id for t in page)
        assert {t.title for t in page} == {f"v2-{i}" for i in range(4)}

    @pytest.mark.asyncio
    async def test_page_past_the_end_carries_the_filtered_total(
        self, db_session: AsyncSession, workspace_id: UUID
    ) -> None:
        """A page past the end reports the filtered total, not the raw row count.

        This is the fallback ``count_stmt`` path in ``fetch_page`` — the one
        statement that would keep counting superseded rows if the predicate
        were attached to the page statement but not to the shared ``scope``.
        """
        repo = SQLAlchemyTaskRepository(db_session)
        story = await _seed_story(db_session, workspace_id, "Past the end")
        await self._seed_two_completed_versions(db_session, story)

        page, total = await repo.list_page(user_story_id=story.id, limit=2, offset=10)

        assert page == []
        assert total == 4

    @pytest.mark.asyncio
    async def test_workspace_scope_returns_only_current_tasks(
        self, db_session: AsyncSession, workspace_id: UUID
    ) -> None:
        """Workspace scope: superseded versions contribute nothing, total == len(items).

        The workspace arm cannot use the story's scalar subquery (it has no
        single story), so it carries the NOT EXISTS form: a task survives only
        when no higher-numbered completed version of its story exists.
        """
        repo = SQLAlchemyTaskRepository(db_session)
        superseded = await _seed_story(db_session, workspace_id, "Superseded")
        await self._seed_two_completed_versions(db_session, superseded)
        plain = await _seed_story(db_session, workspace_id, "Plain")
        plain_v = await seed_extraction(db_session, plain.id, status=ExtractionStatus.COMPLETED)
        await _seed_task(db_session, plain.id, "plain-task", extraction=plain_v)

        page, total = await repo.list_page(workspace_id=workspace_id, limit=10, offset=0)

        assert total == len(page) == 5
        assert {t.title for t in page} == {f"v2-{i}" for i in range(4)} | {"plain-task"}

    @pytest.mark.asyncio
    async def test_workspace_ids_scope_is_filtered_too(
        self, db_session: AsyncSession, workspace_id: UUID
    ) -> None:
        """The unfiltered ``workspace_ids`` scope applies the same predicate."""
        repo = SQLAlchemyTaskRepository(db_session)
        superseded = await _seed_story(db_session, workspace_id, "Superseded")
        await self._seed_two_completed_versions(db_session, superseded)

        page, total = await repo.list_page(workspace_ids=[workspace_id], limit=10, offset=0)

        assert total == len(page) == 4
        assert {t.title for t in page} == {f"v2-{i}" for i in range(4)}

    @pytest.mark.asyncio
    async def test_explicit_extraction_id_reads_exactly_that_version(
        self, db_session: AsyncSession, workspace_id: UUID
    ) -> None:
        """An explicit ``extraction_id`` bypasses the currency predicate.

        Reading v1 on purpose must return v1's tasks, not nothing: the
        version selector's per-version read depends on this arm existing.
        """
        repo = SQLAlchemyTaskRepository(db_session)
        story = await _seed_story(db_session, workspace_id, "Explicit version")
        v1, v2 = await self._seed_two_completed_versions(db_session, story)

        page, total = await repo.list_page(
            user_story_id=story.id, extraction_id=v1.id, limit=10, offset=0
        )

        assert total == 4
        assert {t.title for t in page} == {f"v1-{i}" for i in range(4)}
        assert all(t.extraction_id == v1.id for t in page)
        assert all(t.extraction_id != v2.id for t in page)

    @pytest.mark.asyncio
    async def test_list_current_by_workspace_returns_only_current_tasks(
        self, db_session: AsyncSession, workspace_id: UUID
    ) -> None:
        """``list_current_by_workspace`` carries the predicate unpaginated (the export read)."""
        repo = SQLAlchemyTaskRepository(db_session)
        superseded = await _seed_story(db_session, workspace_id, "Superseded")
        await self._seed_two_completed_versions(db_session, superseded)
        plain = await _seed_story(db_session, workspace_id, "Plain")
        plain_v = await seed_extraction(db_session, plain.id, status=ExtractionStatus.COMPLETED)
        await _seed_task(db_session, plain.id, "plain-task", extraction=plain_v)

        tasks = await repo.list_current_by_workspace(workspace_id)

        assert len(tasks) == 5
        assert {t.title for t in tasks} == {f"v2-{i}" for i in range(4)} | {"plain-task"}


async def _seed_context_project(db_session: AsyncSession, workspace_id: UUID, name: str) -> Project:
    """Save one project for the context-read tests and return it."""
    return await SQLAlchemyProjectRepository(db_session).save(
        Project(name=name, workspace_id=workspace_id)
    )


async def _seed_story_in(db_session: AsyncSession, project: Project, feature: str) -> UserStory:
    """Save one story inside ``project`` and return it."""
    return await SQLAlchemyUserStoryRepository(db_session).save(
        UserStory(
            project_id=project.id,
            actor="user",
            feature=feature,
            benefit="value",
            raw_text=f"As a user, I want {feature} so that value",
        )
    )


async def _mark(
    db_session: AsyncSession, task_id: UUID, reason: str = "Duplicates the auth task"
) -> TaskInvalidation:
    """Create an active mark through the same write path production uses."""
    return await SQLAlchemyTaskInvalidationRepository(db_session).create(
        TaskInvalidation(task_id=task_id, reason=reason)
    )


class TestProjectScope:
    """The ``project_id`` scope of ``list_page`` (versioning-visibility WU2).

    D6: a mirror of the workspace branch — the same ``task → story → project``
    walk and the same ``_current_version_only`` predicate, so a project-scoped
    board obeys the same currency contract as the workspace board and its
    ``total`` cannot keep counting rows the page dropped.
    """

    @pytest.mark.asyncio
    async def test_project_scope_answers_only_that_projects_current_tasks(
        self, db_session: AsyncSession, workspace_id: UUID
    ) -> None:
        """Two projects in one workspace: only the asked project's current-version tasks.

        The superseded version of the asked project's story contributes nothing
        (the same predicate the workspace arm carries), the sibling project's
        task never leaks in, and ``total`` agrees with the rows returned.
        """
        repo = SQLAlchemyTaskRepository(db_session)
        mine = await SQLAlchemyProjectRepository(db_session).save(
            Project(name="Mine", workspace_id=workspace_id)
        )
        other = await SQLAlchemyProjectRepository(db_session).save(
            Project(name="Other", workspace_id=workspace_id)
        )
        mine_story = await _seed_story_in(db_session, mine, "mine story")
        other_story = await _seed_story_in(db_session, other, "other story")

        mine_v1 = await seed_extraction(
            db_session, mine_story.id, status=ExtractionStatus.COMPLETED
        )
        await _seed_task(db_session, mine_story.id, "mine-v1", extraction=mine_v1)
        mine_v2 = await seed_extraction(
            db_session, mine_story.id, status=ExtractionStatus.COMPLETED
        )
        await _seed_task(db_session, mine_story.id, "mine-v2-a", extraction=mine_v2)
        await _seed_task(db_session, mine_story.id, "mine-v2-b", extraction=mine_v2)
        other_v = await seed_extraction(
            db_session, other_story.id, status=ExtractionStatus.COMPLETED
        )
        await _seed_task(db_session, other_story.id, "other-task", extraction=other_v)

        page, total = await repo.list_page(project_id=mine.id, limit=10, offset=0)

        assert total == len(page) == 2
        assert {t.title for t in page} == {"mine-v2-a", "mine-v2-b"}
        assert all(t.user_story_id == mine_story.id for t in page)

    @pytest.mark.asyncio
    async def test_project_scope_for_a_project_with_no_stories_answers_empty(
        self, db_session: AsyncSession, workspace_id: UUID
    ) -> None:
        """A real project with no stories: an empty page and total 0."""
        repo = SQLAlchemyTaskRepository(db_session)
        project = await SQLAlchemyProjectRepository(db_session).save(
            Project(name="Empty", workspace_id=workspace_id)
        )

        page, total = await repo.list_page(project_id=project.id, limit=10, offset=0)

        assert page == []
        assert total == 0


class TestListForContext:
    """The prompt-context read: current-version, valid tasks of one project
    except the excluded story's, unpaginated.

    Three facts belong to the statement, not to a Python pass: currency (no
    higher-numbered completed version of the story), validity (no active mark
    on the task), and the exclusion of the story being decomposed. A page
    window would truncate the context block silently — the read is deliberately
    unbounded, and the signature carries no ``limit``/``offset`` to reopen one.
    """

    @staticmethod
    def _assert_no_window(target: object) -> None:
        """Pin the signature over both the port and the SQLAlchemy implementation."""
        signature = inspect.signature(target)  # type: ignore[arg-type]
        assert "limit" not in signature.parameters, signature
        assert "offset" not in signature.parameters, signature
        exclude = signature.parameters["exclude_story_id"]
        assert exclude.kind is inspect.Parameter.KEYWORD_ONLY, signature
        assert exclude.default is inspect.Parameter.empty, signature

    @pytest.mark.asyncio
    async def test_the_excluded_story_is_absent_in_every_version(
        self, db_session: AsyncSession, workspace_id: UUID
    ) -> None:
        """v1 completed + v2 completed, both with tasks: neither version's tasks return.

        The exclusion rides in the ``WHERE`` on ``tasks.user_story_id``, so it
        holds across every version of the excluded story at once — no Python
        filter re-checks it row by row.
        """
        repo = SQLAlchemyTaskRepository(db_session)
        project = await _seed_context_project(db_session, workspace_id, "Excluded story")
        excluded = await _seed_story_in(db_session, project, "being-decomposed")
        other = await _seed_story_in(db_session, project, "other")
        excluded_v1 = await seed_extraction(
            db_session, excluded.id, status=ExtractionStatus.COMPLETED
        )
        excluded_v2 = await seed_extraction(
            db_session, excluded.id, status=ExtractionStatus.COMPLETED
        )
        await _seed_task(db_session, excluded.id, "excluded-v1", extraction=excluded_v1)
        await _seed_task(db_session, excluded.id, "excluded-v2", extraction=excluded_v2)
        other_v = await seed_extraction(db_session, other.id, status=ExtractionStatus.COMPLETED)
        await _seed_task(db_session, other.id, "other-task", extraction=other_v)

        rows = await repo.list_for_context(project.id, exclude_story_id=excluded.id)

        assert [r.title for r in rows] == ["other-task"]
        assert all(r.user_story_id == other.id for r in rows)

    @pytest.mark.asyncio
    async def test_an_active_mark_hides_the_task_and_revoking_restores_it(
        self, db_session: AsyncSession, workspace_id: UUID
    ) -> None:
        """A task with an active mark is absent; the same task returns after revoke.

        The mark is created and revoked through the invalidation repository —
        the same ``create``/``revoke`` path the mark endpoints drive — so the
        read answers the production validity rule, not a fixture shorthand.
        """
        repo = SQLAlchemyTaskRepository(db_session)
        invalidations = SQLAlchemyTaskInvalidationRepository(db_session)
        project = await _seed_context_project(db_session, workspace_id, "Marked task")
        excluded = await _seed_story_in(db_session, project, "being-decomposed")
        marked_story = await _seed_story_in(db_session, project, "marked")
        plain = await _seed_story_in(db_session, project, "plain")
        marked_v = await seed_extraction(
            db_session, marked_story.id, status=ExtractionStatus.COMPLETED
        )
        plain_v = await seed_extraction(db_session, plain.id, status=ExtractionStatus.COMPLETED)
        marked_task = await _seed_task(
            db_session, marked_story.id, "marked-task", extraction=marked_v
        )
        await _seed_task(db_session, plain.id, "plain-task", extraction=plain_v)

        mark = await _mark(db_session, marked_task.id)

        rows = await repo.list_for_context(project.id, exclude_story_id=excluded.id)
        assert [r.title for r in rows] == ["plain-task"]

        await invalidations.revoke(mark.id, revoked_by=uuid4(), revoked_at=datetime.now(UTC))

        rows = await repo.list_for_context(project.id, exclude_story_id=excluded.id)
        assert [r.title for r in rows] == ["marked-task", "plain-task"]

    @pytest.mark.asyncio
    async def test_a_superseded_versions_tasks_are_absent_when_a_newer_completed_exists(
        self, db_session: AsyncSession, workspace_id: UUID
    ) -> None:
        """v2 completed above v1 completed: only v2's task is current.

        Currency is the same derived rule the task reads carry — ``status ==
        completed`` plus no higher-numbered completed version — never stored.
        """
        repo = SQLAlchemyTaskRepository(db_session)
        project = await _seed_context_project(db_session, workspace_id, "Superseded")
        versioned = await _seed_story_in(db_session, project, "versioned")
        other = await _seed_story_in(db_session, project, "other")
        v1 = await seed_extraction(db_session, versioned.id, status=ExtractionStatus.COMPLETED)
        v2 = await seed_extraction(db_session, versioned.id, status=ExtractionStatus.COMPLETED)
        await _seed_task(db_session, versioned.id, "v1-task", extraction=v1)
        await _seed_task(db_session, versioned.id, "v2-task", extraction=v2)
        other_v = await seed_extraction(db_session, other.id, status=ExtractionStatus.COMPLETED)
        await _seed_task(db_session, other.id, "other-task", extraction=other_v)

        rows = await repo.list_for_context(project.id, exclude_story_id=other.id)

        assert [r.title for r in rows] == ["v2-task"]

    @pytest.mark.asyncio
    async def test_a_pending_version_above_a_completed_one_leaves_it_current(
        self, db_session: AsyncSession, workspace_id: UUID
    ) -> None:
        """A ``pending`` v3 does not supersede a completed v2: v2's tasks stay current.

        Only a *completed* higher version retires the tasks below it — a run
        still in flight has produced nothing to replace them with.
        """
        repo = SQLAlchemyTaskRepository(db_session)
        project = await _seed_context_project(db_session, workspace_id, "Pending above")
        versioned = await _seed_story_in(db_session, project, "versioned")
        other = await _seed_story_in(db_session, project, "other")
        v1 = await seed_extraction(db_session, versioned.id, status=ExtractionStatus.COMPLETED)
        v2 = await seed_extraction(db_session, versioned.id, status=ExtractionStatus.COMPLETED)
        await seed_extraction(db_session, versioned.id, status=ExtractionStatus.PENDING)
        await _seed_task(db_session, versioned.id, "v1-task", extraction=v1)
        await _seed_task(db_session, versioned.id, "v2-task", extraction=v2)
        other_v = await seed_extraction(db_session, other.id, status=ExtractionStatus.COMPLETED)
        await _seed_task(db_session, other.id, "other-task", extraction=other_v)

        rows = await repo.list_for_context(project.id, exclude_story_id=other.id)

        assert [r.title for r in rows] == ["v2-task"]

    @pytest.mark.asyncio
    async def test_the_order_is_deterministic_oldest_first(
        self, db_session: AsyncSession, workspace_id: UUID
    ) -> None:
        """Two calls over the same state return the same ``created_at, id`` order.

        Determinism is what makes two runs over an unchanged project compose
        byte-identical context blocks.
        """
        repo = SQLAlchemyTaskRepository(db_session)
        project = await _seed_context_project(db_session, workspace_id, "Ordered")
        story = await _seed_story_in(db_session, project, "ordered")
        unrelated = uuid4()
        version = await seed_extraction(db_session, story.id, status=ExtractionStatus.COMPLETED)
        await _seed_task(
            db_session,
            story.id,
            "newest",
            extraction=version,
            created_at=datetime(2026, 1, 3),
        )
        await _seed_task(
            db_session,
            story.id,
            "oldest",
            extraction=version,
            created_at=datetime(2026, 1, 1),
        )
        await _seed_task(
            db_session,
            story.id,
            "middle",
            extraction=version,
            created_at=datetime(2026, 1, 2),
        )

        one = await repo.list_for_context(project.id, exclude_story_id=unrelated)
        two = await repo.list_for_context(project.id, exclude_story_id=unrelated)

        assert [r.title for r in one] == ["oldest", "middle", "newest"]
        assert one == two

    @pytest.mark.asyncio
    async def test_rows_carry_title_status_and_owning_story(
        self, db_session: AsyncSession, workspace_id: UUID
    ) -> None:
        """The projection is exactly what the prompt block needs, keyed per task."""
        repo = SQLAlchemyTaskRepository(db_session)
        project = await _seed_context_project(db_session, workspace_id, "Projection")
        story = await _seed_story_in(db_session, project, "projected")
        version = await seed_extraction(db_session, story.id, status=ExtractionStatus.COMPLETED)
        task = await _seed_task(db_session, story.id, "projected-task", extraction=version)

        rows = await repo.list_for_context(project.id, exclude_story_id=uuid4())

        assert [(r.title, r.status, r.user_story_id) for r in rows] == [
            ("projected-task", task.status, story.id)
        ]
        assert rows[0].status is TaskStatus.BACKLOG

    @pytest.mark.asyncio
    async def test_matches_the_current_version_read_the_api_serves(
        self, db_session: AsyncSession, workspace_id: UUID
    ) -> None:
        """Cross-check: the context read equals (b)'s current-version page read.

        The currency rule is now expressed in a third place, so a test ties the
        shapes: ``list_for_context(project)`` must equal the union of the
        current-version rows ``list_page(workspace_id=...)`` — the same read
        ``GET /tasks?workspace_id=`` serves — returns for the project's
        stories, over a two-version, one-invalid-mark fixture.

        The mark sits on a *superseded* version's task on purpose: both reads
        drop that version by currency, so their scopes coincide and this test
        isolates the currency rule. The mark's own effect on the context read
        is the active-mark case above. The excluded story's rows are dropped
        from the page in the test only to align the two scopes — the production
        read puts that exclusion in the ``WHERE``.
        """
        repo = SQLAlchemyTaskRepository(db_session)
        project = await _seed_context_project(db_session, workspace_id, "Cross-check")
        two_versioned = await _seed_story_in(db_session, project, "two-versioned")
        plain = await _seed_story_in(db_session, project, "plain")
        excluded = await _seed_story_in(db_session, project, "being-decomposed")
        v1 = await seed_extraction(db_session, two_versioned.id, status=ExtractionStatus.COMPLETED)
        v2 = await seed_extraction(db_session, two_versioned.id, status=ExtractionStatus.COMPLETED)
        v1_plain = await _seed_task(db_session, two_versioned.id, "v1-plain", extraction=v1)
        v1_marked = await _seed_task(db_session, two_versioned.id, "v1-marked", extraction=v1)
        await _seed_task(db_session, two_versioned.id, "v2-task", extraction=v2)
        plain_v = await seed_extraction(db_session, plain.id, status=ExtractionStatus.COMPLETED)
        await _seed_task(db_session, plain.id, "plain-task", extraction=plain_v)
        excluded_v = await seed_extraction(
            db_session, excluded.id, status=ExtractionStatus.COMPLETED
        )
        await _seed_task(db_session, excluded.id, "excluded-task", extraction=excluded_v)
        await _mark(db_session, v1_marked.id, "Too coarse to implement")
        assert v1_plain.id  # the superseded task stays unmarked

        context_rows = await repo.list_for_context(project.id, exclude_story_id=excluded.id)
        page, _total = await repo.list_page(workspace_id=workspace_id, limit=100, offset=0)

        expected = sorted(t.title for t in page if t.user_story_id != excluded.id)
        assert expected == ["plain-task", "v2-task"], expected
        assert sorted(r.title for r in context_rows) == expected

    def test_signature_carries_no_limit_or_offset(self) -> None:
        """Neither the port nor the implementation exposes a page window."""
        for target in (
            TaskRepository.list_for_context,
            SQLAlchemyTaskRepository.list_for_context,
        ):
            self._assert_no_window(target)
