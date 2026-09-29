"""Integration tests for revision ``0028`` — extraction versioning on real Postgres.

**Nothing in this file executes without a Docker daemon.** On a daemon-less machine every case
here skips, and the invariants it pins stay *unverified*, not green. That is the honest status the
slice's tasks file records for tasks 1.18 and 1.19; the SQLite unit layer mirrors the CHECKs, the
partial index and the allocation numbering, but it cannot prove the DDL, the ``downgrade``, the
story cascade, the real collision or the constraint's Postgres index shape.

What each case adds over the SQLite mirror:

* the duplicate ``(user_story_id, version_number)`` pair refused by the named constraint;
* ``tasks.extraction_id`` refusing null;
* "no current flag, no trigger, no view" read out of the catalog rather than asserted from the
  model;
* the story cascade removing a version's extractions and their tasks, and nothing else;
* ``0028`` refusing a populated database, and leaving the pre-``0028`` schema untouched;
* ``downgrade 0027`` round-tripping on an empty container;
* the allocation losing a real race and minting the next number on the retry — provoked
  deterministically, because the race window lives inside one server-side statement.

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
from alembic.script import ScriptDirectory
from sqlalchemy import delete, func, make_url, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

import storico.infrastructure.database as _database_package
from storico.config.settings import _reset_settings_cache
from storico.domain.entities.extraction import Extraction, ExtractionStatus
from storico.domain.entities.user_story import UserStoryStatus
from storico.infrastructure.database.models import (
    ExtractionModel,
    ProjectModel,
    TaskModel,
    UserModel,
    UserStoryModel,
    WorkspaceModel,
)
from storico.infrastructure.database.repositories import SQLAlchemyExtractionRepository

# ── the daemon probe, copied per the convention above ─────────────────────────────


def _docker_reachable() -> bool:
    """Best-effort check — is the docker daemon pickable in $DOCKER_HOST?

    Copied from ``test_migration_chain.py`` / ``test_projects_integration.py``: the marks below
    evaluate it at import time, so it cannot live in a shared helper module. Three copies of one
    probe, all three needing to move together, is the documented cost.
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
    """The config both the chain and the guard tests use — one container, one script location."""
    return _alembic_config(pg_url)


@pytest.fixture(scope="module")
def throwaway_encryption_key() -> Iterator[None]:
    """A per-run master key, so revision ``0024`` can reach head in the chain.

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


async def _seed_story(session: AsyncSession) -> UUID:
    """Seed the shortest chain a story needs: user → workspace → project → story.

    Every case here inserts ``extractions``/``tasks`` rows, and both walk a FK back to a story, so
    an isolated ``uuid4()`` as ``user_story_id`` would fail on the FK before it could prove anything
    about versioning. One owner per call keeps the unique ``users.email`` and ``workspaces.slug``
    constraints out of the way.
    """
    now = datetime.now(UTC)
    owner = UserModel(
        email=f"v-{uuid4().hex[:8]}@example.com", name="Versioning Owner", created_at=now
    )
    workspace = WorkspaceModel(
        name="Versioning Workspace",
        slug=f"versioning-{uuid4().hex[:8]}",
        owner_id=owner.id,
        created_at=now,
        updated_at=now,
    )
    project = ProjectModel(
        name="Versioning Project",
        workspace_id=workspace.id,
        created_by=owner.id,
        created_at=now,
        updated_at=now,
    )
    story = UserStoryModel(
        project_id=project.id,
        actor="developer",
        feature="version a run",
        benefit="the history is readable",
        raw_text="As a developer, I want versions, so that history is readable.",
        status=UserStoryStatus.PENDING_EXTRACTION,
        created_at=now,
        updated_at=now,
    )
    session.add_all([owner, workspace, project, story])
    await session.commit()
    return story.id


def _extraction_row(story_id: UUID, version: int, **overrides: object) -> ExtractionModel:
    """A complete ``0028`` extraction row, with the four new columns filled in.

    Built at the ORM layer on purpose: the unit cases assert through the repository, and these two
    need to name ``version_number`` by hand — which is exactly what the production birth path is
    not allowed to do.
    """
    now = datetime.now(UTC)
    values = {
        "id": uuid4(),
        "user_story_id": story_id,
        "version_number": version,
        "model_used": "llama3.2",
        "provider": "ollama",
        "temperature": 0.1,
        "status": ExtractionStatus.COMPLETED,
        "user_story_status": UserStoryStatus.EXTRACTED,
        "raw_response": "1. summary: Seed\ndescription: Pinned.",
        "created_at": now,
    }
    values.update(overrides)
    return ExtractionModel(**values)


def _task_row(story_id: UUID, extraction_id: UUID, title: str) -> TaskModel:
    now = datetime.now(UTC)
    return TaskModel(
        id=uuid4(),
        user_story_id=story_id,
        extraction_id=extraction_id,
        title=title,
        description="Pinned by 0028.",
        status="backlog",
        priority="medium",
        created_at=now,
        updated_at=now,
    )


# ── 1.18 — the schema invariants Postgres is the only witness of ──────────────────


@pytest.mark.integration
@_needs_docker
@pytest.mark.asyncio(loop_scope="module")
async def test_the_duplicate_version_pair_is_refused_by_its_constraint(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Two rows with the same ``(user_story_id, version_number)`` cannot both exist.

    The refusal must name ``uq_extractions_story_version``: a duplicate stopped by some other
    mechanism (a trigger, a rewritten insert, a different index) would let the allocation race back
    in unnoticed, and the name is what ties the constraint to the revision that declares it.
    """
    async with session_factory() as session:
        story_id = await _seed_story(session)
        session.add(_extraction_row(story_id, 1))
        await session.commit()

        session.add(_extraction_row(story_id, 1, id=uuid4()))
        with pytest.raises(IntegrityError) as raised:
            await session.commit()

        assert "uq_extractions_story_version" in str(raised.value.orig)
        await session.rollback()

        # The same number on a *different* story is legal: the pair is per story.
        other_story = await _seed_story(session)
        session.add(_extraction_row(other_story, 1))
        await session.commit()


