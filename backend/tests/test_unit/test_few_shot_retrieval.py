"""Unit tests for automatic few-shot retrieval from the vector store.

Covers the unified ``## Few-Shot Examples`` prompt section driven by
``ExtractionService`` with a mocked ``VectorStorePort``. Tests RED→GREEN for
the enabled/disabled/cold-start/limit/search-failure paths.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from storico.domain.ports import ExtractionExample, LLMConfig, ParsedTask
from storico.domain.services.extraction_service import ExtractionService, FewShotConfig
from storico.infrastructure.llm.prompt_manager import PromptManager


def _make_service(vector_store=None, few_shot_config=None):
    """Build an ExtractionService with mocked LLM and parser, real PromptManager."""
    llm_port = AsyncMock()
    llm_port.generate.return_value = "1. summary: T\ndescription: D"
    task_parser = MagicMock()
    task_parser.parse.return_value = [ParsedTask(summary="T", description="D")]
    return ExtractionService(
        llm_port=llm_port,
        prompt_manager=PromptManager(),
        task_parser=task_parser,
        extraction_repo=AsyncMock(),
        task_repo=AsyncMock(),
        vector_store=vector_store,
        few_shot_config=few_shot_config,
    ), llm_port


class TestFewShotRetrieval:
    """ExtractionService renders the unified Few-Shot Examples section."""

    @pytest.mark.asyncio
    async def test_examples_injected_when_retrieval_returns_results(self) -> None:
        """Retrieved examples render the ``## Few-Shot Examples`` section."""
        workspace_id = uuid4()
        mock_store = AsyncMock()
        mock_store.search_similar.return_value = [
            ExtractionExample(
                user_story_text="Previous story",
                tasks_summary="1. Task A\n2. Task B",
                model_used="test",
                confidence_score=0.9,
                similarity_score=0.95,
            )
        ]
        service, llm_port = _make_service(vector_store=mock_store)

        story = MagicMock()
        story.raw_text = "Target story"

        await service.extract(
            story,
            LLMConfig(model="test"),
            workspace_id=workspace_id,
            few_shot_config=FewShotConfig(enabled=True, limit=3, threshold=0.85),
        )

        llm_port.generate.assert_called_once()
        instruction_prompt = llm_port.generate.call_args[0][0]
        assert "## Few-Shot Examples" in instruction_prompt
        assert "Previous story" in instruction_prompt
        assert "Now break down the following user story:" in instruction_prompt

    @pytest.mark.asyncio
    async def test_cold_start_omits_section(self) -> None:
        """No history (empty results) omits the examples section."""
        workspace_id = uuid4()
        mock_store = AsyncMock()
        mock_store.search_similar.return_value = []
        service, llm_port = _make_service(vector_store=mock_store)

        story = MagicMock()
        story.raw_text = "Target story"

        await service.extract(
            story,
            LLMConfig(model="test"),
            workspace_id=workspace_id,
            few_shot_config=FewShotConfig(enabled=True, limit=3, threshold=0.85),
        )

        instruction_prompt = llm_port.generate.call_args[0][0]
        assert "## Few-Shot Examples" not in instruction_prompt
        assert "Target story" in instruction_prompt

    @pytest.mark.asyncio
    async def test_disabled_skips_search_and_omits_section(self) -> None:
        """enabled=False skips the similarity search entirely."""
        workspace_id = uuid4()
        mock_store = AsyncMock()
        service, llm_port = _make_service(
            vector_store=mock_store, few_shot_config=FewShotConfig(enabled=False)
        )

        story = MagicMock()
        story.raw_text = "Target story"

        await service.extract(
            story,
            LLMConfig(model="test"),
            workspace_id=workspace_id,
            few_shot_config=FewShotConfig(enabled=False, limit=3, threshold=0.85),
        )

        mock_store.search_similar.assert_not_called()
        instruction_prompt = llm_port.generate.call_args[0][0]
        assert "## Few-Shot Examples" not in instruction_prompt

    @pytest.mark.asyncio
    async def test_limit_respected_in_search(self) -> None:
        """The workspace limit is passed to the search call."""
        workspace_id = uuid4()
        mock_store = AsyncMock()
        mock_store.search_similar.return_value = []
        service, _ = _make_service(vector_store=mock_store)

        story = MagicMock()
        story.raw_text = "Target story"

        await service.extract(
            story,
            LLMConfig(model="test"),
            workspace_id=workspace_id,
            few_shot_config=FewShotConfig(enabled=True, limit=2, threshold=0.9),
        )

        mock_store.search_similar.assert_called_once_with(
            text="Target story",
            limit=2,
            threshold=0.9,
            workspace_id=workspace_id,
        )

    @pytest.mark.asyncio
    async def test_search_failure_is_best_effort(self) -> None:
        """A search failure does not fail the extraction; section is omitted."""
        workspace_id = uuid4()
        mock_store = AsyncMock()
        mock_store.search_similar.side_effect = RuntimeError("Qdrant down")
        service, llm_port = _make_service(vector_store=mock_store)

        story = MagicMock()
        story.raw_text = "Target story"

        result_tasks, _ = await service.extract(
            story,
            LLMConfig(model="test"),
            workspace_id=workspace_id,
            few_shot_config=FewShotConfig(enabled=True, limit=3, threshold=0.85),
        )

        assert len(result_tasks) == 1
        instruction_prompt = llm_port.generate.call_args[0][0]
        assert "## Few-Shot Examples" not in instruction_prompt

    @pytest.mark.asyncio
    async def test_default_config_falls_back_when_none_passed(self) -> None:
        """No few_shot_config uses the service default (enabled, limit 3)."""
        workspace_id = uuid4()
        mock_store = AsyncMock()
        mock_store.search_similar.return_value = []
        service, _ = _make_service(vector_store=mock_store, few_shot_config=FewShotConfig())

        story = MagicMock()
        story.raw_text = "Target story"

        await service.extract(
            story,
            LLMConfig(model="test"),
            workspace_id=workspace_id,
        )

        mock_store.search_similar.assert_called_once_with(
            text="Target story",
            limit=3,
            threshold=0.85,
            workspace_id=workspace_id,
        )

    @pytest.mark.asyncio
    async def test_no_vector_store_omits_section(self) -> None:
        """No vector store configured means no examples section."""
        service, llm_port = _make_service(vector_store=None)

        story = MagicMock()
        story.raw_text = "Target story"

        await service.extract(
            story,
            LLMConfig(model="test"),
            workspace_id=uuid4(),
            few_shot_config=FewShotConfig(enabled=True),
        )

        instruction_prompt = llm_port.generate.call_args[0][0]
        assert "## Few-Shot Examples" not in instruction_prompt
