"""Postgres-only scale proof: the two context reads stay unbounded at 1000 stories (WU1 1.14).

SQLite cannot prove scale semantics worth trusting here (it enforces no foreign keys and its
query planner is not the one production runs), so these cases run against a Postgres 16
testcontainer — the same harness shape as ``test_projects_integration.py`` and
``test_migration_chain.py``. Each case carries the ``_docker_reachable()`` skipif copied from
``test_migration_chain.py`` rather than shared: the marks evaluate the probe at import time and
that module documents why the copy must move together with its skip semantics. No Docker daemon
means every case skips and the scale proof stays unverified — that is the honest status, not a
green. CI owns the verdict: these cases run for real on GitHub runners, which have a daemon.

Why the stories are **not** created through the HTTP import endpoint: none of the container
integration files wires the FastAPI app, its Auth.js bearer-JWT dependency and a workspace
membership against a live server — they drive repositories and entities directly against the
container, and building that scaffolding here is not this file's job. What runs instead is the
import's own write path, minus only the HTTP and auth shell: ``parse_story_csv`` decodes a
generated 1000-row CSV (exactly at the parser's ``MAX_ROWS`` cap), ``validate_import`` classifies
it, and the stories persist through the same ``save_many`` commit the route executes. The rows
therefore enter through the import machinery — parse, validate, bulk write — and not through
hand-built model inserts.
"""

from __future__ import annotations

import os
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from uuid import UUID

import pytest
import pytest_asyncio
from sqlalchemy import Connection, func, make_url, select
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    async_sessionmaker,
    create_async_engine,
)

from storico.domain.entities.project import Project
from storico.domain.entities.user import User
from storico.domain.entities.user_story import UserStory
from storico.domain.entities.workspace import Workspace
from storico.domain.services.story_import import ImportRow, validate_import
from storico.infrastructure.database.models import Base, UserStoryModel
from storico.infrastructure.database.repositories import (
    SQLAlchemyProjectRepository,
    SQLAlchemyTaskRepository,
    SQLAlchemyUserRepository,
)
from storico.infrastructure.database.repositories.user_story_repository import (
    SQLAlchemyUserStoryRepository,
)
from storico.infrastructure.database.repositories.workspace_repository import (
    SQLAlchemyWorkspaceRepository,
)
from storico.infrastructure.parsers.story_csv import parse_story_csv
from tests._helpers import seed_task


def _docker_reachable() -> bool:
    """Best-effort check — is the docker daemon pickable in $DOCKER_HOST?

    Copied from ``tests/test_integration/test_migration_chain.py`` (which copied it from
    ``test_projects_integration.py``): the skipif marks below evaluate it at import time, and
    this file's edit surface has no home for a shared helper module. The copies must move
    together, or their skip semantics silently diverge.
    """
    host = os.environ.get("DOCKER_HOST", "")
    # Docker Desktop default unix socket path:
    socket_path = host.removeprefix("unix://") if host.startswith("unix://") else ""
    if not socket_path:
        socket_path = os.path.expanduser("~/.docker/run/docker.sock")
        if not os.path.exists(socket_path):
            socket_path = "/var/run/docker.sock"
    return os.path.exists(socket_path) and os.access(socket_path, os.W_OK)


# Applied per case, never to the module — matching test_migration_chain.py's pattern.
_needs_docker = pytest.mark.skipif(
    not _docker_reachable(),
    reason="Docker daemon unreachable — this integration test needs docker to spawn a Postgres container via testcontainers.",
)


def _create_pg_enum_types(connection: Connection) -> None:
    """Create the Postgres enum types the models deliberately do not create.

    Copied from ``test_projects_integration.py``: every status column is declared
    ``PGEnum(..., create_type=False)`` because the Alembic migrations own the ``CREATE TYPE``
    statements, so a schema built with ``create_all`` must emit the types first or Postgres
    fails with ``type "..." does not exist``.
    """
    from sqlalchemy.dialects.postgresql import ENUM as PGEnum

    created: set[str | None] = set()
    for table in Base.metadata.tables.values():
        for column in table.columns:
            enum_type = column.type
            if isinstance(enum_type, PGEnum) and enum_type.name not in created:
                enum_type.create(connection, checkfirst=True)
                created.add(enum_type.name)


@dataclass(frozen=True)
class _ScaleFixture:
    """The seeded 1000-story project and the story excluded from the reads."""

    project_id: UUID
    excluded_story_id: UUID
    story_count: int


# loop_scope="module" keeps the fixtures on the loop that owns the engine; pytest-asyncio
# otherwise gives every single test a fresh loop, and asyncpg connections created on one loop
# cannot be awaited from another (same reason test_projects_integration.py documents).
@pytest_asyncio.fixture(scope="module", loop_scope="module")
async def pg_engine() -> AsyncGenerator[AsyncEngine, None]:
    """Start Postgres 16 in a testcontainer and wire an async engine to it."""
    # Imported lazily so the module import never blocks on testcontainers — it imports docker,
    # which is heavy and may pull images.
    from testcontainers.community.postgres import PostgresContainer

    with PostgresContainer("postgres:16-alpine") as pg:
        url = make_url(pg.get_connection_url()).set(drivername="postgresql+asyncpg")
        engine = create_async_engine(url, pool_size=5, max_overflow=10, pool_pre_ping=True)
        async with engine.begin() as conn:
            # Types before tables: the models' PGEnum columns name types create_all never emits.
            await conn.run_sync(_create_pg_enum_types)
            await conn.run_sync(Base.metadata.create_all)
        yield engine
        await engine.dispose()


