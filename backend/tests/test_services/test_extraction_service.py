"""Integration tests for ExtractionService — EXT-T21.

Uses mocked ports (LLMPort, repos) to test the service layer logic
in isolation from real API calls and databases.
"""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from storico.domain.entities import LLMConnectionError, ParseError
from storico.domain.ports import LLMConfig, ParsedTask
from storico.domain.services.extraction_service import ExtractionService


class TestExtractionService:
    """ExtractionService orchestrates the full extraction pipeline.

    Tests mock all ports (LLMPort, repositories, judge) so no real
    network or database calls are made.
    """

    @pytest.fixture
    def setup(self):
        """Create an ExtractionService with all ports mocked."""
        llm_port = AsyncMock()
        prompt_manager = MagicMock()
        task_parser = MagicMock()
        extraction_repo = AsyncMock()
        task_repo = AsyncMock()
        judge_service = AsyncMock()

        service = ExtractionService(
            llm_port=llm_port,
            prompt_manager=prompt_manager,
            task_parser=task_parser,
            extraction_repo=extraction_repo,
            task_repo=task_repo,
            judge_service=judge_service,
        )
        return {
            "service": service,
            "llm_port": llm_port,
            "prompt_manager": prompt_manager,
            "task_parser": task_parser,
            "extraction_repo": extraction_repo,
            "task_repo": task_repo,
            "judge_service": judge_service,
        }

    # ── extract() — happy path ─────────────────────────────────────

    @pytest.mark.asyncio
    async def test_extract_success(self, setup) -> None:
        """Happy path: LLM returns valid response, tasks parsed."""
        deps = setup
        deps["prompt_manager"].render_system_prompt.return_value = "System prompt"
        deps["prompt_manager"].render.return_value = "Instruction prompt"
        deps["llm_port"].generate.return_value = "1. summary: Task one\ndescription: Desc"
        deps["task_parser"].parse.return_value = [
            ParsedTask(summary="Task one", description="Desc", labels=(), dependencies=()),
        ]

        mock_story = MagicMock()
        mock_story.id = uuid4()
        mock_story.raw_text = "As a user, I want X"

        result_tasks, raw = await deps["service"].extract(mock_story, LLMConfig(model="test"))
        assert len(result_tasks) == 1
        assert result_tasks[0].summary == "Task one"
        assert raw == "1. summary: Task one\ndescription: Desc"

    @pytest.mark.asyncio
    async def test_extract_calls_prompt_manager(self, setup) -> None:
        """extract() calls render_system_prompt and render with correct args."""
        deps = setup
        deps["prompt_manager"].render_system_prompt.return_value = "System"
        deps["prompt_manager"].render.return_value = "Instruction"
        deps["llm_port"].generate.return_value = "1. summary: T\ndescription: D"
        deps["task_parser"].parse.return_value = [ParsedTask(summary="T", description="D")]

        mock_story = MagicMock()
        mock_story.id = uuid4()
        mock_story.raw_text = "As a user, I want X"

        await deps["service"].extract(mock_story, LLMConfig(model="test"))

        deps["prompt_manager"].render_system_prompt.assert_called_once()
        deps["prompt_manager"].render.assert_called_once_with(
            "task_generation.j2",
            user_story="As a user, I want X",
        )

    @pytest.mark.asyncio
    async def test_extract_calls_llm_with_combined_prompt(self, setup) -> None:
        """LLM receives system + instruction combined."""
        deps = setup
        deps["prompt_manager"].render_system_prompt.return_value = "SYSTEM"
        deps["prompt_manager"].render.return_value = "INSTRUCTION"
        deps["llm_port"].generate.return_value = "1. summary: T\ndescription: D"
        deps["task_parser"].parse.return_value = [ParsedTask(summary="T", description="D")]

        mock_story = MagicMock()
        mock_story.id = uuid4()
        mock_story.raw_text = "Story"

        await deps["service"].extract(mock_story, LLMConfig(model="test"))

        # Verify the combined prompt was sent
        call_args = deps["llm_port"].generate.call_args[0]
        combined = call_args[0]
        assert "SYSTEM" in combined
        assert "INSTRUCTION" in combined

    # ── extract() — error handling ─────────────────────────────────

    @pytest.mark.asyncio
    async def test_extract_llm_error_propagates(self, setup) -> None:
        """LLM errors propagate through extract()."""
        deps = setup
        deps["prompt_manager"].render_system_prompt.return_value = "System"
        deps["prompt_manager"].render.return_value = "Instruction"
        deps["llm_port"].generate.side_effect = LLMConnectionError("Cannot connect")

        mock_story = MagicMock()
        mock_story.id = uuid4()
        mock_story.raw_text = "Story"

        with pytest.raises(LLMConnectionError):
            await deps["service"].extract(mock_story, LLMConfig(model="test"))

    @pytest.mark.asyncio
    async def test_extract_parse_error_propagates(self, setup) -> None:
        """Parse errors propagate through extract()."""
        deps = setup
        deps["prompt_manager"].render_system_prompt.return_value = "System"
        deps["prompt_manager"].render.return_value = "Instruction"
        deps["llm_port"].generate.return_value = "garbage output"
        deps["task_parser"].parse.side_effect = ParseError("Could not parse")

        mock_story = MagicMock()
        mock_story.id = uuid4()
        mock_story.raw_text = "Story"

        with pytest.raises(ParseError):
            await deps["service"].extract(mock_story, LLMConfig(model="test"))

    # ── extract_and_persist() — happy path ─────────────────────────

    @pytest.mark.asyncio
    async def test_extract_and_persist_full_pipeline(self, setup) -> None:
        """Full pipeline creates Extraction + Task entities."""
        deps = setup
        story_id = uuid4()
        mock_story = MagicMock()
        mock_story.id = story_id
        mock_story.raw_text = "As a user, I want X"

        deps["prompt_manager"].render_system_prompt.return_value = "System"
        deps["prompt_manager"].render.return_value = "Instruction"
        deps["llm_port"].generate.return_value = "1. summary: Task one\ndescription: Desc"
        deps["task_parser"].parse.return_value = [
            ParsedTask(summary="Task one", description="Desc", labels=(), dependencies=()),
        ]
        deps["extraction_repo"].save.side_effect = lambda e: e
        deps["task_repo"].save.side_effect = lambda t: t
        deps["judge_service"].validate.return_value = MagicMock(
            approved=True, total_score=45, criteria={}
        )

        result = await deps["service"].extract_and_persist(mock_story, LLMConfig(model="test"))
        assert result.status == "completed"
        assert deps["extraction_repo"].save.called
        assert deps["task_repo"].save.called

    @pytest.mark.asyncio
    async def test_extract_and_persist_saves_tasks(self, setup) -> None:
        """Each parsed task is persisted via task_repo.save()."""
        deps = setup
        story_id = uuid4()
        mock_story = MagicMock()
        mock_story.id = story_id
        mock_story.raw_text = "Story"

        deps["prompt_manager"].render_system_prompt.return_value = "S"
        deps["prompt_manager"].render.return_value = "I"
        deps["llm_port"].generate.return_value = "1. summary: T1\ndescription: D1\n2. summary: T2\ndescription: D2"
        deps["task_parser"].parse.return_value = [
            ParsedTask(summary="T1", description="D1"),
            ParsedTask(summary="T2", description="D2"),
        ]
        deps["extraction_repo"].save.side_effect = lambda e: e
        deps["task_repo"].save.side_effect = lambda t: t

        await deps["service"].extract_and_persist(mock_story, LLMConfig(model="test"))
        assert deps["task_repo"].save.call_count == 2

    # ── extract_and_persist() — error handling ─────────────────────

    @pytest.mark.asyncio
    async def test_extract_llm_error_persists_failed(self, setup) -> None:
        """LLM error persists failed extraction with error_info."""
        deps = setup
        story_id = uuid4()
        mock_story = MagicMock()
        mock_story.id = story_id
        mock_story.raw_text = "As a user, I want X"

        deps["prompt_manager"].render_system_prompt.return_value = "System"
        deps["prompt_manager"].render.return_value = "Instruction"
        deps["llm_port"].generate.side_effect = LLMConnectionError("Cannot connect")
        deps["extraction_repo"].save.side_effect = lambda e: e

        result = await deps["service"].extract_and_persist(mock_story, LLMConfig(model="test"))
        assert result.status == "failed"
        assert "Cannot connect" in (result.error_info or "")

    @pytest.mark.asyncio
    async def test_extract_parse_error_persists_failed(self, setup) -> None:
        """Parse error persists failed extraction."""
        deps = setup
        mock_story = MagicMock()
        mock_story.id = uuid4()
        mock_story.raw_text = "Test"

        deps["prompt_manager"].render_system_prompt.return_value = "System"
        deps["prompt_manager"].render.return_value = "Instruction"
        deps["llm_port"].generate.return_value = "garbage output"
        deps["task_parser"].parse.side_effect = ParseError("Could not parse")
        deps["extraction_repo"].save.side_effect = lambda e: e

        result = await deps["service"].extract_and_persist(mock_story, LLMConfig(model="test"))
        assert result.status == "failed"

    @pytest.mark.asyncio
    async def test_extract_and_persist_failed_extraction_still_saved(self, setup) -> None:
        """Even a failed extraction is saved to the repo."""
        deps = setup
        mock_story = MagicMock()
        mock_story.id = uuid4()
        mock_story.raw_text = "Story"

        deps["prompt_manager"].render_system_prompt.return_value = "S"
        deps["prompt_manager"].render.return_value = "I"
        deps["llm_port"].generate.side_effect = LLMConnectionError("Fail")
        deps["extraction_repo"].save.side_effect = lambda e: e

        result = await deps["service"].extract_and_persist(mock_story, LLMConfig(model="test"))
        assert deps["extraction_repo"].save.called
        assert result.status == "failed"

    # ── Judge interaction ─────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_extract_and_persist_with_judge(self, setup) -> None:
        """Judge is called and confidence is computed."""
        deps = setup
        story_id = uuid4()
        mock_story = MagicMock()
        mock_story.id = story_id
        mock_story.raw_text = "Story"

        deps["prompt_manager"].render_system_prompt.return_value = "S"
        deps["prompt_manager"].render.return_value = "I"
        deps["llm_port"].generate.return_value = "1. summary: T\ndescription: D"
        deps["task_parser"].parse.return_value = [ParsedTask(summary="T", description="D")]
        deps["extraction_repo"].save.side_effect = lambda e: e
        deps["task_repo"].save.side_effect = lambda t: t
        deps["judge_service"].validate.return_value = MagicMock(
            approved=True, total_score=45, criteria={}
        )

        result = await deps["service"].extract_and_persist(mock_story, LLMConfig(model="test"))
        assert result.confidence_score == 45 / 50.0
        deps["judge_service"].validate.assert_called_once()

    @pytest.mark.asyncio
    async def test_extract_and_persist_judge_failure_does_not_break(self, setup) -> None:
        """Judge failure should not break extraction — confidence stays None."""
        deps = setup
        story_id = uuid4()
        mock_story = MagicMock()
        mock_story.id = story_id
        mock_story.raw_text = "Story"

        deps["prompt_manager"].render_system_prompt.return_value = "S"
        deps["prompt_manager"].render.return_value = "I"
        deps["llm_port"].generate.return_value = "1. summary: T\ndescription: D"
        deps["task_parser"].parse.return_value = [ParsedTask(summary="T", description="D")]
        deps["extraction_repo"].save.side_effect = lambda e: e
        deps["task_repo"].save.side_effect = lambda t: t
        deps["judge_service"].validate.side_effect = LLMConnectionError("Judge down")

        result = await deps["service"].extract_and_persist(mock_story, LLMConfig(model="test"))
        assert result.status == "completed"
        # Confidence is None because judge failed, but extraction still succeeds
