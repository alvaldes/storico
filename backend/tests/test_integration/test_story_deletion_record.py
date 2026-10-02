"""Integration tests for revision ``0029`` — the deletion record on real Postgres.

**Nothing in this file executes without a Docker daemon.** On a daemon-less machine every case
here skips, and the invariants it pins stay *unverified*, not green. That is the honest status
task 4.16 records; the SQLite unit layer pins the model's declared shape (no FK to ``stories``,
``deleted_by`` as a ``users.id`` FK), but SQLite ignores ``ON DELETE`` actions entirely, so the
two behaviours that make the record an audit trail — surviving the story cascade, and losing
only ``deleted_by`` when the actor's account dies — are Postgres's to witness, and CI's to run.

What each case adds over the SQLite mirror:

* the ``story_deletions`` row outliving the ``DELETE`` of the story it records, with its values
  (story id, project id, workspace id, the ``(actor, feature, benefit)`` trio, the destroyed
  version numbers) intact — the whole point of holding the identity as values instead of a
  foreign key;
* the actor's account deletion nulling ``deleted_by`` and nothing else, column by column;
* the story delete cascading its extractions, tasks and marks away while a neighbouring story's
  rows in the same workspace are untouched.

The deletion itself goes through the production path — ``SQLAlchemyUserStoryRepository.
delete_with_record`` — so the one-transaction pairing the unit suite proved against SQLite is
exercised against the real engine too, not bypassed with a hand-rolled ``DELETE``.

The Alembic mechanics (URL rendering, config without an ini file, the throwaway master key, and
``asyncio.to_thread`` around ``command.upgrade``) are copied from
``tests/test_integration/test_migration_chain.py`` rather than imported: the marks evaluate
``_docker_reachable()`` at import time, and that module documents the same copy-not-share reason.
**The copies must move together.**
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncGenerator, Iterator
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from alembic import command
from alembic.config import Config
from sqlalchemy import delete, func, make_url, select
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

import storico.infrastructure.database as _database_package
from storico.config.settings import _reset_settings_cache
from storico.domain.entities.extraction import ExtractionStatus
from storico.domain.entities.story_deletion import StoryDeletion
from storico.domain.entities.user_story import UserStoryStatus
from storico.infrastructure.database.models import (
    ExtractionModel,
    ProjectModel,
    StoryDeletionModel,
    TaskInvalidationModel,
    TaskModel,
    UserModel,
    UserStoryModel,
    WorkspaceModel,
)
from storico.infrastructure.database.repositories import SQLAlchemyUserStoryRepository

# ── the daemon probe, copied per the convention above ─────────────────────────────


def _docker_reachable() -> bool:
    """Best-effort check — is the docker daemon pickable in $DOCKER_HOST?

    Copied from ``test_migration_chain.py`` / ``test_extraction_versioning_schema.py``: the marks
    below evaluate it at import time, so it cannot live in a shared helper module. The copies of
    one probe all need to move together, which is the documented cost.
    """
    host = os.environ.get("DOCKER_HOST", "")
    socket_path = host.removeprefix("unix://") if host.startswith("unix://") else ""
    if not socket_path:
        socket_path = os.path.expanduser("~/.docker/run/docker.sock")
        if not os.path.exists(socket_path):
            socket_path = "/var/run/docker.sock"
    return os.path.exists(socket_path) and os.access(socket_path, os.W_OK)


_needs_docker = pytest.mark.skipif(
    not _docker_reachable(),
    reason="Docker daemon unreachable — these integration tests spawn a Postgres container via testcontainers.",
)

_ALEMBIC_SCRIPT_LOCATION = Path(_database_package.__file__).resolve().parent / "alembic"


def _alembic_config(url: str) -> Config:
    """An Alembic config pointing at the packaged scripts and at ``url``.

    The URL travels through ``config.attributes`` — the channel ``env.py`` reads — never through the
    ``sqlalchemy.url`` option, whose ini placeholder is truthy and would hide a caller's override.
    """
    config = Config()
    config.set_main_option("script_location", str(_ALEMBIC_SCRIPT_LOCATION))
    config.attributes["sqlalchemy_url"] = url
    return config


def _alembic_ready_url(container_url: str) -> str:
    """The container's URL in, the asyncpg URL Alembic receives out.

    ``render_as_string(hide_password=False)`` is load-bearing: ``URL.__str__`` masks the password as
    ``***``, and ``env.py`` puts this value into a configparser option, which needs a string.
    """
    return (
        make_url(container_url)
        .set(drivername="postgresql+asyncpg")
        .render_as_string(hide_password=False)
    )


@pytest.fixture(scope="module")
def pg_url() -> Iterator[str]:
    """One Postgres 16 container for the module, in an Alembic-ready asyncpg URL."""
    from testcontainers.community.postgres import PostgresContainer

    with PostgresContainer("postgres:16-alpine") as pg:
        yield _alembic_ready_url(pg.get_connection_url())


@pytest.fixture(scope="module")
def alembic_config(pg_url: str) -> Config:
    """The config every case here uses — one container, one script location."""
    return _alembic_config(pg_url)


@pytest.fixture(scope="module")
def throwaway_encryption_key() -> Iterator[None]:
    """A per-run master key, so revision ``0024`` can let the chain reach head.

    Generated, never hardcoded: the container database is empty, nothing is encrypted, and the
    value's only job is to let the upgrade run. The settings cache is cleared around it because
    ``Settings.load()`` is ``lru_cache``-wrapped and may already be primed before this fixture.
    """
    from cryptography.fernet import Fernet

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setenv("STORICO_ENCRYPTION_KEY", Fernet.generate_key().decode())
    _reset_settings_cache()
    try:
        yield
    finally:
        monkeypatch.undo()
        _reset_settings_cache()


# ── the migrated database ─────────────────────────────────────────────────────────


@pytest_asyncio.fixture(scope="module", loop_scope="module")
async def migrated_engine(
    pg_url: str,
    alembic_config: Config,
    throwaway_encryption_key: None,
) -> AsyncGenerator[AsyncEngine, None]:
    """Run the whole chain to head once, then yield an engine on that database.

    ``command.upgrade`` goes through ``asyncio.to_thread`` because ``env.py`` ends in
    ``asyncio.run(...)``: calling Alembic from inside a running loop raises.
    """
    await asyncio.to_thread(command.upgrade, alembic_config, "head")

    engine = create_async_engine(pg_url, poolclass=NullPool)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture(scope="module", loop_scope="module")
async def session_factory(migrated_engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """One session factory over the migrated container database."""
    return async_sessionmaker(bind=migrated_engine, class_=AsyncSession, expire_on_commit=False)


# ── seeding helpers ───────────────────────────────────────────────────────────────


async def _seed_project(session: AsyncSession) -> tuple[UUID, UUID, UUID]:
    """Seed the shortest chain a story needs: user → workspace → project.

    Returns ``(owner_id, workspace_id, project_id)``. Every case here inserts stories under this
    project, and both ``extractions`` and ``tasks`` walk a FK back to a story, so an isolated
    ``uuid4()`` as ``user_story_id`` would fail on the FK before it could prove anything. One
    owner per call keeps the unique ``users.email`` and ``workspaces.slug`` constraints out of
    the way.
    """
    now = datetime.now(UTC)
    owner = UserModel(
        email=f"d-{uuid4().hex[:8]}@example.com", name="Deletion Owner", created_at=now
    )
    session.add(owner)
    # The primary key is a column default (`default=uuid7`), so SQLAlchemy materializes
    # ``owner.id`` at INSERT time, not at construction. Reading it before this flush yields
    # ``None`` and every dependent row is born with a null FK — the same trap the sibling
    # integration file documents.
    await session.flush()
    workspace = WorkspaceModel(
        name="Deletion Workspace",
        slug=f"deletion-{uuid4().hex[:8]}",
        owner_id=owner.id,
        created_at=now,
        updated_at=now,
    )
    session.add(workspace)
    await session.flush()
    project = ProjectModel(
        name="Deletion Project",
        workspace_id=workspace.id,
        created_by=owner.id,
        created_at=now,
        updated_at=now,
    )
    session.add(project)
    await session.flush()
    return owner.id, workspace.id, project.id


async def _seed_story(session: AsyncSession, project_id: UUID) -> UUID:
    """One story under ``project_id``, returning its id."""
    now = datetime.now(UTC)
    story = UserStoryModel(
        project_id=project_id,
        actor="developer",
        feature="delete a story cleanly",
        benefit="the audit trail is readable",
        raw_text="As a developer, I want a clean delete, so that the audit trail is readable.",
        status=UserStoryStatus.EXTRACTED,
        created_at=now,
        updated_at=now,
    )
    session.add(story)
    await session.flush()
    return story.id


def _extraction_row(story_id: UUID, version: int) -> ExtractionModel:
    """A complete ``0028`` extraction row, with the four versioning columns filled in."""
    return ExtractionModel(
        id=uuid4(),
        user_story_id=story_id,
        version_number=version,
        model_used="llama3.2",
        provider="ollama",
        temperature=0.1,
        status=ExtractionStatus.COMPLETED,
        user_story_status=UserStoryStatus.EXTRACTED,
        raw_response="1. summary: Seed\ndescription: Pinned.",
        created_at=datetime.now(UTC),
    )


def _task_row(story_id: UUID, extraction_id: UUID, title: str) -> TaskModel:
    now = datetime.now(UTC)
    return TaskModel(
        id=uuid4(),
        user_story_id=story_id,
        extraction_id=extraction_id,
        title=title,
        description="Seeded for the deletion record.",
        status="backlog",
        priority="medium",
        created_at=now,
        updated_at=now,
    )


def _record_for(
    story: UserStoryModel,
    project: ProjectModel,
    *,
    version_numbers: list[int],
    deleted_by: UUID | None,
) -> StoryDeletion:
    """The frozen ``StoryDeletion`` the production service would hand to ``delete_with_record``.

    Built from the live rows the way ``StoryDeletionService`` builds it — identity as values,
    version numbers ascending — so the repository's one-transaction pairing is exercised
    end-to-end rather than simulated with a hand-written INSERT.
    """
    return StoryDeletion(
        story_id=story.id,
        project_id=project.id,
        workspace_id=project.workspace_id,
        actor=story.actor,
        feature=story.feature,
        benefit=story.benefit,
        version_numbers=version_numbers,
        deleted_by=deleted_by,
    )


# ── 4.16 — the deletion record invariants Postgres is the only witness of ─────────


@pytest.mark.integration
@_needs_docker
@pytest.mark.asyncio(loop_scope="module")
async def test_the_record_survives_the_story_cascade(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Deleting a story with versions and tasks leaves its ``story_deletions`` row standing.

    The record survives because it holds the story's identity **as values** and carries no
    foreign key to ``stories`` — a record that referenced the story would be destroyed by the
    very delete it records. The deletion goes through the real ``delete_with_record``, so the
    cascade (story → extractions, story → tasks) and the record's INSERT share one transaction,
    exactly as production runs them.
    """
    async with session_factory() as session:
        _, _, project_id = await _seed_project(session)
        story_id = await _seed_story(session, project_id)
        story = await session.get(UserStoryModel, story_id)
        project = await session.get(ProjectModel, project_id)
        assert story is not None and project is not None

        run_one = _extraction_row(story_id, 1)
        session.add(run_one)
        await session.flush()
        session.add(_task_row(story_id, run_one.id, "Task of version one"))
        run_two = _extraction_row(story_id, 2)
        session.add(run_two)
        await session.flush()
        session.add(_task_row(story_id, run_two.id, "Task of version two"))
        await session.commit()

        await SQLAlchemyUserStoryRepository(session).delete_with_record(
            story_id,
            _record_for(story, project, version_numbers=[1, 2], deleted_by=None),
        )

    async with session_factory() as verify:
        record = (
            await verify.execute(
                select(StoryDeletionModel).where(StoryDeletionModel.story_id == story_id)
            )
        ).scalar_one()  # exactly one: one deletion, one record

        assert record.story_id == story_id, "the story id did not survive as a value"
        assert record.project_id == project_id, "the project id did not survive as a value"
        assert record.workspace_id == project.workspace_id, (
            "the workspace id did not survive as a value"
        )
        assert record.actor == "developer", "the actor did not survive as a value"
        assert record.feature == "delete a story cleanly", "the feature did not survive as a value"
        assert record.benefit == "the audit trail is readable", (
            "the benefit did not survive as a value"
        )
        assert record.version_numbers == [1, 2], (
            "the destroyed version numbers did not survive ascending"
        )
        assert record.deleted_by is None, "an ownerless record grew an actor reference"

        # And the story itself is really gone — the record records a deletion that happened.
        assert await verify.get(UserStoryModel, story_id) is None