@pytest_asyncio.fixture(scope="module", loop_scope="module")
async def scale_project(pg_engine: AsyncEngine) -> AsyncGenerator[_ScaleFixture, None]:
    """Seed one project with 1000 stories through the CSV import's write path.

    The import machinery — ``parse_story_csv`` → ``validate_import`` → ``save_many`` — is the
    exact write path ``POST /api/v1/workspaces/{ws}/stories/import`` executes after its HTTP
    and auth shell (see the module docstring for why that shell is not driven here). Each story
    then gets one completed run with one task, so the task read has one valid current-version
    task per story to return.
    """
    factory = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with factory() as session:
        owner = await SQLAlchemyUserRepository(session).save(
            User(email="scale-owner@test.example", name="Scale Owner")
        )
        workspace = await SQLAlchemyWorkspaceRepository(session).save(
            Workspace(
                name="Scale Workspace",
                slug="scale-workspace",
                owner_id=owner.id,
            )
        )
        project = await SQLAlchemyProjectRepository(session).save(
            Project(name="Scale Project", workspace_id=workspace.id)
        )

        csv_lines = ["actor,feature,benefit"]
        csv_lines += [f"user,implement scale feature {i},measurable value" for i in range(1000)]
        parsed = parse_story_csv("\n".join(csv_lines).encode("utf-8"))
        report = validate_import(
            [
                ImportRow(
                    line_number=row.line_number,
                    actor=row.actor,
                    feature=row.feature,
                    benefit=row.benefit,
                    raw_text=row.raw_text,
                    field_count=row.field_count,
                    expected_field_count=parsed.expected_field_count,
                )
                for row in parsed.rows
            ],
            parsed.mode,
            existing={},
        )
        assert not report.blocked, [e.reason for e in report.errors]
        assert len(report.new_stories) == 1000

        saved = await SQLAlchemyUserStoryRepository(session).save_many(
            [
                UserStory(
                    project_id=project.id,
                    actor=s.actor,
                    feature=s.feature,
                    benefit=s.benefit,
                    raw_text=s.raw_text,
                )
                for s in report.new_stories
            ]
        )
        assert len(saved) == 1000

        for story in saved:
            # One completed run with one task per story: the default of ``seed_task``
            # mints the COMPLETED extraction the task's NOT NULL FK requires.
            await seed_task(session, story.id, f"Task for scale story {story.id}")

        yield _ScaleFixture(
            project_id=project.id,
            excluded_story_id=saved[0].id,
            story_count=len(saved),
        )


@pytest.mark.integration
@_needs_docker
@pytest.mark.asyncio(loop_scope="module")
async def test_the_story_read_returns_999_of_1000_without_the_excluded_one(
    pg_engine: AsyncEngine, scale_project: _ScaleFixture
) -> None:
    """A 1000-story project answers 999 rows for one exclusion — past every page cap.

    The count equals the project's story total minus one, read from the table
    itself, so the read neither truncates to ``list_page``'s 20/100 window nor
    loses a row.
    """
    factory = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with factory() as session:
        rows = await SQLAlchemyUserStoryRepository(session).list_for_context(
            scale_project.project_id, exclude_story_id=scale_project.excluded_story_id
        )
        total = (
            await session.execute(
                select(func.count())
                .select_from(UserStoryModel)
                .where(UserStoryModel.project_id == scale_project.project_id)
            )
        ).scalar_one()

    assert len(rows) == 999
    assert len(rows) == total - 1
    assert all(row.id != scale_project.excluded_story_id for row in rows)


@pytest.mark.integration
@_needs_docker
@pytest.mark.asyncio(loop_scope="module")
async def test_the_task_read_returns_every_valid_current_version_task_without_a_limit(
    pg_engine: AsyncEngine, scale_project: _ScaleFixture
) -> None:
    """999 current-version tasks come back from one statement — no ``LIMIT`` intervenes.

    Every story carries exactly one completed run with one task and no active
    mark, so every task is valid and current: the read must answer all 999 of
    the non-excluded stories' tasks. 999 is far past the API's page cap of 100,
    which is the truncation an unbounded read exists to prevent. That no
    ``limit``/``offset`` exists in the signature at all is pinned at the unit
    layer (``test_task_repo.py::TestListForContext::test_signature_carries_no_limit_or_offset``).
    """
    factory = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with factory() as session:
        rows = await SQLAlchemyTaskRepository(session).list_for_context(
            scale_project.project_id, exclude_story_id=scale_project.excluded_story_id
        )

    assert len(rows) == 999
    assert all(row.user_story_id != scale_project.excluded_story_id for row in rows)
    # One task per story, each owned by the story the read says it came from.
    assert len({row.user_story_id for row in rows}) == 999


@pytest.mark.integration
@_needs_docker
@pytest.mark.asyncio(loop_scope="module")
async def test_two_calls_over_the_same_state_are_byte_identical(
    pg_engine: AsyncEngine, scale_project: _ScaleFixture
) -> None:
    """Both reads answer identical rows twice — the determinism the prompt block needs."""
    factory = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with factory() as session:
        stories_one = await SQLAlchemyUserStoryRepository(session).list_for_context(
            scale_project.project_id, exclude_story_id=scale_project.excluded_story_id
        )
        tasks_one = await SQLAlchemyTaskRepository(session).list_for_context(
            scale_project.project_id, exclude_story_id=scale_project.excluded_story_id
        )
        stories_two = await SQLAlchemyUserStoryRepository(session).list_for_context(
            scale_project.project_id, exclude_story_id=scale_project.excluded_story_id
        )
        tasks_two = await SQLAlchemyTaskRepository(session).list_for_context(
            scale_project.project_id, exclude_story_id=scale_project.excluded_story_id
        )

    assert stories_one == stories_two
    assert tasks_one == tasks_two
