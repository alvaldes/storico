"""Run-level truncation contract — `odd/tasks/extraction-truncation.md` (S1/S2/S3/S5).

An answer cut by the output budget must end as a ``failed`` extraction with zero
tasks persisted for that version and an ``error_info`` that names ``max_tokens``
and says raising it is the fix — never as a ``completed`` run carrying a partial
task set. The failure travels the deterministic path (``LLMError`` in
``run_background_extraction``), so no retry may happen; and a legitimately short
(not truncated) answer still ends ``completed`` with its tasks.

The truncating run goes through the **real** ``OpenAIAdapter`` with a mocked SDK
client, so the whole chain — adapter classification, parser, runner, terminal
marks, task persistence — is what the assertions observe, not a stub raising the
exception on the adapter's behalf.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from storico.domain.entities.extraction import ExtractionStatus
from storico.domain.ports import LLMConfig, LLMPort
from storico.domain.ports.llm_port import LLMResponse
from storico.infrastructure.database.repositories import SQLAlchemyTaskRepository
from storico.infrastructure.llm.openai_adapter import OpenAIAdapter
from storico.infrastructure.tasks import extraction_task
from tests._helpers import seed_extraction

#: Three tasks' worth of prompt-shaped text, cut mid-sentence by the budget.
_TRUNCATED_ANSWER = (
    "1. summary: Create the database schema\n"
    "description: Create the tables for transaction history records.\n"
    "2. summary: Implement the listing API endpoint\n"
    "description: Build a REST endpoint that returns paginated transaction hi"
)

#: One task, finished cleanly — short, not truncated.
_SHORT_ANSWER = "1. summary: Only task\ndescription: Do the one thing.\n"


def _factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)


async def _seed_pending(engine: AsyncEngine, story_id: UUID, **kwargs: Any) -> Any:
    """Seed a ``pending`` extraction the way the route's birth path leaves it."""
    async with _factory(engine)() as session:
        return await seed_extraction(session, story_id, **kwargs)  # type: ignore[arg-type]


async def _reload(engine: AsyncEngine, extraction_id: UUID) -> Any:
    from storico.infrastructure.database.repositories import SQLAlchemyExtractionRepository

    async with _factory(engine)() as session:
        found = await SQLAlchemyExtractionRepository(session).find_by_id(extraction_id)
        assert found is not None
        return found


async def _tasks_of_version(engine: AsyncEngine, story_id: UUID, extraction_id: UUID) -> list[Any]:
    async with _factory(engine)() as session:
        return list(
            await SQLAlchemyTaskRepository(session).list_by_story_version(story_id, extraction_id)
        )


def _truncating_openai_client(content: str) -> MagicMock:
    """A mocked ``AsyncOpenAI`` whose answer is non-empty but budget-cut.

    The mocked response mirrors the installed SDK's typed shape:
    ``Choice.finish_reason`` is the ``"length"`` member of
    ``Literal["stop", "length", "tool_calls", "content_filter", "function_call"]``
    (``openai/types/chat/chat_completion.py``).
    """
    client = MagicMock()
    response = MagicMock()
    response.choices = [MagicMock()]
    response.choices[0].message.content = content
    response.choices[0].finish_reason = "length"
    response.choices[0].message.refusal = None
    response.usage = None
    client.chat.completions.create = AsyncMock(return_value=response)
    return client


def _make_the_vector_store_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    """Turn the RAG dependency off, the way a deployment without one runs."""

    def _unavailable(_settings: object) -> None:
        raise RuntimeError("vector store deliberately unavailable for this test")

    monkeypatch.setattr(extraction_task, "get_embedding_port", _unavailable)


class _ShortAnswerLLM(LLMPort):
    """A provider that answers one clean task and records how often it was asked."""

    def __init__(self) -> None:
        self.calls = 0

    async def generate(
        self,
        prompt: str,  # noqa: ARG002
        config: LLMConfig,  # noqa: ARG002
        system_prompt: str | None = None,  # noqa: ARG002
    ) -> LLMResponse:
        self.calls += 1
        return LLMResponse(text=_SHORT_ANSWER, usage=None)


class TestTruncatedRunEndsFailed:
    """S1/S2/S3/S5 at the level the extraction row and its tasks live."""

    @pytest.mark.asyncio
    async def test_a_budget_truncated_answer_ends_failed_with_zero_tasks_and_names_the_budget(
        self,
        test_engine: AsyncEngine,
        monkeypatch: pytest.MonkeyPatch,
        seed_workspace,
    ) -> None:
        """The hole today: a truncated answer with content persists as ``completed``."""
        seeded = await seed_workspace(member=False)
        pending = await _seed_pending(
            test_engine, seeded.story_id, provider="openai", prompt_config={"validate": False}
        )
        client = _truncating_openai_client(_TRUNCATED_ANSWER)
        monkeypatch.setattr(extraction_task, "get_engine", lambda: test_engine)
        monkeypatch.setattr(
            extraction_task,
            "OpenAIAdapter",
            lambda **kwargs: OpenAIAdapter(
                api_key=kwargs.get("api_key") or "test-key",
                base_url=kwargs.get("base_url"),
                client=client,
            ),
        )
        _make_the_vector_store_unavailable(monkeypatch)

        # Default ``max_retries=2`` on purpose: the assertion below is that the
        # deterministic path never reaches the retry loop (S3).
        await extraction_task.run_background_extraction(
            extraction_id=pending.id,
            story_id=seeded.story_id,
            workspace_id=seeded.workspace_id,
            model="gpt-4o-mini",
            version_number=1,
            provider="openai",
            api_key="test-key",
        )

        failed = await _reload(test_engine, pending.id)
        assert failed.status is ExtractionStatus.FAILED
        assert failed.error_info is not None
        # S2: the reason names the budget and the way out.
        assert "max_tokens" in failed.error_info
        assert "max tokens" in failed.error_info.lower()
        # S1/S5: zero tasks persisted for that version.
        assert await _tasks_of_version(test_engine, seeded.story_id, pending.id) == []
        # S3: the provider was asked exactly once — no retry.
        assert client.chat.completions.create.await_count == 1

    @pytest.mark.asyncio
    async def test_a_legitimately_short_answer_still_completes_with_its_tasks(
        self,
        test_engine: AsyncEngine,
        monkeypatch: pytest.MonkeyPatch,
        seed_workspace,
    ) -> None:
        """A finished one-task answer is a ``completed`` run carrying that task."""
        seeded = await seed_workspace(member=False)
        pending = await _seed_pending(
            test_engine, seeded.story_id, provider="ollama", prompt_config={"validate": False}
        )
        llm = _ShortAnswerLLM()
        monkeypatch.setattr(extraction_task, "get_engine", lambda: test_engine)
        monkeypatch.setattr(extraction_task, "OllamaAdapter", lambda **_: llm)
        _make_the_vector_store_unavailable(monkeypatch)

        await extraction_task.run_background_extraction(
            extraction_id=pending.id,
            story_id=seeded.story_id,
            workspace_id=seeded.workspace_id,
            model="llama3.2",
            version_number=1,
        )

        completed = await _reload(test_engine, pending.id)
        assert completed.status is ExtractionStatus.COMPLETED
        assert completed.error_info is None
        tasks = await _tasks_of_version(test_engine, seeded.story_id, pending.id)
        assert len(tasks) == 1
        assert tasks[0].title == "Only task"
        assert llm.calls == 1
