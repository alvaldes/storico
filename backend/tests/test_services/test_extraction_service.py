"""Integration tests for ExtractionService — EXT-T21.

Uses mocked ports (LLMPort, judge, vector store) to test the service layer
logic in isolation from real API calls and databases. The service renders
prompts and generates tasks only; persistence lives in the background task,
whose invariants are exercised in ``TestRunnerPersistencePath`` below.
"""

import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest
from cryptography.fernet import Fernet
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

import storico.infrastructure.tasks.extraction_task as extraction_task
from storico.domain.entities import LLMConnectionError, ParseError
from storico.domain.entities.exceptions import JudgeOutputError
from storico.domain.entities.extraction import ExtractionStatus
from storico.domain.entities.workspace_llm_config import WorkspaceLLMConfig
from storico.domain.ports import (
    ExtractionExample,
    LLMConfig,
    LLMPort,
    ParsedTask,
    VectorStorePort,
)
from storico.domain.ports.llm_port import DEFAULT_MAX_TOKENS, DEFAULT_TEMPERATURE, LLMResponse
from storico.domain.services.extraction_judge_service import JudgeResult
from storico.domain.services.extraction_service import ExtractionService, FewShotConfig
from storico.infrastructure.crypto import FernetCipher
from storico.infrastructure.database.repositories import (
    SQLAlchemyExtractionRepository,
    SQLAlchemyWorkspaceLLMConfigRepository,
)
from tests._helpers import seed_extraction, simple_context


