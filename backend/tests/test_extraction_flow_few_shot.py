"""Integration-lite tests for the unified few-shot extraction flow.

Covers the end-to-end mapping from workspace-scoped vector retrieval into the
``## Few-Shot Examples`` prompt section, plus the new prompt config fields.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from storico.api.schemas.workspace_prompt import PromptRequest, PromptResponse
from storico.domain.ports import ExtractionExample, LLMConfig, ParsedTask
from storico.domain.services.extraction_service import ExtractionService, FewShotConfig
from storico.infrastructure.llm.prompt_manager import PromptManager


@pytest.fixture
def mock_llm_port():
    """Mock LLM port that returns a predictable extraction response."""
    mock = AsyncMock()
    mock.generate.return_value = (
        "1. summary: Set up authentication database\n"
        "description: Create tables for users and sessions.\n"
        "2. summary: Implement login endpoint\n"
        "description: Build POST /auth/login with credential validation."
    )
    return mock


class TestExtractionFlowWithFewShot:
    """Full extraction flow with vector-sourced few-shot examples."""

    @pytest.mark.asyncio
    async def test_extraction_includes_few_shot_section(self, mock_llm_port) -> None:
        """Retrieved examples render a single ``## Few-Shot Examples`` section."""
        vector_store = AsyncMock()
        vector_store.search_similar.return_value = [
            ExtractionExample(
                user_story_text="As a user, I want login",
                tasks_summary="1. summary: Setup auth\ndescription: Create tables.",
                model_used="test",
                confidence_score=0.9,
                similarity_score=0.95,
            )
        ]

        service = ExtractionService(
            llm_port=mock_llm_port,
            prompt_manager=PromptManager(),
            task_parser=MagicMock(
                parse=MagicMock(return_value=[ParsedTask(summary="T", description="D")])
            ),
            extraction_repo=AsyncMock(),
            task_repo=AsyncMock(),
            vector_store=vector_store,
        )

        user_story = MagicMock()
        user_story.raw_text = "As a user, I want to log in"

        await service.extract(
            user_story,
            LLMConfig(model="test-model"),
            system_prompt="System prompt",
            instruction_template=None,
            workspace_id=uuid4(),
            few_shot_config=FewShotConfig(enabled=True, limit=3, threshold=0.85),
        )

        instruction_prompt = mock_llm_port.generate.call_args[0][0]
        assert "## Few-Shot Examples" in instruction_prompt
        assert "As a user, I want login" in instruction_prompt
        # The legacy "Style Reference" header is gone.
        assert "Style Reference" not in instruction_prompt

    @pytest.mark.asyncio
    async def test_extraction_disabled_omits_section(self, mock_llm_port) -> None:
        """Disabled few-shot config → no section, no search."""
        vector_store = AsyncMock()
        service = ExtractionService(
            llm_port=mock_llm_port,
            prompt_manager=PromptManager(),
            task_parser=MagicMock(parse=MagicMock(return_value=[])),
            extraction_repo=AsyncMock(),
            task_repo=AsyncMock(),
            vector_store=vector_store,
        )

        user_story = MagicMock()
        user_story.raw_text = "As a user, I want to log in"

        await service.extract(
            user_story,
            LLMConfig(model="test-model"),
            workspace_id=uuid4(),
            few_shot_config=FewShotConfig(enabled=False),
        )

        vector_store.search_similar.assert_not_called()
        instruction_prompt = mock_llm_port.generate.call_args[0][0]
        assert "## Few-Shot Examples" not in instruction_prompt


class TestPromptConfigRoundTrip:
    """PromptRequest/PromptResponse with the new few-shot config fields."""

    def test_request_accepts_config(self) -> None:
        request = PromptRequest(few_shot_enabled=False, few_shot_limit=5, few_shot_threshold=0.9)
        assert request.few_shot_enabled is False
        assert request.few_shot_limit == 5

    def test_response_exposes_config_defaults(self) -> None:
        response = PromptResponse()
        assert response.few_shot_enabled is True
        assert response.few_shot_limit == 3
        assert response.few_shot_threshold == 0.85

    def test_response_serializes_config(self) -> None:
        response = PromptResponse(few_shot_enabled=False, few_shot_limit=5, few_shot_threshold=0.9)
        data = response.model_dump()
        assert data["few_shot_enabled"] is False
        assert data["few_shot_limit"] == 5
        assert data["few_shot_threshold"] == 0.9
        assert "few_shot_examples" not in data
