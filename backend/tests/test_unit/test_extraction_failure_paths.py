"""Tests for the extraction task's failure paths — the two helpers that had none.

``_mark_failed`` and ``_mark_extraction_failed`` are the paths that run when an extraction
breaks, which are the least likely to be exercised by hand and the easiest to leave
uncovered. They were: adding ``completed_at`` to both of them produced an
``UnboundLocalError`` that the whole 654-test suite passed straight through, because a
function-local ``from datetime import ...`` further down made ``datetime`` a local name for
the entire function and the new line came before it. Nothing reached these helpers, so
nothing noticed.

These tests reach them, and the recovery sweep with them — all three are terminal paths.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from sqlalchemy import update
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

from storico.domain.entities import Extraction
from storico.domain.entities.extraction import ExtractionStatus
from storico.domain.entities.user_story import UserStoryStatus
from storico.infrastructure.database.models import Base
from storico.infrastructure.database.repositories import (
    SQLAlchemyExtractionRepository,
    SQLAlchemyUserStoryRepository,
)
from storico.infrastructure.tasks import extraction_task


@pytest_asyncio.fixture
async def engine() -> AsyncGenerator[AsyncEngine, None]:
    """An in-memory database shared by every session opened against it.

    ``StaticPool`` is what makes the sharing true: ``_mark_extraction_failed`` opens its own
    session on purpose — the caller's may be in a broken state — so without a single shared
    connection the second session would see an empty database and quietly do nothing.
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


async def _store_pending(engine: AsyncEngine, story_id: UUID) -> UUID:
    """Store a ``pending`` extraction and return its id, the way a started job leaves it."""
    async with _factory(engine)() as session:
        pending = Extraction(
            user_story_id=story_id,
            model_used="llama3.2",
            raw_response="",
            status=ExtractionStatus.PENDING,
            user_story_status=UserStoryStatus.PENDING_EXTRACTION,
        )
        await SQLAlchemyExtractionRepository(session).save(pending)
        return pending.id


async def _reload(engine: AsyncEngine, extraction_id: UUID) -> Extraction:
    async with _factory(engine)() as session:
        found = await SQLAlchemyExtractionRepository(session).find_by_id(extraction_id)
        assert found is not None
        return found


async def _age_the_row(engine: AsyncEngine, extraction_id: UUID) -> None:
    """Backdate ``created_at`` so the sweep considers the extraction abandoned."""
    table = Base.metadata.tables["extractions"]
    async with engine.begin() as conn:
        await conn.execute(
            update(table)
            .where(table.c.id == extraction_id)
            .values(created_at=datetime(2020, 1, 1, tzinfo=UTC))
        )


@pytest.mark.asyncio
async def test_mark_failed_records_when_the_job_ended(engine: AsyncEngine) -> None:
    """The in-request failure path: a failed extraction gets an end time, not only a reason."""
    extraction_id = await _store_pending(engine, uuid4())
    assert (await _reload(engine, extraction_id)).completed_at is None
    before = datetime.now(UTC).replace(tzinfo=None)

    async with _factory(engine)() as session:
        await extraction_task._mark_failed(
            SQLAlchemyExtractionRepository(session),
            SQLAlchemyUserStoryRepository(session),
            extraction_id,
            "the model refused",
        )

    failed = await _reload(engine, extraction_id)
    assert failed.status is ExtractionStatus.FAILED
    assert failed.error_info == "the model refused"
    assert failed.completed_at is not None
    # Not before the job was marked failed, and not in the future.
    assert failed.completed_at.replace(tzinfo=None) >= before


@pytest.mark.asyncio
async def test_the_standalone_failure_helper_records_it_too(
    engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The out-of-band path: it opens its own session, so it has its own way to be wrong."""
    extraction_id = await _store_pending(engine, uuid4())
    # The helper builds its session from the module's ``get_engine``; point it at the scratch one.
    monkeypatch.setattr(extraction_task, "get_engine", lambda: engine)

    await extraction_task._mark_extraction_failed(extraction_id, "the worker died")

    failed = await _reload(engine, extraction_id)
    assert failed.status is ExtractionStatus.FAILED
    assert failed.error_info == "the worker died"
    assert failed.completed_at is not None


@pytest.mark.asyncio
async def test_the_recovery_sweep_records_an_end_time(
    engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A job abandoned by a crash is terminal too, and it ends when it was swept."""
    extraction_id = await _store_pending(engine, uuid4())
    await _age_the_row(engine, extraction_id)
    monkeypatch.setattr(extraction_task, "get_engine", lambda: engine)

    await extraction_task.recover_stuck_extractions(max_age_minutes=1)

    swept = await _reload(engine, extraction_id)
    assert swept.status is ExtractionStatus.FAILED
    assert swept.error_info is not None
    assert swept.completed_at is not None


@pytest.mark.asyncio
async def test_a_pending_job_is_left_alone_by_every_failure_path(
    engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The other half of the invariant: none of these paths writes an end time to a job still
    running, and a sweep with nothing stale changes nothing."""
    fresh_id = await _store_pending(engine, uuid4())
    monkeypatch.setattr(extraction_task, "get_engine", lambda: engine)

    # Not aged, so the sweep must leave it alone.
    await extraction_task.recover_stuck_extractions(max_age_minutes=5)

    fresh = await _reload(engine, fresh_id)
    assert fresh.status is ExtractionStatus.PENDING
    assert fresh.completed_at is None
