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
from storico.domain.entities.exceptions import LLMError
from storico.domain.entities.extraction import ExtractionStatus
from storico.domain.ports import LLMConfig, LLMPort
from storico.infrastructure.database.models import Base
from storico.infrastructure.database.repositories import (
    SQLAlchemyExtractionRepository,
    SQLAlchemyUserStoryRepository,
)
from storico.infrastructure.tasks import extraction_task
from tests._helpers import seed_extraction


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
    """Store a ``pending`` extraction and return its id, the way a started job leaves it.

    The seed goes through the birth path (``create_next_version``, via the shared
    builder): from ``0028`` on a pending row is born with its version number, and
    ``save()`` cannot create one.
    """
    async with _factory(engine)() as session:
        pending = await seed_extraction(session, story_id)
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


# ── Render-time snapshot (WU3 task 3.1, tranche 3a) ───────────────


def _make_the_vector_store_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    """Turn the RAG dependency off before the background task builds it.

    ``_run_extraction`` builds the embedding port and the ``QdrantAdapter`` inside one
    ``try``, and any failure there takes the production "vector store unavailable"
    branch (``vector_store=None``) — the same branch a deployment with no vector store
    configured runs. The tests here are about the extraction row, not retrieval.
    """

    def _unavailable(_settings: object) -> None:
        raise RuntimeError("vector store deliberately unavailable for this test")

    monkeypatch.setattr(extraction_task, "get_embedding_port", _unavailable)


async def _seed_pending(engine: AsyncEngine, story_id: UUID, **kwargs: object) -> Extraction:
    """Seed a ``pending`` extraction the way the route's birth path leaves it."""
    async with _factory(engine)() as session:
        return await seed_extraction(session, story_id, model_used="llama3.2", **kwargs)  # type: ignore[arg-type]


class _ObservingLLM(LLMPort):
    """Record the row the run holds at the instant the provider is asked, then refuse.

    The observation goes through the repository (``find_by_id``) on a fresh session,
    never by patching the repo: the assertion is about what the row holds.
    """

    def __init__(self, engine: AsyncEngine, extraction_id: UUID) -> None:
        self._engine = engine
        self._extraction_id = extraction_id
        self.seen_prompt: str | None = None
        self.seen_system: str | None = None
        self.observed: Extraction | None = None

    async def _observe(self, prompt: str, system_prompt: str | None) -> None:
        self.seen_prompt = prompt
        self.seen_system = system_prompt
        async with _factory(self._engine)() as session:
            self.observed = await SQLAlchemyExtractionRepository(session).find_by_id(
                self._extraction_id
            )

    async def generate(
        self,
        prompt: str,  # noqa: ARG002
        config: LLMConfig,  # noqa: ARG002
        system_prompt: str | None = None,  # noqa: ARG002
    ) -> str:
        await self._observe(prompt, system_prompt)
        raise LLMError("the provider refused after render")


class _ObservingAnsweringLLM(_ObservingLLM):
    """Same observation, then a valid answer so the run completes."""

    async def generate(
        self,
        prompt: str,
        config: LLMConfig,  # noqa: ARG002
        system_prompt: str | None = None,
    ) -> str:
        await self._observe(prompt, system_prompt)
        return "1. summary: Set up the schema\ndescription: Create the tables.\n"