class TestExtractionService:
    """ExtractionService renders prompts and generates tasks.

    Tests mock all ports (LLMPort, judge, vector store) so no real
    network or database calls are made.
    """

    @pytest.fixture
    def setup(self):
        """Create an ExtractionService with its ports mocked."""
        llm_port = AsyncMock()
        prompt_manager = MagicMock()
        task_parser = MagicMock()
        judge_service = AsyncMock()

        service = ExtractionService(
            llm_port=llm_port,
            prompt_manager=prompt_manager,
            task_parser=task_parser,
            judge_service=judge_service,
        )
        return {
            "service": service,
            "llm_port": llm_port,
            "prompt_manager": prompt_manager,
            "task_parser": task_parser,
            "judge_service": judge_service,
        }

    # ── render() + generate() — happy path ─────────────────────────

    @pytest.mark.asyncio
    async def test_extract_success(self, setup) -> None:
        """Happy path: LLM returns valid response, tasks parsed."""
        deps = setup
        deps["prompt_manager"].render_instruction.return_value = "System prompt"
        deps["prompt_manager"].render_instruction.return_value = "Instruction prompt"
        deps["llm_port"].generate.return_value = LLMResponse(
            text="1. summary: Task one\ndescription: Desc"
        )
        deps["task_parser"].parse.return_value = [
            ParsedTask(summary="Task one", description="Desc", labels=(), dependencies=()),
        ]

        mock_story = MagicMock()
        mock_story.id = uuid4()
        mock_story.raw_text = "As a user, I want X"

        rendered = await deps["service"].render(mock_story, context=simple_context())
        result = await deps["service"].generate(rendered, LLMConfig(model="test"))
        assert len(result.tasks) == 1
        assert result.tasks[0].summary == "Task one"
        assert result.raw_response == "1. summary: Task one\ndescription: Desc"

    @pytest.mark.asyncio
    async def test_extract_calls_prompt_manager(self, setup) -> None:
        """render() calls render_instruction with the workspace template."""
        deps = setup
        deps["prompt_manager"].render_instruction.return_value = "Instruction"
        deps["llm_port"].generate.return_value = LLMResponse(text="1. summary: T\ndescription: D")
        deps["task_parser"].parse.return_value = [ParsedTask(summary="T", description="D")]

        mock_story = MagicMock()
        mock_story.id = uuid4()
        mock_story.raw_text = "As a user, I want X"

        await deps["service"].render(mock_story, context=simple_context())

        deps["prompt_manager"].render_instruction.assert_called_once_with(
            None,
            user_story="As a user, I want X",
            project_context=simple_context().as_template_variables(),
            negative_examples=[],
            negative_examples_omitted=0,
            few_shots=[],
        )

    @pytest.mark.asyncio
    async def test_extract_calls_llm_with_separate_system_prompt(self, setup) -> None:
        """LLM receives the instruction as prompt and system_prompt separately."""
        deps = setup
        deps["prompt_manager"].render_instruction.return_value = "INSTRUCTION"
        deps["llm_port"].generate.return_value = LLMResponse(text="1. summary: T\ndescription: D")
        deps["task_parser"].parse.return_value = [ParsedTask(summary="T", description="D")]

        mock_story = MagicMock()
        mock_story.id = uuid4()
        mock_story.raw_text = "Story"

        rendered = await deps["service"].render(
            mock_story, system_prompt="SYSTEM", context=simple_context()
        )
        await deps["service"].generate(rendered, LLMConfig(model="test"))

        # Verify the system prompt is passed separately, not concatenated
        deps["llm_port"].generate.assert_called_once_with(
            "INSTRUCTION",
            LLMConfig(model="test"),
            system_prompt="SYSTEM",
        )

    @pytest.mark.asyncio
    async def test_extract_forwards_instruction_template(self, setup) -> None:
        """A DB instruction template is forwarded to render_instruction."""
        deps = setup
        deps["prompt_manager"].render_instruction.return_value = "Custom instruction"
        deps["llm_port"].generate.return_value = LLMResponse(text="1. summary: T\ndescription: D")
        deps["task_parser"].parse.return_value = [ParsedTask(summary="T", description="D")]

        mock_story = MagicMock()
        mock_story.id = uuid4()
        mock_story.raw_text = "Story"

        await deps["service"].render(
            mock_story,
            instruction_template="Custom: {{user_story}}",
            context=simple_context(),
        )

        deps["prompt_manager"].render_instruction.assert_called_once_with(
            "Custom: {{user_story}}",
            user_story="Story",
            project_context=simple_context().as_template_variables(),
            negative_examples=[],
            negative_examples_omitted=0,
            few_shots=[],
        )

    # ── render() + generate() — error handling ─────────────────────

    @pytest.mark.asyncio
    async def test_extract_llm_error_propagates(self, setup) -> None:
        """LLM errors propagate through generate()."""
        deps = setup
        deps["prompt_manager"].render_instruction.return_value = "System"
        deps["prompt_manager"].render_instruction.return_value = "Instruction"
        deps["llm_port"].generate.side_effect = LLMConnectionError("Cannot connect")

        mock_story = MagicMock()
        mock_story.id = uuid4()
        mock_story.raw_text = "Story"

        rendered = await deps["service"].render(mock_story, context=simple_context())
        with pytest.raises(LLMConnectionError):
            await deps["service"].generate(rendered, LLMConfig(model="test"))

    @pytest.mark.asyncio
    async def test_extract_parse_error_propagates(self, setup) -> None:
        """Parse errors propagate through generate()."""
        deps = setup
        deps["prompt_manager"].render_instruction.return_value = "System"
        deps["prompt_manager"].render_instruction.return_value = "Instruction"
        deps["llm_port"].generate.return_value = LLMResponse(text="garbage output")
        deps["task_parser"].parse.side_effect = ParseError("Could not parse")

        mock_story = MagicMock()
        mock_story.id = uuid4()
        mock_story.raw_text = "Story"

        rendered = await deps["service"].render(mock_story, context=simple_context())
        with pytest.raises(ParseError):
            await deps["service"].generate(rendered, LLMConfig(model="test"))

    # ── Judge interaction ─────────────────────────────────────────

    # The judge is no longer driven by the service: the runner reaches into
    # ``_judge_service`` between generate() and mark_completed(). Its wiring
    # is exercised in ``TestRunnerPersistencePath``.

    # ── RAG integration ──────────────────────────────────────────────

    @pytest.fixture
    def setup_with_rag(self):
        """Create an ExtractionService with vector store mocked."""
        llm_port = AsyncMock()
        prompt_manager = MagicMock()
        task_parser = MagicMock()
        judge_service = AsyncMock()
        vector_store = AsyncMock()

        service = ExtractionService(
            llm_port=llm_port,
            prompt_manager=prompt_manager,
            task_parser=task_parser,
            judge_service=judge_service,
            vector_store=vector_store,
            few_shot_config=FewShotConfig(enabled=True, limit=2, threshold=0.8),
        )
        return {
            "service": service,
            "llm_port": llm_port,
            "prompt_manager": prompt_manager,
            "task_parser": task_parser,
            "judge_service": judge_service,
            "vector_store": vector_store,
        }

    @pytest.mark.asyncio
    async def test_extract_without_vector_store(self, setup) -> None:
        """VectorStorePort=None — existing behavior preserved, no RAG call."""
        deps = setup
        deps["prompt_manager"].render_instruction.return_value = "System"
        deps["prompt_manager"].render_instruction.return_value = "Instruction"
        deps["llm_port"].generate.return_value = LLMResponse(text="1. summary: T\ndescription: D")
        deps["task_parser"].parse.return_value = [ParsedTask(summary="T", description="D")]

        mock_story = MagicMock()
        mock_story.id = uuid4()
        mock_story.raw_text = "Story"

        rendered = await deps["service"].render(mock_story, context=simple_context())
        result = await deps["service"].generate(rendered, LLMConfig(model="test"))
        assert len(result.tasks) == 1
        # Vector store should not be referenced at all
        assert (
            not hasattr(deps["service"], "_vector_store") or deps["service"]._vector_store is None
        )

    @pytest.mark.asyncio
    async def test_extract_with_rag_examples(self, setup_with_rag) -> None:
        """VectorStorePort returns examples, prompt includes them."""
        deps = setup_with_rag
        mock_examples = [
            ExtractionExample(
                user_story_text="Previous story",
                tasks_summary="1. Task A\n2. Task B",
                model_used="test",
                confidence_score=0.9,
                similarity_score=0.95,
            )
        ]
        deps["vector_store"].search_similar.return_value = mock_examples
        deps["prompt_manager"].render_instruction.return_value = "System"
        deps["prompt_manager"].render_instruction.return_value = "Instruction with examples"
        deps["llm_port"].generate.return_value = LLMResponse(text="1. summary: T\ndescription: D")
        deps["task_parser"].parse.return_value = [ParsedTask(summary="T", description="D")]

        mock_story = MagicMock()
        mock_story.id = uuid4()
        mock_story.raw_text = "Story"

        # RAG retrieval requires a workspace scope; this call exercises the
        # scoped-search path end to end.
        await deps["service"].render(mock_story, workspace_id=uuid4(), context=simple_context())

        # Verify search_similar was called
        deps["vector_store"].search_similar.assert_called_once()

        # Verify prompt was rendered with examples kwarg
        call_kwargs = deps["prompt_manager"].render_instruction.call_args[1]
        assert "examples" in call_kwargs
        assert "Previous story" in call_kwargs["examples"]

    @pytest.mark.asyncio
    async def test_extract_rag_search_fails(self, setup_with_rag) -> None:
        """VectorStorePort raises, extraction proceeds without examples."""
        deps = setup_with_rag
        deps["vector_store"].search_similar.side_effect = RuntimeError("RAG down")
        deps["prompt_manager"].render_instruction.return_value = "System"
        deps["prompt_manager"].render_instruction.return_value = "Instruction"
        deps["llm_port"].generate.return_value = LLMResponse(text="1. summary: T\ndescription: D")
        deps["task_parser"].parse.return_value = [ParsedTask(summary="T", description="D")]

        mock_story = MagicMock()
        mock_story.id = uuid4()
        mock_story.raw_text = "Story"

        rendered = await deps["service"].render(
            mock_story, workspace_id=uuid4(), context=simple_context()
        )
        result = await deps["service"].generate(rendered, LLMConfig(model="test"))
        assert len(result.tasks) == 1
        # Should render WITHOUT examples kwarg
        call_kwargs = deps["prompt_manager"].render_instruction.call_args[1]
        assert "examples" not in call_kwargs

    @pytest.mark.asyncio
    async def test_extract_rag_enabled_without_workspace_skips_search(self, setup_with_rag) -> None:
        """A RAG-enabled extraction with no workspace scope fails closed.

        An unscoped search would reach every workspace and leak other
        workspaces' user stories into this prompt, so retrieval is skipped
        entirely: no vector search runs and no examples reach the prompt.
        """
        deps = setup_with_rag
        deps["vector_store"].search_similar.return_value = [
            ExtractionExample(
                user_story_text="Story from another workspace",
                tasks_summary="1. Task A",
                model_used="test",
                confidence_score=0.9,
                similarity_score=0.95,
            )
        ]
        deps["prompt_manager"].render_instruction.return_value = "Instruction"
        deps["llm_port"].generate.return_value = LLMResponse(text="1. summary: T\ndescription: D")
        deps["task_parser"].parse.return_value = [ParsedTask(summary="T", description="D")]

        mock_story = MagicMock()
        mock_story.id = uuid4()
        mock_story.raw_text = "Story"

        rendered = await deps["service"].render(mock_story, context=simple_context())
        result = await deps["service"].generate(rendered, LLMConfig(model="test"))

        assert len(result.tasks) == 1
        deps["vector_store"].search_similar.assert_not_called()
        call_kwargs = deps["prompt_manager"].render_instruction.call_args[1]
        assert "examples" not in call_kwargs

    @pytest.mark.asyncio
    async def test_extract_rag_enabled_without_story_id_skips_search(
        self, setup_with_rag, caplog: pytest.LogCaptureFixture
    ) -> None:
        """A RAG-enabled extraction whose story has no id fails closed.

        A retrieval that cannot state which story to exclude must not run at
        all: without ``exclude_story_id`` the search could return the story's
        own previous run as its own few-shot example. Skipping retrieval —
        mirroring the missing-``workspace_id`` branch above — is strictly
        better than retrieving unexcludable, and the skip is observable:
        exactly one warning carrying ``reason="missing_story_id"``.
        """
        deps = setup_with_rag
        deps["vector_store"].search_similar.return_value = [
            ExtractionExample(
                user_story_text="Story from an earlier run",
                tasks_summary="1. Task A",
                model_used="test",
                confidence_score=0.9,
                similarity_score=0.95,
            )
        ]
        deps["prompt_manager"].render_instruction.return_value = "Instruction"
        deps["llm_port"].generate.return_value = LLMResponse(text="1. summary: T\ndescription: D")
        deps["task_parser"].parse.return_value = [ParsedTask(summary="T", description="D")]

        # A story stand-in with no ``id`` attribute at all.
        mock_story = SimpleNamespace(raw_text="Story")

        with caplog.at_level(logging.WARNING, logger="storico.domain.services.extraction_service"):
            rendered = await deps["service"].render(
                mock_story, workspace_id=uuid4(), context=simple_context()
            )
        result = await deps["service"].generate(rendered, LLMConfig(model="test"))

        assert len(result.tasks) == 1
        deps["vector_store"].search_similar.assert_not_called()
        call_kwargs = deps["prompt_manager"].render_instruction.call_args[1]
        assert "examples" not in call_kwargs

        warnings = [
            record
            for record in caplog.records
            if getattr(record, "reason", None) == "missing_story_id"
        ]
        assert len(warnings) == 1


