"""Tests for the Trello export startup sweep — ``recover_stuck_trello_exports``.

The sweep is the mechanism the shipped runner wrongly claimed to exist: a row
stranded at ``pending`` or ``running`` by a crash or a cancelled task is not an
honest record of work in progress, it is a member polling forever. These tests
mirror ``test_extraction_failure_paths.py``'s sweep cases — a stale row goes
terminal, a fresh one is left alone — with the one deviation the job's contract
forces: ``running`` is swept too, because a cancelled task leaves the row there.

The rows are backdated by constructing them with an old ``created_at`` — the
entity takes one, so no raw SQL update is needed.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

from storico.api.error_codes import TRELLO_EXPORT_INTERRUPTED
from storico.domain.entities.trello_export import TrelloExport, TrelloExportStatus
from storico.infrastructure.database.models import Base
from storico.infrastructure.database.repositories.trello_export_repository import (
    SQLAlchemyTrelloExportRepository,
)
from storico.infrastructure.tasks import trello_export_task


@pytest_asyncio.fixture
async def engine() -> AsyncGenerator[AsyncEngine, None]:
    """An in-memory database shared by every session opened against it.

    ``StaticPool`` is what makes the sharing true: the sweep opens its own
    session on the process engine — the caller's session is long gone by the
    time startup recovery runs — so without a single shared connection the
    sweep's session would see an empty database and quietly do nothing.
    """
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


def _factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)


async def _store_job(
    engine: AsyncEngine,
    status: TrelloExportStatus,
    *,
    created_at: datetime | None = None,
    **kwargs,
) -> UUID:
    """Store a job row in *status* and return its id."""
    async with _factory(engine)() as session:
        saved = await SQLAlchemyTrelloExportRepository(session).save(
            TrelloExport(
                workspace_id=uuid4(),
                status=status,
                created_at=created_at or datetime.now(UTC),
                **kwargs,
            )
        )
        return saved.id


async def _reload(engine: AsyncEngine, job_id: UUID) -> TrelloExport:
    async with _factory(engine)() as session:
        found = await SQLAlchemyTrelloExportRepository(session).find_by_id(job_id)
        assert found is not None
        return found


_OLD = datetime(2020, 1, 1, tzinfo=UTC)


@pytest.mark.asyncio
async def test_the_sweep_marks_a_stale_pending_job_failed(
    engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A pending row abandoned by a crash becomes failed, with an end time."""
    job_id = await _store_job(engine, TrelloExportStatus.PENDING, created_at=_OLD)
    monkeypatch.setattr(trello_export_task, "get_engine", lambda: engine)

    await trello_export_task.recover_stuck_trello_exports(max_age_minutes=5)

    swept = await _reload(engine, job_id)
    assert swept.status is TrelloExportStatus.FAILED
    assert swept.error_code == TRELLO_EXPORT_INTERRUPTED
    assert swept.completed_at is not None


@pytest.mark.asyncio
async def test_the_sweep_marks_a_stale_running_job_failed(
    engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``running`` is the state a cancelled task strands the row in — it is
    swept too, which the extraction's sweep (pending only) does not do."""
    job_id = await _store_job(engine, TrelloExportStatus.RUNNING, created_at=_OLD)
    monkeypatch.setattr(trello_export_task, "get_engine", lambda: engine)

    await trello_export_task.recover_stuck_trello_exports(max_age_minutes=5)

    swept = await _reload(engine, job_id)
    assert swept.status is TrelloExportStatus.FAILED
    assert swept.error_code == TRELLO_EXPORT_INTERRUPTED


@pytest.mark.asyncio
async def test_the_sweep_leaves_a_fresh_job_alone(
    engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The part that is easy to get wrong: a row the current process just
    created — pending or running — is nobody's orphan, and the sweep must
    not terminate it."""
    fresh_pending = await _store_job(engine, TrelloExportStatus.PENDING)
    fresh_running = await _store_job(engine, TrelloExportStatus.RUNNING)
    monkeypatch.setattr(trello_export_task, "get_engine", lambda: engine)

    await trello_export_task.recover_stuck_trello_exports(max_age_minutes=5)

    for job_id in (fresh_pending, fresh_running):
        untouched = await _reload(engine, job_id)
        assert untouched.status is not TrelloExportStatus.FAILED
        assert untouched.completed_at is None
        assert untouched.error_code is None


@pytest.mark.asyncio
async def test_the_sweep_keeps_the_board_identity_it_finds(
    engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A running row that already built its board keeps that board through the
    sweep — the same rule every other terminal path follows."""
    job_id = await _store_job(
        engine,
        TrelloExportStatus.RUNNING,
        created_at=_OLD,
        board_id="board-1",
        board_url="https://trello.com/b/board-1",
    )
    monkeypatch.setattr(trello_export_task, "get_engine", lambda: engine)

    await trello_export_task.recover_stuck_trello_exports(max_age_minutes=5)

    swept = await _reload(engine, job_id)
    assert swept.status is TrelloExportStatus.FAILED
    assert swept.board_id == "board-1"
    assert swept.board_url == "https://trello.com/b/board-1"
