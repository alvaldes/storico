"""The unfiltered list endpoints must not issue one query per workspace.

The "no filter" branch of ``/api/v1/stories/``, ``/api/v1/tasks/`` and ``/api/v1/extractions/``
awaited one repository call per workspace the caller belongs to. The dev database is a Supabase
pooler in ``us-east-1`` where one statement costs ~2s — a bare ``SELECT 1`` already measures
800ms in ``/api/v1/health`` — and the account used for that measurement belongs to 12 workspaces.
Those three calls awaited one statement per workspace and measured 31.7s, 25.6s and 30.4s; their
filtered twins, which await two statements, answered in 5-6s.

These tests pin the replacement: **one** statement against the listed table, no matter how many
workspaces the caller belongs to. The statements are counted on the engine rather than by mocking
the repository, because the defect was the number of statements issued — a mock the route calls
once would keep passing if the query itself were split in two.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
import pytest_asyncio
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from storico.domain.entities.extraction import ExtractionStatus
from tests._helpers import seed_extraction, seed_task

# endpoint, the table that endpoint lists, and whether the listed rows need seeding on top of a story.
ENDPOINTS = [
    pytest.param("/api/v1/stories/", "user_stories", False, id="stories"),
    pytest.param("/api/v1/tasks/", "tasks", True, id="tasks"),
    pytest.param("/api/v1/extractions/", "extractions", True, id="extractions"),
]

WORKSPACES = 3


@pytest_asyncio.fixture
async def three_workspaces(seed_workspace):
    """Three workspaces the caller belongs to, each with one story."""
    return [await seed_workspace(stories=1) for _ in range(WORKSPACES)]


@pytest_asyncio.fixture
async def seed_listed_rows(db_session: AsyncSession):
    """Add one task and one extraction to a seeded workspace's story.

    Both are saved rather than posted: the task route would be exercised by the same request
    the test is timing, and an extraction has no HTTP creation route at all. The task reuses
    the extraction the test seeds (passed through ``seed_task``) so the row counts below stay
    one task and one extraction per workspace — ``seed_task`` would otherwise mint an extra
    version per task.
    """

    async def _seed(seeded) -> None:
        # The extraction is completed so the task it carries is visible to the
        # current-version reads (D-a-5 item 2); the row counts below are
        # unchanged — one task and one extraction per workspace.
        extraction = await seed_extraction(
            db_session,
            seeded.story_id,
            status=ExtractionStatus.COMPLETED,
            completed_at=datetime.now(UTC),
        )
        await seed_task(db_session, seeded.story_id, "Counted task", extraction=extraction)

    return _seed


class ReadsOf:
    """Count the statements that read one table, on the real engine.

    A context manager so the listener is removed even when an assertion fails: a leaked
    ``before_cursor_execute`` listener would keep recording into a list nobody reads, on an engine
    the next test in the same module reuses.
    """

    def __init__(self, engine: AsyncEngine, table: str) -> None:
        self._engine = engine
        self._needle = f"FROM {table}"
        self.statements: list[str] = []

    def _record(self, _conn, _cursor, statement, _parameters, _context, _executemany) -> None:
        if self._needle in statement:
            self.statements.append(statement)

    def __enter__(self) -> ReadsOf:
        event.listen(self._engine.sync_engine, "before_cursor_execute", self._record)
        return self

    def __exit__(self, *_exc) -> None:
        event.remove(self._engine.sync_engine, "before_cursor_execute", self._record)


@pytest.mark.asyncio
@pytest.mark.parametrize(("endpoint", "table", "needs_rows"), ENDPOINTS)
async def test_unfiltered_list_reads_its_table_once(
    authed_client,
    test_engine: AsyncEngine,
    three_workspaces,
    seed_listed_rows,
    endpoint: str,
    table: str,
    needs_rows: bool,
) -> None:
    """One statement against the listed table, however many workspaces the caller belongs to."""
    if needs_rows:
        for seeded in three_workspaces:
            await seed_listed_rows(seeded)

    with ReadsOf(test_engine, table) as reads:
        response = await authed_client.get(endpoint)

    assert response.status_code == 200
    assert len(reads.statements) == 1, (
        f"{endpoint} read {table} {len(reads.statements)} times; "
        "the workspaces must fold into a single statement"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(("endpoint", "table", "needs_rows"), ENDPOINTS)
async def test_unfiltered_list_still_returns_rows_from_every_workspace(
    authed_client,
    three_workspaces,
    seed_listed_rows,
    endpoint: str,
    table: str,
    needs_rows: bool,
) -> None:
    """The single query returns what the loop returned: every workspace's rows."""
    if needs_rows:
        for seeded in three_workspaces:
            await seed_listed_rows(seeded)

    response = await authed_client.get(endpoint)

    assert response.status_code == 200
    assert response.json()["total"] == WORKSPACES


@pytest.mark.asyncio
async def test_the_unfiltered_task_list_shows_no_superseded_tasks(
    authed_client,
    three_workspaces,
    seed_listed_rows,
    db_session: AsyncSession,
) -> None:
    """The no-parameter ``GET /api/v1/tasks/`` reads current versions only.

    This file's whole point is that the unfiltered branch must not quietly read
    across every workspace's full history — and the current-version predicate
    (D-a-5 item 2) must ride that single statement too. One workspace's story
    carries two completed versions: v1's two tasks are superseded by v2's
    three, so v1's rows are gone from the response while ``total`` agrees with
    the rows actually returned.
    """
    seeded = three_workspaces[0]
    superseded = await seed_extraction(
        db_session,
        seeded.story_id,
        status=ExtractionStatus.COMPLETED,
        completed_at=datetime.now(UTC),
    )
    await seed_task(db_session, seeded.story_id, "Old task 1", extraction=superseded)
    await seed_task(db_session, seeded.story_id, "Old task 2", extraction=superseded)
    current = await seed_extraction(
        db_session,
        seeded.story_id,
        status=ExtractionStatus.COMPLETED,
        completed_at=datetime.now(UTC),
    )
    await seed_task(db_session, seeded.story_id, "New task 1", extraction=current)
    await seed_task(db_session, seeded.story_id, "New task 2", extraction=current)
    await seed_task(db_session, seeded.story_id, "New task 3", extraction=current)
    # A second workspace keeps its ordinary single-version story, so the
    # unfiltered branch is proven to fold workspaces without un-superseding rows.
    await seed_listed_rows(three_workspaces[1])

    response = await authed_client.get("/api/v1/tasks/")

    assert response.status_code == 200
    data = response.json()
    titles = [item["title"] for item in data["items"]]
    assert "Old task 1" not in titles
    assert "Old task 2" not in titles
    # v2's three tasks plus the other workspace's current one.
    assert data["total"] == len(data["items"]) == 4


@pytest.mark.asyncio
async def test_a_caller_in_no_workspace_still_gets_an_empty_page(authed_client) -> None:
    """No memberships is the path where the fold must not even be attempted."""
    response = await authed_client.get("/api/v1/stories/")

    assert response.status_code == 200
    assert response.json()["items"] == []
    assert response.json()["total"] == 0