# ── The live persistence path (the runner) ──────────────────────────

_ANSWER = (
    "1. summary: Set up the schema\n"
    "description: Create the tables.\n\n"
    "2. summary: Build the endpoint\n"
    "description: Expose the data.\n"
)


class _AnsweringLLM(LLMPort):
    """LLM fake that answers with two well-formed tasks."""

    async def generate(
        self,
        prompt: str,  # noqa: ARG002
        config: LLMConfig,  # noqa: ARG002
        system_prompt: str | None = None,  # noqa: ARG002
    ) -> LLMResponse:
        return LLMResponse(text=_ANSWER)


class _UnreachableLLM(LLMPort):
    """LLM fake whose connection always fails."""

    async def generate(
        self,
        prompt: str,  # noqa: ARG002
        config: LLMConfig,  # noqa: ARG002
        system_prompt: str | None = None,  # noqa: ARG002
    ) -> LLMResponse:
        raise LLMConnectionError("Cannot connect")


class _FailingParser:
    """Parser fake that refuses every response."""

    def parse(self, raw_response: str) -> list[ParsedTask]:  # noqa: ARG002
        raise ParseError("Could not parse")


class _ApprovingJudge:
    """Judge fake scoring 49/49, approved — via the real ``JudgeResult`` contract.

    The runner computes ``confidence = total_score / max_total`` and persists the
    whole ``judge_result`` record, so the fake must return a real ``JudgeResult``
    (built through ``from_model_output``), not a loose ``SimpleNamespace``.
    """

    async def validate(self, **kwargs: object) -> JudgeResult:  # noqa: ARG002
        return JudgeResult.from_model_output(
            {
                "coherence": {"score": 7, "justification": "all tasks belong"},
                "completeness": {"score": 7, "justification": "nothing missing"},
                "feasibility": {"score": 7, "justification": "all realizable"},
                "clarity": {"score": 7, "justification": "clear"},
                "granularity": {"score": 7, "justification": "right size"},
                "dependencies": {"score": 7, "justification": "correct order"},
                "usefulness": {"score": 7, "justification": "sprint-ready"},
            }
        )


