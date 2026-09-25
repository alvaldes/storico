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

import pytest
import pytest_asyncio
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from storico.domain.entities import Extraction, Task
from storico.infrastructure.database.repositories import (
    SQLAlchemyExtractionRepository,
    SQLAlchemyTaskRepository,
)

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
    the test is timing, and an extraction has no HTTP creation route at all.
    """

    async def _seed(seeded) -> None:
        await SQLAlchemyTaskRepository(db_session).save(
            Task(user_story_id=seeded.story_id, title="Counted task")
        )
        await SQLAlchemyExtractionRepository(db_session).save(
            Extraction(
                user_story_id=seeded.story_id,
                model_used="llama3.2",
                raw_response="1. summary: Task one\ndescription: Do it",
            )
        )

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
async def test_a_caller_in_no_workspace_still_gets_an_empty_page(authed_client) -> None:
    """No memberships is the path where the fold must not even be attempted."""
    response = await authed_client.get("/api/v1/stories/")

    assert response.status_code == 200
    assert response.json()["items"] == []
    assert response.json()["total"] == 0