@pytest.mark.integration
@_needs_docker
@pytest.mark.asyncio(loop_scope="module")
async def test_deleting_the_actor_nulls_deleted_by_only(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Deleting the user who performed the deletion nulls ``deleted_by`` and nothing else.

    ``fk_story_deletions_deleted_by_users`` is the table's **only** foreign key, declared
    ``ON DELETE SET NULL``: an account deletion may not erase the audit trail, only the actor
    reference on it. The verification re-reads the row in a fresh session rather than trusting
    the identity map, because the SET NULL is a database-side update no session performs.

    The deleted user is a **dedicated** actor row, not the workspace's owner: the owner is
    referenced by ``workspaces.owner_id`` with ``ON DELETE CASCADE`` (0007), so deleting that
    user would cascade the workspace, the project and the story away — a different scenario
    than the one this case pins. The record only ever references its deleter through
    ``deleted_by``, so a deleter with no other rows isolates exactly the FK under test.
    """
    async with session_factory() as session:
        owner_id, _, project_id = await _seed_project(session)
        story_id = await _seed_story(session, project_id)
        story = await session.get(UserStoryModel, story_id)
        project = await session.get(ProjectModel, project_id)
        assert story is not None and project is not None

        deleter = UserModel(
            email=f"d-{uuid4().hex[:8]}@example.com",
            name="Dedicated Deleter",
            created_at=datetime.now(UTC),
        )
        session.add(deleter)
        await session.flush()

        await SQLAlchemyUserStoryRepository(session).delete_with_record(
            story_id,
            _record_for(story, project, version_numbers=[1], deleted_by=deleter.id),
        )

        # Snapshot the row as it stood before the account deletion, column by column.
        before = (
            await session.execute(
                select(StoryDeletionModel).where(StoryDeletionModel.story_id == story_id)
            )
        ).scalar_one()
        snapshot = {
            "story_id": before.story_id,
            "project_id": before.project_id,
            "workspace_id": before.workspace_id,
            "actor": before.actor,
            "feature": before.feature,
            "benefit": before.benefit,
            "version_numbers": list(before.version_numbers),
            "deleted_by": before.deleted_by,
            "deleted_at": before.deleted_at,
        }
        assert snapshot["deleted_by"] == deleter.id, "the fixture did not record the deleter"
        assert snapshot["story_id"] == story_id

        await session.execute(delete(UserModel).where(UserModel.id == deleter.id))
        await session.commit()  # no refusal: SET NULL, not RESTRICT

    async with session_factory() as verify:
        after = (
            await verify.execute(
                select(StoryDeletionModel).where(StoryDeletionModel.story_id == story_id)
            )
        ).scalar_one()

        assert after.deleted_by is None, "deleted_by survived the user it pointed at"
        for column, value in snapshot.items():
            if column == "deleted_by":
                continue
            assert getattr(after, column) == value, (
                f"the account delete touched {column}: {getattr(after, column)!r} != {value!r}"
            )
        assert owner_id  # the workspace owner is untouched by this scenario by construction


@pytest.mark.integration
@_needs_docker
@pytest.mark.asyncio(loop_scope="module")
async def test_the_story_cascade_takes_its_versions_tasks_and_marks_and_nothing_else(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """The story delete cascades its extractions, tasks and marks away — and nothing else does.

    The marks hang off tasks, so they reach the delete through **two** cascades
    (story → tasks → marks, and story → extractions → tasks → marks): the row counts are
    asserted rather than a single "it disappeared". A second story in the *same workspace*
    keeps its own rows — proof of the cascade's scope, not just its fire.
    """
    async with session_factory() as session:
        owner_id, _, project_id = await _seed_project(session)
        doomed = await _seed_story(session, project_id)
        kept = await _seed_story(session, project_id)

        for story_id in (doomed, kept):
            run = _extraction_row(story_id, 1)
            session.add(run)
            await session.flush()
            task = _task_row(story_id, run.id, f"Task of {story_id}")
            session.add(task)
            await session.flush()
            session.add(
                TaskInvalidationModel(
                    task_id=task.id,
                    reason="Seeded mark",
                    marked_by=owner_id,
                    marked_at=datetime.now(UTC),
                )
            )
            await session.flush()
        await session.commit()

        story = await session.get(UserStoryModel, doomed)
        project = await session.get(ProjectModel, project_id)
        assert story is not None and project is not None
        await SQLAlchemyUserStoryRepository(session).delete_with_record(
            doomed,
            _record_for(story, project, version_numbers=[1], deleted_by=None),
        )

    async def _count(model: type, story_id: UUID) -> int:
        async with session_factory() as session:
            return (
                await session.execute(
                    select(func.count()).select_from(model).where(model.user_story_id == story_id)
                )
            ).scalar_one()

    assert await _count(ExtractionModel, doomed) == 0
    assert await _count(TaskModel, doomed) == 0
    assert await _count(ExtractionModel, kept) == 1, "the cascade reached a neighbouring story"
    assert await _count(TaskModel, kept) == 1, "the cascade reached a neighbouring story's tasks"

    async with session_factory() as session:
        kept_marks = (
            await session.execute(
                select(func.count())
                .select_from(TaskInvalidationModel)
                .join(TaskModel, TaskModel.id == TaskInvalidationModel.task_id)
                .where(TaskModel.user_story_id == kept)
            )
        ).scalar_one()
        assert kept_marks == 1, "the cascade reached a neighbouring story's marks"

        records = (
            (
                await session.execute(
                    select(StoryDeletionModel).where(StoryDeletionModel.story_id == doomed)
                )
            )
            .scalars()
            .all()
        )
        assert len(records) == 1, "the record did not survive the multi-cascade delete"
        assert records[0].version_numbers == [1]
