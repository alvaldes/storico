"""Integration tests for Few-Shot Examples extraction flow."""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from storico.domain.ports import FewShotExample

from storico.domain.entities.few_shot import FewShotExample as FewShotExampleEntity
from storico.domain.services.extraction_service import ExtractionService
from storico.infrastructure.llm.prompt_manager import PromptManager
from storico.api.schemas.workspace_prompt import PromptRequest, PromptResponse


@pytest.fixture
def few_shot_examples():
    """Sample few-shot examples for testing."""
    return [
        {
            "user_story": "As a user, I want to log in so that I can access my account",
            "tasks": "1. summary: Set up auth database schema\ndescription: Create tables for users, sessions, and password hashes with proper indexes.\n\n2. summary: Implement login API endpoint\ndescription: Build POST /auth/login endpoint that validates credentials and returns JWT token.\n\n3. summary: Build login UI component\ndescription: Create React form with email/password fields, validation, and error handling.",
        },
        {
            "user_story": "As a user, I want to reset my password so that I can regain access",
            "tasks": "1. summary: Create password reset token model\ndescription: Add database table for reset tokens with expiration.\n\n2. summary: Implement forgot password endpoint\ndescription: Build POST /auth/forgot-password that sends reset email.\n\n3. summary: Build reset password page\ndescription: Create page with token validation and new password form.",
        },
    ]


class TestExtractionFlowWithFewShot:
    """Integration tests for the full extraction flow with few-shot examples."""

    @pytest.fixture
    def mock_llm_port(self):
        """Create a mock LLM port that returns predictable responses."""
        mock = AsyncMock()
        mock.generate = AsyncMock(return_value="""
1. summary: Set up authentication database
description: Create tables for users, sessions, and password hashes.

2. summary: Implement login endpoint
description: Build POST /auth/login with credential validation.

3. summary: Create login UI form
description: Build React form with email/password fields and validation.
""")
        return mock

    @pytest.fixture
    def prompt_manager(self):
        """Create a real PromptManager instance."""
        return PromptManager()

    @pytest.mark.asyncio
    async def test_extraction_includes_few_shot_in_prompt(
        self, mock_llm_port, prompt_manager, few_shot_examples
    ):
        """Test that extraction prompt includes few-shot examples section."""
        # Create a minimal extraction service
        service = ExtractionService(
            llm_port=mock_llm_port,
            prompt_manager=prompt_manager,
            task_parser=MagicMock(),
            extraction_repo=AsyncMock(),
            task_repo=AsyncMock(),
        )

        # Mock user story
        user_story = MagicMock()
        user_story.raw_text = "As a user, I want to log in so that I can access my account"

        # Mock task parser
        service._task_parser.parse = MagicMock(return_value=[
            MagicMock(summary="Task 1", description="Desc 1", labels=[], dependencies=[]),
        ])

        # Mock RAG to return no examples
        service._fetch_rag_examples = AsyncMock(return_value=[])

        # Run extraction with few-shot examples
        await service.extract(
            user_story=user_story,
            config=MagicMock(model="test-model", temperature=0.1, max_tokens=2048, timeout=120),
            system_prompt="System prompt",
            instruction_template=None,
            few_shot_examples=few_shot_examples,
        )

        # Verify LLM was called
        mock_llm_port.generate.assert_called_once()
        call_args = mock_llm_port.generate.call_args
        instruction_prompt = call_args[0][0]  # First positional arg

        # Verify few-shot section is in the prompt
        assert "## Few-Shot Examples (Style Reference)" in instruction_prompt
        assert "User Story: As a user, I want to log in so that I can access my account" in instruction_prompt
        assert "Tasks:" in instruction_prompt
        assert "1. summary: Set up auth database schema" in instruction_prompt
        assert "---" in instruction_prompt

    @pytest.mark.asyncio
    async def test_extraction_without_few_shot_omits_section(
        self, mock_llm_port, prompt_manager
    ):
        """Test that extraction without few-shot omits the section."""
        service = ExtractionService(
            llm_port=mock_llm_port,
            prompt_manager=prompt_manager,
            task_parser=MagicMock(),
            extraction_repo=AsyncMock(),
            task_repo=AsyncMock(),
        )

        user_story = MagicMock()
        user_story.raw_text = "Test story"
        service._task_parser.parse = MagicMock(return_value=[])
        service._fetch_rag_examples = AsyncMock(return_value=[])

        await service.extract(
            user_story=user_story,
            config=MagicMock(model="test-model", temperature=0.1, max_tokens=2048, timeout=120),
            system_prompt="System prompt",
            instruction_template=None,
            few_shot_examples=None,
        )

        call_args = mock_llm_port.generate.call_args
        instruction_prompt = call_args[0][0]

        assert "## Few-Shot Examples (Style Reference)" not in instruction_prompt

    @pytest.mark.asyncio
    async def test_extraction_with_empty_few_shot_list_omits_section(
        self, mock_llm_port, prompt_manager
    ):
        """Test that empty few-shot list omits the section."""
        service = ExtractionService(
            llm_port=mock_llm_port,
            prompt_manager=prompt_manager,
            task_parser=MagicMock(),
            extraction_repo=AsyncMock(),
            task_repo=AsyncMock(),
        )

        user_story = MagicMock()
        user_story.raw_text = "Test story"
        service._task_parser.parse = MagicMock(return_value=[])
        service._fetch_rag_examples = AsyncMock(return_value=[])

        await service.extract(
            user_story=user_story,
            config=MagicMock(model="test-model", temperature=0.1, max_tokens=2048, timeout=120),
            system_prompt="System prompt",
            instruction_template=None,
            few_shot_examples=[],
        )

        call_args = mock_llm_port.generate.call_args
        instruction_prompt = call_args[0][0]

        assert "## Few-Shot Examples (Style Reference)" not in instruction_prompt

    @pytest.mark.asyncio
    async def test_few_shot_order_before_rag(
        self, mock_llm_port, prompt_manager, few_shot_examples
    ):
        """Test few-shot section appears before RAG section."""
        service = ExtractionService(
            llm_port=mock_llm_port,
            prompt_manager=prompt_manager,
            task_parser=MagicMock(),
            extraction_repo=AsyncMock(),
            task_repo=AsyncMock(),
        )

        user_story = MagicMock()
        user_story.raw_text = "Target story"
        service._task_parser.parse = MagicMock(return_value=[])

        # Mock RAG to return examples
        rag_example = MagicMock()
        rag_example.user_story_text = "RAG story"
        rag_example.tasks_summary = "RAG tasks"
        rag_example.confidence_score = 0.9
        service._fetch_rag_examples = AsyncMock(return_value=[rag_example])

        await service.extract(
            user_story=user_story,
            config=MagicMock(model="test-model", temperature=0.1, max_tokens=2048, timeout=120),
            system_prompt="System prompt",
            instruction_template=None,
            few_shot_examples=few_shot_examples,
        )

        call_args = mock_llm_port.generate.call_args
        instruction_prompt = call_args[0][0]

        few_shot_pos = instruction_prompt.find("## Few-Shot Examples (Style Reference)")
        rag_pos = instruction_prompt.find("## Relevant Historical Examples")

        assert few_shot_pos != -1
        assert rag_pos != -1
        assert few_shot_pos < rag_pos