class _RecordingJudge:
    """Judge fake that records the ``LLMConfig`` it was called with, then approves.

    D7's assertion lives on the config the judge is *handed*, not only on the
    record the run writes: the point of the setting is that the judge call runs
    with the workspace's judge model.
    """

    def __init__(self) -> None:
        self.configs: list[LLMConfig] = []

    async def validate(self, **kwargs: object) -> JudgeResult:
        self.configs.append(kwargs["config"])
        return JudgeResult.from_model_output(
            {
                "coherence": {"score": 7, "justification": "all tasks belong"},
                "completeness": {"score": 7, "justification": "nothing missing"},
                "feasibility": {"score": 7, "justification": "all realizable"},
                "clarity": {"score": 7, "justification": "clear"},
                "granularity": {"score": 7, "justification": "right size"},
                "dependencies": {"score": 7, "justification": "correct order"},
                "usefulness": {"score": 7, "justification": "sprint-ready"},
            }
        )


class _BrokenJudge:
    """Judge fake whose validation call fails with a transient-shaped error."""

    async def validate(self, **kwargs: object) -> SimpleNamespace:  # noqa: ARG002
        raise LLMConnectionError("Judge down")


class _UnusableOutputJudge:
    """Judge fake whose answer fails the ``JudgeResult`` contract (D2).

    Raises ``JudgeOutputError`` — the error an unusable judge payload produces
    — and counts its calls, so the test can prove the runner classifies the
    failure instead of retrying it.
    """

    def __init__(self) -> None:
        self.calls = 0

    async def validate(self, **kwargs: object) -> JudgeResult:  # noqa: ARG002
        self.calls += 1
        raise JudgeOutputError("judge criterion 'coherence' is not a usable score: 'high'")


class _RecordingVectorStore(VectorStorePort):
    """Vector store that records ``store_extraction`` calls instead of writing."""

    def __init__(self, store_error: Exception | None = None) -> None:
        self.stored: list[dict] = []
        self._store_error = store_error

    async def search_similar(  # noqa: ARG002
        self,
        text: str,
        limit: int = 3,
        threshold: float = 0.85,
        *,
        workspace_id: UUID,  # noqa: ARG002
        exclude_story_id: str,  # noqa: ARG002
    ) -> list:
        return []

    async def store_extraction(self, **kwargs: object) -> bool:
        if self._store_error is not None:
            raise self._store_error
        self.stored.append(kwargs)
        return True

    async def set_has_invalid_tasks(self, *, extraction_id: str, has_invalid_tasks: bool) -> None:
        # Deliberately inert no-op: task 3.6 replaces this stub with a recording
        # fake once the mark handlers call it.
        return None

    async def delete_by_story(
        self,
        *,
        workspace_id: UUID,  # noqa: ARG002
        user_story_id: str,  # noqa: ARG002
    ) -> None:
        # Deliberately inert: the extraction path never deletes vector points,
        # so this fake has nothing to record. The deletion-recording fake that
        # exercises ``delete_by_story`` lives where the deletion behaviour is
        # tested (tests/test_api/test_stories.py).
        return None


async def _seed_judge_model(
    engine: AsyncEngine, workspace_id: UUID, judge_model: str | None
) -> None:
    """Persist a workspace LLM config row carrying ``judge_model`` (or none).

    Written with the real repository and its own master key, so the row reads back
    exactly as production would serve it. The row deliberately carries no credential:
    the runner's read of the judge model must not depend on the process master key.
    """
    master_key = Fernet.generate_key().decode("ascii")
    factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        await SQLAlchemyWorkspaceLLMConfigRepository(session, FernetCipher(master_key)).upsert(
            WorkspaceLLMConfig(
                workspace_id=workspace_id,
                provider="ollama",
                model="llama3.2",
                judge_model=judge_model,
            )
        )


def _make_vector_store_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    """Turn the RAG dependency off before the background task builds it.

    Same pattern as ``tests/test_api/test_extraction.py``: raising from the
    embedding-port factory takes the runner's production "vector store
    unavailable" branch (``vector_store=None``) and keeps the test off every
    live service.
    """

    def _unavailable(_settings) -> None:
        raise RuntimeError("vector store deliberately unavailable for this test")

    monkeypatch.setattr(extraction_task, "get_embedding_port", _unavailable)