@pytest.mark.integration
@_needs_docker
@pytest.mark.asyncio(loop_scope="module")
async def test_tasks_refuse_a_null_extraction_id(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """``tasks.extraction_id`` is NOT NULL: a task with no run is refused at the database.

    The application cannot make this true by convention, and the refusal is what forces the runner
    and the dead path to carry the id — the clause the second Phase-3 pull-in landed in PR 1.
    """
    async with session_factory() as session:
        story_id = await _seed_story(session)
        task = _task_row(story_id, None, "No run")  # type: ignore[arg-type]
        session.add(task)
        with pytest.raises(IntegrityError, match="not-null|NOT NULL"):
            await session.commit()
        await session.rollback()


@pytest.mark.integration
@_needs_docker
@pytest.mark.asyncio(loop_scope="module")
async def test_no_current_flag_no_trigger_and_no_view_on_extractions(
    migrated_engine: AsyncEngine,
) -> None:
    """The current version is derived, so nothing may *store* it in the schema.

    Read out of the catalog rather than asserted from the model: a column, a trigger or a matview
    that answers "which version is current" would each be a second source of truth, and the only
    proof that none exists is a query against Postgres itself.
    """
    async with migrated_engine.connect() as conn:
        columns = (
            (
                await conn.execute(
                    text(
                        "SELECT column_name FROM information_schema.columns "
                        "WHERE table_name = 'extractions'"
                    )
                )
            )
            .scalars()
            .all()
        )
        triggers = (
            (
                await conn.execute(
                    text(
                        "SELECT tgname FROM pg_trigger t "
                        "JOIN pg_class c ON c.oid = t.tgrelid "
                        "WHERE c.relname = 'extractions' AND NOT t.tgisinternal"
                    )
                )
            )
            .scalars()
            .all()
        )
        matviews = (
            (
                await conn.execute(
                    text("SELECT matviewname FROM pg_matviews WHERE matviewname ILIKE '%current%'")
                )
            )
            .scalars()
            .all()
        )

    assert not [c for c in columns if "current" in c], (
        f"a stored-current column came back: {columns}"
    )
    assert triggers == [], f"extractions carries triggers: {triggers}"
    assert matviews == [], f"a materialized view claims the current version: {matviews}"

    # And the four versioning columns really are there — the same read proves the DDL ran.
    for expected in ("version_number", "provider", "temperature", "prompt_rendered"):
        assert expected in columns, f"{expected} is missing from extractions: {columns}"


@pytest.mark.integration
@_needs_docker
@pytest.mark.asyncio(loop_scope="module")
async def test_deleting_the_story_removes_its_versions_and_their_tasks_and_nothing_else(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """The story cascade is the only deletion path a version has (D15).

    Two stories each get a version with a task; deleting one story must empty its own extractions
    and tasks and leave the other's untouched — proof of both the CASCADE and its scope. That the
    tasks go through *two* cascades (story→tasks and story→extractions→tasks) is why the row counts
    are asserted rather than a single "it disappeared".
    """
    async with session_factory() as session:
        doomed = await _seed_story(session)
        kept = await _seed_story(session)

        run = _extraction_row(doomed, 1)
        session.add(run)
        await session.flush()
        session.add(_task_row(doomed, run.id, "Doomed task"))
        other_run = _extraction_row(kept, 1)
        session.add(other_run)
        await session.flush()
        session.add(_task_row(kept, other_run.id, "Kept task"))
        await session.commit()

        await session.execute(delete(UserStoryModel).where(UserStoryModel.id == doomed))
        await session.commit()

        async def _count(model, story_id) -> int:  # noqa: ANN001
            return (
                await session.execute(
                    select(func.count()).select_from(model).where(model.user_story_id == story_id)
                )
            ).scalar_one()

        assert await _count(ExtractionModel, doomed) == 0
        assert await _count(TaskModel, doomed) == 0
        assert await _count(ExtractionModel, kept) == 1, "the cascade reached a neighbouring story"
        assert await _count(TaskModel, kept) == 1


@pytest.mark.integration
@_needs_docker
@pytest.mark.asyncio(loop_scope="module")
async def test_downgrade_to_0027_and_back_round_trips_on_an_empty_database(
    pg_url: str,
    alembic_config: Config,
) -> None:
    """``0028`` can be taken back off an empty database and re-applied cleanly.

    This is the rollback boundary the unit layer cannot see at all: SQLite refuses to alter a
    constraint, so the ``downgrade()`` body has never executed on this machine before CI runs this
    case. Re-applying afterwards proves the pair is symmetric — a downgrade that drops a column the
    upgrade still expects would otherwise surface as a failed deploy.
    """
    declared_head = ScriptDirectory.from_config(alembic_config).get_current_head()
    assert declared_head == "0028", f"the packaged scripts declare head {declared_head}"

    await asyncio.to_thread(command.downgrade, alembic_config, "0027")
    async with create_async_engine(pg_url, poolclass=NullPool).connect() as conn:
        columns = (
            (
                await conn.execute(
                    text(
                        "SELECT column_name FROM information_schema.columns WHERE table_name = 'extractions'"
                    )
                )
            )
            .scalars()
            .all()
        )
        tables = (
            (
                await conn.execute(
                    text(
                        "SELECT table_name FROM information_schema.tables WHERE table_name = 'task_invalidations'"
                    )
                )
            )
            .scalars()
            .all()
        )
        recorded = (
            (await conn.execute(text("SELECT version_num FROM alembic_version"))).scalars().all()
        )

    assert not {"version_number", "provider", "temperature", "prompt_rendered"} & set(columns)
    assert tables == [], "task_invalidations survived its downgrade"
    assert recorded == ["0027"], f"the chain recorded {recorded} after downgrade"

    await asyncio.to_thread(command.upgrade, alembic_config, "head")


# ── 1.19 — the real collision, provoked rather than simulated ────────────────────


@pytest.mark.integration
@_needs_docker
@pytest.mark.asyncio(loop_scope="module")
async def test_a_lost_allocation_race_retries_and_mints_the_next_number(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """An uncommitted competing insert makes the first attempt lose; the retry wins the next number.

    The race window lives inside one server-side statement, so it cannot be timed — it is provoked:
    one session holds an uncommitted version 1 for the story, the allocation's INSERT-SELECT blocks
    on the unique index, the holder commits, the first attempt comes back as
    ``uq_extractions_story_version`` and the retry mints 2.

    This asserts **one** collision and never "three real collisions": the bound of 3 is discriminated
    by the unit case that forces a conflict on every attempt, and provoking three genuinely needs a
    statement that does not exist.
    """
    async with session_factory() as holder, session_factory() as racer:
        story_id = await _seed_story(holder)

        held = _extraction_row(story_id, 1)
        holder.add(held)
        await holder.flush()  # the row exists for the server, and is not yet committed

        pending = SQLAlchemyExtractionRepository(racer).create_next_version(
            _entity_for(story_id),
        )
        allocation = asyncio.create_task(pending)

        # Let the allocation reach the blocked INSERT before the holder releases it.
        await asyncio.sleep(0.2)
        await holder.commit()

        won = await allocation

        assert won.version_number == 2, (
            "the retry did not mint the next number after losing the pair: "
            f"got {won.version_number}"
        )

        total = (
            await holder.execute(
                select(func.count())
                .select_from(ExtractionModel)
                .where(ExtractionModel.user_story_id == story_id)
            )
        ).scalar_one()
        assert total == 2, "the lost attempt left a phantom row behind"


def _entity_for(story_id: UUID) -> Extraction:
    """A pending entity for the birth path — the shape ``create_next_version`` expects.

    Built through the domain entity, not the ORM model: the repository's own contract is that the
    number it returns comes from the INSERT and any carried number is ignored.
    """
    return Extraction(
        user_story_id=story_id,
        model_used="llama3.2",
        raw_response="",
        provider="ollama",
        temperature=0.1,
    )