class TestRenderTimeSnapshot:
    """The rendered prompt becomes a real snapshot column the moment it is rendered.

    Three cases from task 3.1: a run that reaches render freezes the prompt before the
    provider is contacted; a run that dies before render keeps ``prompt_rendered`` null;
    and the regression — after a failed run and after a completed run, every snapshot
    column still holds its birth/render value (the terminal writes must not re-null it).
    """

    @pytest.mark.asyncio
    async def test_a_run_that_reaches_render_freezes_the_prompt_before_the_provider_is_asked(
        self, test_engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch, seed_workspace
    ) -> None:
        seeded = await seed_workspace(member=False)
        pending = await _seed_pending(
            test_engine, seeded.story_id, prompt_config={"validate": False}
        )
        llm = _ObservingLLM(test_engine, pending.id)

        monkeypatch.setattr(extraction_task, "get_engine", lambda: test_engine)
        monkeypatch.setattr(extraction_task, "OllamaAdapter", lambda **_: llm)
        _make_the_vector_store_unavailable(monkeypatch)

        await extraction_task.run_background_extraction(
            extraction_id=pending.id,
            story_id=seeded.story_id,
            workspace_id=seeded.workspace_id,
            model="llama3.2",
            max_retries=0,
        )

        observed = llm.observed
        assert observed is not None, "the adapter was never called, so render was never reached"
        expected = (llm.seen_system or "") + "\n\n" + (llm.seen_prompt or "")
        assert observed.prompt_rendered == expected
        assert observed.prompt_config is not None
        assert observed.prompt_config.get("system_prompt") == llm.seen_system
        # At the instant the provider is asked, the run has no output yet.
        assert observed.raw_response == ""
        assert observed.confidence_score is None
        assert "usage" not in observed.prompt_config

    @pytest.mark.asyncio
    async def test_a_run_that_dies_before_render_keeps_prompt_rendered_null(
        self, test_engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch, seed_workspace
    ) -> None:
        seeded = await seed_workspace(member=False)
        pending = await _seed_pending(
            test_engine, seeded.story_id, prompt_config={"validate": False}
        )
        monkeypatch.setattr(extraction_task, "get_engine", lambda: test_engine)
        _make_the_vector_store_unavailable(monkeypatch)

        # A cloud provider without its credential dies inside ``_build_llm_port`` —
        # before any prompt is rendered — and the failure is still terminal.
        await extraction_task.run_background_extraction(
            extraction_id=pending.id,
            story_id=seeded.story_id,
            workspace_id=seeded.workspace_id,
            model="llama3.2",
            provider="gemini",
            api_key=None,
            max_retries=0,
        )

        failed = await _reload(test_engine, pending.id)
        assert failed.status is ExtractionStatus.FAILED
        assert failed.prompt_rendered is None

    @pytest.mark.asyncio
    async def test_after_a_failed_run_every_snapshot_column_still_holds_its_birth_or_render_value(
        self, test_engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch, seed_workspace
    ) -> None:
        seeded = await seed_workspace(member=False)
        pending = await _seed_pending(
            test_engine, seeded.story_id, temperature=0.42, prompt_config={"validate": False}
        )
        llm = _ObservingLLM(test_engine, pending.id)

        monkeypatch.setattr(extraction_task, "get_engine", lambda: test_engine)
        monkeypatch.setattr(extraction_task, "OllamaAdapter", lambda **_: llm)
        _make_the_vector_store_unavailable(monkeypatch)

        await extraction_task.run_background_extraction(
            extraction_id=pending.id,
            story_id=seeded.story_id,
            workspace_id=seeded.workspace_id,
            model="llama3.2",
            max_retries=0,
        )

        failed = await _reload(test_engine, pending.id)
        assert failed.status is ExtractionStatus.FAILED
        expected = (llm.seen_system or "") + "\n\n" + (llm.seen_prompt or "")
        assert failed.prompt_rendered == expected
        assert failed.provider == "ollama"
        assert failed.temperature == 0.42
        assert failed.version_number == 1

    @pytest.mark.asyncio
    async def test_after_a_completed_run_every_snapshot_column_still_holds_its_birth_or_render_value(
        self, test_engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch, seed_workspace
    ) -> None:
        seeded = await seed_workspace(member=False)
        pending = await _seed_pending(
            test_engine, seeded.story_id, temperature=0.42, prompt_config={"validate": False}
        )
        llm = _ObservingAnsweringLLM(test_engine, pending.id)

        monkeypatch.setattr(extraction_task, "get_engine", lambda: test_engine)
        monkeypatch.setattr(extraction_task, "OllamaAdapter", lambda **_: llm)
        _make_the_vector_store_unavailable(monkeypatch)

        await extraction_task.run_background_extraction(
            extraction_id=pending.id,
            story_id=seeded.story_id,
            workspace_id=seeded.workspace_id,
            model="llama3.2",
            max_retries=0,
        )

        completed = await _reload(test_engine, pending.id)
        assert completed.status is ExtractionStatus.COMPLETED
        expected = (llm.seen_system or "") + "\n\n" + (llm.seen_prompt or "")
        assert completed.prompt_rendered == expected
        assert completed.provider == "ollama"
        assert completed.temperature == 0.42
        assert completed.version_number == 1