class TestRunnerPersistencePath:
    """The dead ``extract_and_persist`` path's invariants, on the live runner.

    ``ExtractionService`` no longer persists anything, so the cases that
    exercised the deleted dead path run ``run_background_extraction`` instead —
    the real engine (SQLite in-memory) with the LLM adapter, parser, judge and
    vector store swapped by monkeypatch, the pattern
    ``tests/test_api/test_extraction.py`` already uses.
    """

    @pytest.mark.asyncio
    async def test_llm_error_is_recorded_on_a_failed_extraction(
        self, test_engine: AsyncEngine, monkeypatch, seed_workspace
    ) -> None:
        """An LLM error marks the same row failed, with error_info and a stamp."""
        factory = async_sessionmaker(bind=test_engine, class_=AsyncSession, expire_on_commit=False)
        seeded = await seed_workspace(member=False)

        async with factory() as session:
            pending = await seed_extraction(session, seeded.story_id, model_used="llama3.2")

        monkeypatch.setattr(extraction_task, "get_engine", lambda: test_engine)
        monkeypatch.setattr(extraction_task, "OllamaAdapter", lambda **_: _UnreachableLLM())
        _make_vector_store_unavailable(monkeypatch)

        await extraction_task.run_background_extraction(
            extraction_id=pending.id,
            story_id=seeded.story_id,
            workspace_id=seeded.workspace_id,
            model="llama3.2",
            version_number=1,
            max_retries=0,
        )

        async with factory() as session:
            failed = await SQLAlchemyExtractionRepository(session).find_by_id(pending.id)

        assert failed is not None
        # The run marks its own birth row — no second row, no second number.
        assert failed.id == pending.id
        assert failed.status == ExtractionStatus.FAILED
        assert "Cannot connect" in (failed.error_info or "")
        # A failure is terminal too, and it ends at a known moment rather than never.
        assert failed.completed_at is not None

    @pytest.mark.asyncio
    async def test_parse_error_is_recorded_on_a_failed_extraction(
        self, test_engine: AsyncEngine, monkeypatch, seed_workspace
    ) -> None:
        """A ParseError is a deterministic failure: the row is marked failed."""
        factory = async_sessionmaker(bind=test_engine, class_=AsyncSession, expire_on_commit=False)
        seeded = await seed_workspace(member=False)

        async with factory() as session:
            pending = await seed_extraction(session, seeded.story_id, model_used="llama3.2")

        monkeypatch.setattr(extraction_task, "get_engine", lambda: test_engine)
        monkeypatch.setattr(extraction_task, "OllamaAdapter", lambda **_: _AnsweringLLM())
        monkeypatch.setattr(extraction_task, "TaskParser", lambda: _FailingParser())
        _make_vector_store_unavailable(monkeypatch)

        await extraction_task.run_background_extraction(
            extraction_id=pending.id,
            story_id=seeded.story_id,
            workspace_id=seeded.workspace_id,
            model="llama3.2",
            version_number=1,
            max_retries=0,
        )

        async with factory() as session:
            failed = await SQLAlchemyExtractionRepository(session).find_by_id(pending.id)

        assert failed is not None
        assert failed.status == ExtractionStatus.FAILED

    @pytest.mark.asyncio
    async def test_judge_is_called_and_confidence_is_recorded(
        self, test_engine: AsyncEngine, monkeypatch, seed_workspace
    ) -> None:
        """With validate on, the judge runs and the row carries its score."""
        factory = async_sessionmaker(bind=test_engine, class_=AsyncSession, expire_on_commit=False)
        seeded = await seed_workspace(member=False)

        async with factory() as session:
            pending = await seed_extraction(session, seeded.story_id, model_used="llama3.2")

        monkeypatch.setattr(extraction_task, "get_engine", lambda: test_engine)
        monkeypatch.setattr(extraction_task, "OllamaAdapter", lambda **_: _AnsweringLLM())
        monkeypatch.setattr(extraction_task, "LLMJudgeService", lambda **_: _ApprovingJudge())
        _make_vector_store_unavailable(monkeypatch)

        await extraction_task.run_background_extraction(
            extraction_id=pending.id,
            story_id=seeded.story_id,
            workspace_id=seeded.workspace_id,
            model="llama3.2",
            version_number=1,
            validate=True,
            max_retries=0,
        )

        async with factory() as session:
            completed = await SQLAlchemyExtractionRepository(session).find_by_id(pending.id)

        assert completed is not None
        assert completed.status == ExtractionStatus.COMPLETED
        assert completed.confidence_score == pytest.approx(49 / 49.0)
        # The full judge record is persisted on the same terminal write (D4):
        # state ok, the per-criterion scores with their justifications, the
        # computed total, the derived indices (T3), and which model judged
        # (T1: the extraction model).
        record = completed.judge_result
        assert record is not None
        assert record["state"] == "ok"
        assert record["total_score"] == 49
        assert record["max_total"] == 49
        assert record["approved"] is True
        assert record["criteria"]["coherence"] == {
            "score": 7,
            "justification": "all tasks belong",
        }
        assert record["tas"] == pytest.approx(7.0)
        assert record["ifi"] == pytest.approx(7.0)
        assert record["model"] == "llama3.2"
        assert record["model_source"] == "extraction"
        assert record["error"] is None
        assert record["error_type"] is None

    @pytest.mark.asyncio
    async def test_a_configured_judge_model_is_what_the_judge_runs_with(
        self, test_engine: AsyncEngine, monkeypatch, seed_workspace
    ) -> None:
        """With ``judge_model`` configured, the judge runs with it (D7/S4).

        Observed twice: on the config the judge is actually called with — same
        temperature, budget and timeout as the extraction config, only the model
        swapped — and on the persisted record, which names the judge model and
        its ``workspace`` source. No provider probe, no second credential: the
        provider and endpoint stay the extraction config's own.
        """
        factory = async_sessionmaker(bind=test_engine, class_=AsyncSession, expire_on_commit=False)
        seeded = await seed_workspace(member=False)

        async with factory() as session:
            pending = await seed_extraction(session, seeded.story_id, model_used="llama3.2")
        await _seed_judge_model(test_engine, seeded.workspace_id, "qwen2.5-judge")

        judge = _RecordingJudge()
        monkeypatch.setattr(extraction_task, "get_engine", lambda: test_engine)
        monkeypatch.setattr(extraction_task, "OllamaAdapter", lambda **_: _AnsweringLLM())
        monkeypatch.setattr(extraction_task, "LLMJudgeService", lambda **_: judge)
        _make_vector_store_unavailable(monkeypatch)

        await extraction_task.run_background_extraction(
            extraction_id=pending.id,
            story_id=seeded.story_id,
            workspace_id=seeded.workspace_id,
            model="llama3.2",
            version_number=1,
            validate=True,
            max_retries=0,
        )

        # The judge was called once, with the judge model and the extraction
        # config's other knobs untouched.
        assert len(judge.configs) == 1
        assert judge.configs[0].model == "qwen2.5-judge"
        assert judge.configs[0].temperature == DEFAULT_TEMPERATURE
        assert judge.configs[0].max_tokens == DEFAULT_MAX_TOKENS
        assert judge.configs[0].timeout == 120

        async with factory() as session:
            completed = await SQLAlchemyExtractionRepository(session).find_by_id(pending.id)

        assert completed is not None
        record = completed.judge_result
        assert record is not None
        assert record["state"] == "ok"
        assert record["model"] == "qwen2.5-judge"
        assert record["model_source"] == "workspace"

    @pytest.mark.asyncio
    async def test_the_failed_record_also_names_the_judge_model(
        self, test_engine: AsyncEngine, monkeypatch, seed_workspace
    ) -> None:
        """A judge that failed still records who judged: model and source travel.

        "Requested and failed" (D5) must name the model that was *asked*, so the
        agreement analysis can see which judge produced the failed attempt.
        """
        factory = async_sessionmaker(bind=test_engine, class_=AsyncSession, expire_on_commit=False)
        seeded = await seed_workspace(member=False)

        async with factory() as session:
            pending = await seed_extraction(session, seeded.story_id, model_used="llama3.2")
        await _seed_judge_model(test_engine, seeded.workspace_id, "qwen2.5-judge")

        monkeypatch.setattr(extraction_task, "get_engine", lambda: test_engine)
        monkeypatch.setattr(extraction_task, "OllamaAdapter", lambda **_: _AnsweringLLM())
        monkeypatch.setattr(extraction_task, "LLMJudgeService", lambda **_: _BrokenJudge())
        _make_vector_store_unavailable(monkeypatch)

        await extraction_task.run_background_extraction(
            extraction_id=pending.id,
            story_id=seeded.story_id,
            workspace_id=seeded.workspace_id,
            model="llama3.2",
            version_number=1,
            validate=True,
            max_retries=0,
        )

        async with factory() as session:
            completed = await SQLAlchemyExtractionRepository(session).find_by_id(pending.id)

        assert completed is not None
        record = completed.judge_result
        assert record is not None
        assert record["state"] == "failed"
        assert record["error"] == "Judge down"
        assert record["model"] == "qwen2.5-judge"
        assert record["model_source"] == "workspace"

    @pytest.mark.asyncio
    async def test_a_blank_stored_judge_model_is_not_a_model_name(
        self, test_engine: AsyncEngine, monkeypatch, seed_workspace
    ) -> None:
        """A stored judge model made of spaces is "not configured", not a model.

        Same convention as ``base_url``/``api_key``: the runner normalizes the
        stored value, so a legacy blank falls back to the extraction model and
        the record says so, instead of asking a provider for a model named
        ``"   "``.
        """
        factory = async_sessionmaker(bind=test_engine, class_=AsyncSession, expire_on_commit=False)
        seeded = await seed_workspace(member=False)

        async with factory() as session:
            pending = await seed_extraction(session, seeded.story_id, model_used="llama3.2")
        await _seed_judge_model(test_engine, seeded.workspace_id, "   ")

        judge = _RecordingJudge()
        monkeypatch.setattr(extraction_task, "get_engine", lambda: test_engine)
        monkeypatch.setattr(extraction_task, "OllamaAdapter", lambda **_: _AnsweringLLM())
        monkeypatch.setattr(extraction_task, "LLMJudgeService", lambda **_: judge)
        _make_vector_store_unavailable(monkeypatch)

        await extraction_task.run_background_extraction(
            extraction_id=pending.id,
            story_id=seeded.story_id,
            workspace_id=seeded.workspace_id,
            model="llama3.2",
            version_number=1,
            validate=True,
            max_retries=0,
        )

        assert judge.configs[0].model == "llama3.2"

        async with factory() as session:
            completed = await SQLAlchemyExtractionRepository(session).find_by_id(pending.id)

        assert completed is not None
        record = completed.judge_result
        assert record is not None
        assert record["model"] == "llama3.2"
        assert record["model_source"] == "extraction"

    @pytest.mark.asyncio
    async def test_the_rag_point_carries_the_judge_state(
        self, test_engine: AsyncEngine, monkeypatch, seed_workspace
    ) -> None:
        """The Qdrant payload carries ``judge_state`` so "not requested" stays unambiguous.

        A ``null`` on a point that never carried ``prompt_config`` could not tell
        the two apart (D6); the point itself now says what the judge did.
        """
        factory = async_sessionmaker(bind=test_engine, class_=AsyncSession, expire_on_commit=False)
        seeded = await seed_workspace(member=False)

        async with factory() as session:
            pending = await seed_extraction(session, seeded.story_id, model_used="llama3.2")

        store = _RecordingVectorStore()
        monkeypatch.setattr(extraction_task, "get_engine", lambda: test_engine)
        monkeypatch.setattr(extraction_task, "OllamaAdapter", lambda **_: _AnsweringLLM())
        monkeypatch.setattr(extraction_task, "LLMJudgeService", lambda **_: _ApprovingJudge())
        monkeypatch.setattr(extraction_task, "get_embedding_port", lambda _settings: object())
        monkeypatch.setattr(extraction_task, "QdrantAdapter", lambda **_: store)

        await extraction_task.run_background_extraction(
            extraction_id=pending.id,
            story_id=seeded.story_id,
            workspace_id=seeded.workspace_id,
            model="llama3.2",
            version_number=1,
            validate=True,
            max_retries=0,
        )

        assert len(store.stored) == 1
        assert store.stored[0]["judge_state"] == "ok"

    @pytest.mark.asyncio
    async def test_judge_failure_does_not_break_the_run(
        self, test_engine: AsyncEngine, monkeypatch, seed_workspace
    ) -> None:
        """A failing judge still completes the run, with no confidence score."""
        factory = async_sessionmaker(bind=test_engine, class_=AsyncSession, expire_on_commit=False)
        seeded = await seed_workspace(member=False)

        async with factory() as session:
            pending = await seed_extraction(session, seeded.story_id, model_used="llama3.2")

        monkeypatch.setattr(extraction_task, "get_engine", lambda: test_engine)
        monkeypatch.setattr(extraction_task, "OllamaAdapter", lambda **_: _AnsweringLLM())
        monkeypatch.setattr(extraction_task, "LLMJudgeService", lambda **_: _BrokenJudge())
        _make_vector_store_unavailable(monkeypatch)

        await extraction_task.run_background_extraction(
            extraction_id=pending.id,
            story_id=seeded.story_id,
            workspace_id=seeded.workspace_id,
            model="llama3.2",
            version_number=1,
            validate=True,
            max_retries=0,
        )

        async with factory() as session:
            completed = await SQLAlchemyExtractionRepository(session).find_by_id(pending.id)

        assert completed is not None
        assert completed.status == ExtractionStatus.COMPLETED
        # Confidence is None because the judge failed, but the run still succeeds.
        assert completed.confidence_score is None
        # The failure is recorded on the row: "requested and failed" is
        # distinguishable from "never requested" (D5).
        record = completed.judge_result
        assert record is not None
        assert record["state"] == "failed"
        assert record["error"] == "Judge down"
        assert record["error_type"] == "LLMConnectionError"
        assert record["model"] == "llama3.2"
        assert record["model_source"] == "extraction"
        assert record["approved"] is False

    @pytest.mark.asyncio
    async def test_a_raising_judge_model_lookup_is_a_classified_judge_failure(
        self, test_engine: AsyncEngine, monkeypatch, seed_workspace
    ) -> None:
        """A config lookup that raises cannot fail the run (F2).

        ``_resolve_judge_model`` runs on the judge path, so a database or cipher
        error reaching it must be classified exactly like a judge call failure:
        the run completes with ``confidence_score`` null and a failed judge
        record, never retried as if the extraction itself had failed. The record
        still names who was asked — the honest values when the model could not
        be resolved are the extraction model and ``"extraction"``.
        """
        factory = async_sessionmaker(bind=test_engine, class_=AsyncSession, expire_on_commit=False)
        seeded = await seed_workspace(member=False)

        async with factory() as session:
            pending = await seed_extraction(session, seeded.story_id, model_used="llama3.2")

        async def _raising_lookup(session: object, workspace_id: object, settings: object) -> str:
            raise RuntimeError("config store unavailable")

        monkeypatch.setattr(extraction_task, "get_engine", lambda: test_engine)
        monkeypatch.setattr(extraction_task, "OllamaAdapter", lambda **_: _AnsweringLLM())
        monkeypatch.setattr(extraction_task, "LLMJudgeService", lambda **_: _ApprovingJudge())
        monkeypatch.setattr(extraction_task, "_resolve_judge_model", _raising_lookup)
        _make_vector_store_unavailable(monkeypatch)

        await extraction_task.run_background_extraction(
            extraction_id=pending.id,
            story_id=seeded.story_id,
            workspace_id=seeded.workspace_id,
            model="llama3.2",
            version_number=1,
            validate=True,
            max_retries=2,
        )

        async with factory() as session:
            completed = await SQLAlchemyExtractionRepository(session).find_by_id(pending.id)

        assert completed is not None
        # The lookup failure is a judge-path failure: the run itself completes.
        assert completed.status == ExtractionStatus.COMPLETED
        assert completed.confidence_score is None
        record = completed.judge_result
        assert record is not None
        assert record["state"] == "failed"
        assert record["error"] == "config store unavailable"
        assert record["error_type"] == "RuntimeError"
        # The honest values when no judge model could be resolved.
        assert record["model"] == "llama3.2"
        assert record["model_source"] == "extraction"

    @pytest.mark.asyncio
    async def test_an_unusable_judge_payload_is_a_classified_failure_not_a_retried_one(
        self, test_engine: AsyncEngine, monkeypatch, seed_workspace
    ) -> None:
        """A ``JudgeOutputError`` is caught as an ``LLMError``: no retry, a failed record.

        Before the contract existed, the deterministic type errors of the judge
        parser escaped into the generic ``except Exception`` of the runner and
        were retried with exponential backoff as if they were a network cut.
        """
        factory = async_sessionmaker(bind=test_engine, class_=AsyncSession, expire_on_commit=False)
        seeded = await seed_workspace(member=False)

        async with factory() as session:
            pending = await seed_extraction(session, seeded.story_id, model_used="llama3.2")

        judge = _UnusableOutputJudge()
        monkeypatch.setattr(extraction_task, "get_engine", lambda: test_engine)
        monkeypatch.setattr(extraction_task, "OllamaAdapter", lambda **_: _AnsweringLLM())
        monkeypatch.setattr(extraction_task, "LLMJudgeService", lambda **_: judge)
        _make_vector_store_unavailable(monkeypatch)

        await extraction_task.run_background_extraction(
            extraction_id=pending.id,
            story_id=seeded.story_id,
            workspace_id=seeded.workspace_id,
            model="llama3.2",
            version_number=1,
            validate=True,
            max_retries=2,
        )

        # Classified, not retried: exactly one judge attempt even though the
        # runner had two retries budgeted.
        assert judge.calls == 1

        async with factory() as session:
            completed = await SQLAlchemyExtractionRepository(session).find_by_id(pending.id)

        assert completed is not None
        assert completed.status == ExtractionStatus.COMPLETED
        assert completed.confidence_score is None
        record = completed.judge_result
        assert record is not None
        assert record["state"] == "failed"
        assert "coherence" in record["error"]
        assert record["error_type"] == "JudgeOutputError"

    @pytest.mark.asyncio
    async def test_validate_without_a_judge_service_records_a_failed_record(
        self, test_engine: AsyncEngine, monkeypatch, seed_workspace
    ) -> None:
        """``validate=True`` with no judge service leaves a failed record, not a null.

        "Not requested" and "requested and could not run" must stay
        distinguishable on the row (D5), so the missing service is a classified
        failure with its own message.
        """
        factory = async_sessionmaker(bind=test_engine, class_=AsyncSession, expire_on_commit=False)
        seeded = await seed_workspace(member=False)

        async with factory() as session:
            pending = await seed_extraction(session, seeded.story_id, model_used="llama3.2")

        monkeypatch.setattr(extraction_task, "get_engine", lambda: test_engine)
        monkeypatch.setattr(extraction_task, "OllamaAdapter", lambda **_: _AnsweringLLM())
        monkeypatch.setattr(extraction_task, "LLMJudgeService", lambda **_: None)
        _make_vector_store_unavailable(monkeypatch)

        await extraction_task.run_background_extraction(
            extraction_id=pending.id,
            story_id=seeded.story_id,
            workspace_id=seeded.workspace_id,
            model="llama3.2",
            version_number=1,
            validate=True,
            max_retries=0,
        )

        async with factory() as session:
            completed = await SQLAlchemyExtractionRepository(session).find_by_id(pending.id)

        assert completed is not None
        assert completed.status == ExtractionStatus.COMPLETED
        assert completed.confidence_score is None
        record = completed.judge_result
        assert record is not None
        assert record["state"] == "failed"
        assert record["error"] == "judge service unavailable"

    @pytest.mark.asyncio
    async def test_a_run_without_validation_leaves_judge_result_null(
        self, test_engine: AsyncEngine, monkeypatch, seed_workspace
    ) -> None:
        """A switched-off run writes no judge record: "not requested" is ``NULL`` (D5)."""
        factory = async_sessionmaker(bind=test_engine, class_=AsyncSession, expire_on_commit=False)
        seeded = await seed_workspace(member=False)

        async with factory() as session:
            pending = await seed_extraction(session, seeded.story_id, model_used="llama3.2")

        monkeypatch.setattr(extraction_task, "get_engine", lambda: test_engine)
        monkeypatch.setattr(extraction_task, "OllamaAdapter", lambda **_: _AnsweringLLM())
        _make_vector_store_unavailable(monkeypatch)

        await extraction_task.run_background_extraction(
            extraction_id=pending.id,
            story_id=seeded.story_id,
            workspace_id=seeded.workspace_id,
            model="llama3.2",
            version_number=1,
            max_retries=0,
        )

        async with factory() as session:
            completed = await SQLAlchemyExtractionRepository(session).find_by_id(pending.id)

        assert completed is not None
        assert completed.status == ExtractionStatus.COMPLETED
        assert completed.judge_result is None

    @pytest.mark.asyncio
    async def test_a_run_without_validation_leaves_the_rag_judge_state_null(
        self, test_engine: AsyncEngine, monkeypatch, seed_workspace
    ) -> None:
        """The Qdrant point of a switched-off run carries ``judge_state=None``."""
        factory = async_sessionmaker(bind=test_engine, class_=AsyncSession, expire_on_commit=False)
        seeded = await seed_workspace(member=False)

        async with factory() as session:
            pending = await seed_extraction(session, seeded.story_id, model_used="llama3.2")

        store = _RecordingVectorStore()
        monkeypatch.setattr(extraction_task, "get_engine", lambda: test_engine)
        monkeypatch.setattr(extraction_task, "OllamaAdapter", lambda **_: _AnsweringLLM())
        monkeypatch.setattr(extraction_task, "get_embedding_port", lambda _settings: object())
        monkeypatch.setattr(extraction_task, "QdrantAdapter", lambda **_: store)

        await extraction_task.run_background_extraction(
            extraction_id=pending.id,
            story_id=seeded.story_id,
            workspace_id=seeded.workspace_id,
            model="llama3.2",
            version_number=1,
            max_retries=0,
        )

        assert len(store.stored) == 1
        assert store.stored[0]["judge_state"] is None

    @pytest.mark.asyncio
    async def test_vector_store_failure_does_not_break_the_run(
        self, test_engine: AsyncEngine, monkeypatch, seed_workspace
    ) -> None:
        """A raising vector store still completes the run."""
        factory = async_sessionmaker(bind=test_engine, class_=AsyncSession, expire_on_commit=False)
        seeded = await seed_workspace(member=False)

        async with factory() as session:
            pending = await seed_extraction(session, seeded.story_id, model_used="llama3.2")

        store = _RecordingVectorStore(store_error=RuntimeError("Store failed"))
        monkeypatch.setattr(extraction_task, "get_engine", lambda: test_engine)
        monkeypatch.setattr(extraction_task, "OllamaAdapter", lambda **_: _AnsweringLLM())
        monkeypatch.setattr(extraction_task, "get_embedding_port", lambda _settings: object())
        monkeypatch.setattr(extraction_task, "QdrantAdapter", lambda **_: store)

        await extraction_task.run_background_extraction(
            extraction_id=pending.id,
            story_id=seeded.story_id,
            workspace_id=seeded.workspace_id,
            model="llama3.2",
            version_number=1,
            max_retries=0,
        )

        async with factory() as session:
            completed = await SQLAlchemyExtractionRepository(session).find_by_id(pending.id)

        assert completed is not None
        assert completed.status == ExtractionStatus.COMPLETED
        assert completed.completed_at is not None
