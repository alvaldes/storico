"""Integration tests for ExtractionService — EXT-T21.

Uses mocked ports (LLMPort, judge, vector store) to test the service layer
logic in isolation from real API calls and databases. The service renders
prompts and generates tasks only; persistence lives in the background task,
whose invariants are exercised in ``TestRunnerPersistencePath`` below.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

import storico.infrastructure.tasks.extraction_task as extraction_task
from storico.domain.entities import LLMConnectionError, ParseError
from storico.domain.entities.extraction import ExtractionStatus
from storico.domain.ports import (
    ExtractionExample,
    LLMConfig,
    LLMPort,
    ParsedTask,
    VectorStorePort,
)
from storico.domain.services.extraction_service import ExtractionService, FewShotConfig
from storico.infrastructure.database.repositories import SQLAlchemyExtractionRepository
from tests._helpers import seed_extraction


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
        deps["llm_port"].generate.return_value = "1. summary: Task one\ndescription: Desc"
        deps["task_parser"].parse.return_value = [
            ParsedTask(summary="Task one", description="Desc", labels=(), dependencies=()),
        ]

        mock_story = MagicMock()
        mock_story.id = uuid4()
        mock_story.raw_text = "As a user, I want X"

        rendered = await deps["service"].render(mock_story)
        result_tasks, raw = await deps["service"].generate(rendered, LLMConfig(model="test"))
        assert len(result_tasks) == 1
        assert result_tasks[0].summary == "Task one"
        assert raw == "1. summary: Task one\ndescription: Desc"

    @pytest.mark.asyncio
    async def test_extract_calls_prompt_manager(self, setup) -> None:
        """render() calls render_instruction with the workspace template."""
        deps = setup
        deps["prompt_manager"].render_instruction.return_value = "Instruction"
        deps["llm_port"].generate.return_value = "1. summary: T\ndescription: D"
        deps["task_parser"].parse.return_value = [ParsedTask(summary="T", description="D")]

        mock_story = MagicMock()
        mock_story.id = uuid4()
        mock_story.raw_text = "As a user, I want X"

        await deps["service"].render(mock_story)

        deps["prompt_manager"].render_instruction.assert_called_once_with(
            None,
            user_story="As a user, I want X",
        )

    @pytest.mark.asyncio
    async def test_extract_calls_llm_with_separate_system_prompt(self, setup) -> None:
        """LLM receives the instruction as prompt and system_prompt separately."""
        deps = setup
        deps["prompt_manager"].render_instruction.return_value = "INSTRUCTION"
        deps["llm_port"].generate.return_value = "1. summary: T\ndescription: D"
        deps["task_parser"].parse.return_value = [ParsedTask(summary="T", description="D")]

        mock_story = MagicMock()
        mock_story.id = uuid4()
        mock_story.raw_text = "Story"

        rendered = await deps["service"].render(mock_story, system_prompt="SYSTEM")
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
        deps["llm_port"].generate.return_value = "1. summary: T\ndescription: D"
        deps["task_parser"].parse.return_value = [ParsedTask(summary="T", description="D")]

        mock_story = MagicMock()
        mock_story.id = uuid4()
        mock_story.raw_text = "Story"

        await deps["service"].render(
            mock_story,
            instruction_template="Custom: {{user_story}}",
        )

        deps["prompt_manager"].render_instruction.assert_called_once_with(
            "Custom: {{user_story}}",
            user_story="Story",
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

        rendered = await deps["service"].render(mock_story)
        with pytest.raises(LLMConnectionError):
            await deps["service"].generate(rendered, LLMConfig(model="test"))

    @pytest.mark.asyncio
    async def test_extract_parse_error_propagates(self, setup) -> None:
        """Parse errors propagate through generate()."""
        deps = setup
        deps["prompt_manager"].render_instruction.return_value = "System"
        deps["prompt_manager"].render_instruction.return_value = "Instruction"
        deps["llm_port"].generate.return_value = "garbage output"
        deps["task_parser"].parse.side_effect = ParseError("Could not parse")

        mock_story = MagicMock()
        mock_story.id = uuid4()
        mock_story.raw_text = "Story"

        rendered = await deps["service"].render(mock_story)
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
        deps["llm_port"].generate.return_value = "1. summary: T\ndescription: D"
        deps["task_parser"].parse.return_value = [ParsedTask(summary="T", description="D")]

        mock_story = MagicMock()
        mock_story.id = uuid4()
        mock_story.raw_text = "Story"

        rendered = await deps["service"].render(mock_story)
        result_tasks, raw = await deps["service"].generate(rendered, LLMConfig(model="test"))
        assert len(result_tasks) == 1
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
        deps["llm_port"].generate.return_value = "1. summary: T\ndescription: D"
        deps["task_parser"].parse.return_value = [ParsedTask(summary="T", description="D")]

        mock_story = MagicMock()
        mock_story.id = uuid4()
        mock_story.raw_text = "Story"

        # RAG retrieval requires a workspace scope; this call exercises the
        # scoped-search path end to end.
        await deps["service"].render(mock_story, workspace_id=uuid4())

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
        deps["llm_port"].generate.return_value = "1. summary: T\ndescription: D"
        deps["task_parser"].parse.return_value = [ParsedTask(summary="T", description="D")]

        mock_story = MagicMock()
        mock_story.id = uuid4()
        mock_story.raw_text = "Story"

        rendered = await deps["service"].render(mock_story, workspace_id=uuid4())
        result_tasks, raw = await deps["service"].generate(rendered, LLMConfig(model="test"))
        assert len(result_tasks) == 1
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
        deps["llm_port"].generate.return_value = "1. summary: T\ndescription: D"
        deps["task_parser"].parse.return_value = [ParsedTask(summary="T", description="D")]

        mock_story = MagicMock()
        mock_story.id = uuid4()
        mock_story.raw_text = "Story"

        rendered = await deps["service"].render(mock_story)
        result_tasks, raw = await deps["service"].generate(rendered, LLMConfig(model="test"))

        assert len(result_tasks) == 1
        deps["vector_store"].search_similar.assert_not_called()
        call_kwargs = deps["prompt_manager"].render_instruction.call_args[1]
        assert "examples" not in call_kwargs


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
    ) -> str:
        return _ANSWER


class _UnreachableLLM(LLMPort):
    """LLM fake whose connection always fails."""

    async def generate(
        self,
        prompt: str,  # noqa: ARG002
        config: LLMConfig,  # noqa: ARG002
        system_prompt: str | None = None,  # noqa: ARG002
    ) -> str:
        raise LLMConnectionError("Cannot connect")


class _FailingParser:
    """Parser fake that refuses every response."""

    def parse(self, raw_response: str) -> list[ParsedTask]:  # noqa: ARG002
        raise ParseError("Could not parse")


class _ApprovingJudge:
    """Judge fake scoring 45/50, approved."""

    async def validate(self, **kwargs: object) -> SimpleNamespace:  # noqa: ARG002
        return SimpleNamespace(approved=True, total_score=45, criteria={})


class _BrokenJudge:
    """Judge fake whose validation call fails."""

    async def validate(self, **kwargs: object) -> SimpleNamespace:  # noqa: ARG002
        raise LLMConnectionError("Judge down")


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
    ) -> list:
        return []

    async def store_extraction(self, **kwargs: object) -> bool:
        if self._store_error is not None:
            raise self._store_error
        self.stored.append(kwargs)
        return True

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
            validate=True,
            max_retries=0,
        )

        async with factory() as session:
            completed = await SQLAlchemyExtractionRepository(session).find_by_id(pending.id)

        assert completed is not None
        assert completed.status == ExtractionStatus.COMPLETED
        assert completed.confidence_score == pytest.approx(45 / 50.0)

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
            validate=True,
            max_retries=0,
        )

        async with factory() as session:
            completed = await SQLAlchemyExtractionRepository(session).find_by_id(pending.id)

        assert completed is not None
        assert completed.status == ExtractionStatus.COMPLETED
        # Confidence is None because the judge failed, but the run still succeeds.
        assert completed.confidence_score is None

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
            max_retries=0,
        )

        async with factory() as session:
            completed = await SQLAlchemyExtractionRepository(session).find_by_id(pending.id)

        assert completed is not None
        assert completed.status == ExtractionStatus.COMPLETED
        assert completed.completed_at is not None