class TestPromptAPIRoundtrip:
    """Tests for API round-trip with few-shot examples."""

    def test_prompt_request_accepts_valid_examples(self, few_shot_examples):
        """Test PromptRequest validates and accepts valid examples."""
        request = PromptRequest(few_shot_examples=few_shot_examples)
        assert request.few_shot_examples is not None and len(request.few_shot_examples) == 2

    def test_prompt_request_serializes_correctly(self, few_shot_examples):
        """Test PromptRequest serializes to dict correctly."""
        request = PromptRequest(few_shot_examples=few_shot_examples)
        data = request.model_dump()

        assert "few_shot_examples" in data
        assert len(data["few_shot_examples"]) == 2
        assert data["few_shot_examples"][0]["user_story"] == few_shot_examples[0]["user_story"]

    def test_prompt_response_includes_examples(self, few_shot_examples):
        """Test PromptResponse includes few_shot_examples."""
        response = PromptResponse(
            system_prompt="System prompt",
            instruction_template="Template",
            few_shot_examples=few_shot_examples,
        )

        assert response.few_shot_examples is not None
        assert len(response.few_shot_examples) == 2


class TestPromptTemplateRendering:
    """Tests for template rendering with few-shot examples."""

    def test_template_with_custom_instruction_includes_few_shot(self):
        """Test that custom instruction templates also receive few-shot context."""
        pm = PromptManager()

        custom_template = """
Custom instruction for: {{user_story}}

{% if few_shot_examples %}
FEW_SHOT_PRESENT
{% endif %}
"""

        few_shot = [{"user_story": "Test", "tasks": "1. summary: Test\ndescription: Test desc"}]

        result = pm.render_instruction(custom_template, few_shot_examples=few_shot, user_story="Target")  # type: ignore[arg-type]

        assert "FEW_SHOT_PRESENT" in result

    def test_template_without_few_shot_renders_correctly(self):
        """Test template without few-shot renders correctly."""
        pm = PromptManager()

        custom_template = """
{% if few_shot_examples %}
HAS_FEW_SHOT
{% else %}
NO_FEW_SHOT
{% endif %}
"""

        result = pm.render_instruction(custom_template, few_shot_examples=None, user_story="Test")

        assert "NO_FEW_SHOT" in result
        assert "HAS_FEW_SHOT" not in result


if __name__ == "__main__":
    pytest.main([__file__, "-v"])