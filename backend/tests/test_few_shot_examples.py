"""Unit tests for Few-Shot Examples feature."""

from __future__ import annotations

import pytest
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from storico.domain.ports import FewShotExample
from uuid import uuid4

from storico.domain.entities.few_shot import FewShotExample as FewShotExampleEntity
from storico.domain.services.extraction_service import ExtractionService
from storico.infrastructure.llm.prompt_manager import PromptManager
from storico.api.schemas.workspace_prompt import FewShotExample as PydanticFewShotExample, PromptRequest


class TestFewShotExampleFormatting:
    """Tests for formatting few-shot examples for prompt injection."""

    def test_format_few_shot_single_example(self):
        """Test formatting a single few-shot example."""
        examples: list[FewShotExampleEntity] = [
            {
                "user_story": "As a user, I want to log in so that I can access my account",
                "tasks": "1. summary: Set up auth database schema\ndescription: Create tables for users and sessions.",
            }
        ]

        # Create a minimal service instance (we only need the formatting method)
        service = ExtractionService.__new__(ExtractionService)
        formatted = service._format_few_shot(examples)

        assert "User Story: As a user, I want to log in" in formatted
        assert "Tasks:\n1. summary: Set up auth database schema" in formatted
        assert formatted.strip().endswith("---")

    def test_format_few_shot_multiple_examples(self):
        """Test formatting multiple few-shot examples with separators."""
        examples: list[FewShotExampleEntity] = [
            {
                "user_story": "As a user, I want to log in",
                "tasks": "1. summary: Task 1\ndescription: Desc 1",
            },
            {
                "user_story": "As an admin, I want to manage users",
                "tasks": "1. summary: Task A\ndescription: Desc A",
            },
        ]

        service = ExtractionService.__new__(ExtractionService)
        formatted = service._format_few_shot(examples)

        # Both examples should be present
        assert "User Story: As a user, I want to log in" in formatted
        assert "User Story: As an admin, I want to manage users" in formatted
        # Should have separator between examples
        assert formatted.count("---") == 2

    def test_format_few_shot_empty_list(self):
        """Test formatting empty list returns empty string."""
        service = ExtractionService.__new__(ExtractionService)
        formatted = service._format_few_shot([])
        assert formatted == ""


class TestPromptManagerFewShot:
    """Tests for PromptManager handling of few_shot_examples."""

    def test_render_instruction_includes_few_shot_in_context(self):
        """Test that few_shot_examples are passed to template context."""
        pm = PromptManager()

        few_shot = [
            {"user_story": "Test story", "tasks": "1. summary: Test\ndescription: Test desc"}
        ]  # type: ignore[list-item]

        # Use a simple template that shows few_shot_examples
        template = "{% if few_shot_examples %}HAS_FEW_SHOT{% else %}NO_FEW_SHOT{% endif %}"

        result = pm.render_instruction(template, few_shot_examples=few_shot, user_story="test")  # type: ignore[arg-type]

        assert "HAS_FEW_SHOT" in result
        assert "NO_FEW_SHOT" not in result

    def test_render_instruction_without_few_shot(self):
        """Test that missing few_shot_examples doesn't break rendering."""
        pm = PromptManager()

        template = "{% if few_shot_examples %}HAS_FEW_SHOT{% else %}NO_FEW_SHOT{% endif %}"

        result = pm.render_instruction(template, few_shot_examples=None, user_story="test")

        assert "NO_FEW_SHOT" in result
        assert "HAS_FEW_SHOT" not in result

    def test_render_instruction_with_empty_few_shot_list(self):
        """Test that empty few_shot_examples list is treated as falsy."""
        pm = PromptManager()

        template = "{% if few_shot_examples %}HAS_FEW_SHOT{% else %}NO_FEW_SHOT{% endif %}"

        result = pm.render_instruction(template, few_shot_examples=[], user_story="test")

        assert "NO_FEW_SHOT" in result


class TestPromptTemplateFewShot:
    """Tests for the task_generation.j2 template with few-shot examples."""

    def test_template_renders_few_shot_section_when_provided(self):
        """Test template includes few-shot section when examples provided."""
        pm = PromptManager()

        few_shot = [
            {"user_story": "As a user, I want to log in", "tasks": "1. summary: Setup\ndescription: Create tables"}
        ]  # type: ignore[list-item]

        # Render the actual task_generation template
        result = pm.render_instruction(
            None,  # use default template
            few_shot_examples=few_shot,
            user_story="As a user, I want to reset password",
            examples=None,
        )  # type: ignore[arg-type]

        assert "## Few-Shot Examples (Style Reference)" in result
        assert "User Story: As a user, I want to log in" in result
        assert "Tasks:\n1. summary: Setup\ndescription: Create tables" in result
        assert "---" in result

    def test_template_omits_few_shot_section_when_none(self):
        """Test template omits few-shot section when no examples."""
        pm = PromptManager()

        result = pm.render_instruction(
            None,
            few_shot_examples=None,
            user_story="As a user, I want to reset password",
            examples=None,
        )

        assert "## Few-Shot Examples (Style Reference)" not in result

    def test_template_omits_few_shot_section_when_empty_list(self):
        """Test template omits few-shot section when empty list."""
        pm = PromptManager()

        result = pm.render_instruction(
            None,
            few_shot_examples=[],
            user_story="As a user, I want to reset password",
            examples=None,
        )

        assert "## Few-Shot Examples (Style Reference)" not in result

    def test_template_orders_few_shot_before_rag(self):
        """Test few-shot section appears before RAG section."""
        pm = PromptManager()

        few_shot = [{"user_story": "FS story", "tasks": "1. summary: FS\ndescription: FS tasks"}]  # type: ignore[list-item]
        rag_examples = [{"user_story_text": "RAG story", "tasks_summary": "RAG tasks", "confidence_score": 0.9}]

        result = pm.render_instruction(
            None,
            few_shot_examples=few_shot,
            user_story="Target story",
            examples=[{"user_story_text": "RAG story", "tasks_summary": "RAG tasks", "confidence_score": 0.9}],
        )  # type: ignore[arg-type]

        few_shot_pos = result.find("## Few-Shot Examples (Style Reference)")
        rag_pos = result.find("## Relevant Historical Examples")

        assert few_shot_pos != -1
        assert rag_pos != -1
        assert few_shot_pos < rag_pos  # Few-shot comes first


class TestPydanticFewShotValidation:
    """Tests for Pydantic schema validation."""

    def test_valid_few_shot_example(self):
        """Test valid few-shot example passes validation."""
        example = PydanticFewShotExample(
            user_story="As a user, I want to log in so that I can access my account",
            tasks="1. summary: Set up auth\ndescription: Create user and session tables with proper indexes.",
        )
        assert example.user_story.startswith("As a user")
        assert "summary:" in example.tasks

    def test_user_story_too_short(self):
        """Test user_story with < 10 chars fails validation."""
        with pytest.raises(ValueError, match="at least 10 characters"):
            PydanticFewShotExample(
                user_story="Short",
                tasks="1. summary: Test\ndescription: Test description here",
            )

    def test_tasks_too_short(self):
        """Test tasks with < 20 chars fails validation."""
        with pytest.raises(ValueError, match="at least 20 characters"):
            PydanticFewShotExample(
                user_story="As a user, I want to log in",
                tasks="Too short",
            )

    def test_prompt_request_max_3_examples(self):
        """Test PromptRequest rejects more than 3 examples."""
        examples = [
            PydanticFewShotExample(user_story="As a user, I want feature A", tasks="1. summary: A\ndescription: Desc A"),
            PydanticFewShotExample(user_story="As a user, I want feature B", tasks="1. summary: B\ndescription: Desc B"),
            PydanticFewShotExample(user_story="As a user, I want feature C", tasks="1. summary: C\ndescription: Desc C"),
            PydanticFewShotExample(user_story="As a user, I want feature D", tasks="1. summary: D\ndescription: Desc D"),
        ]
        with pytest.raises(ValueError, match="at most 3 items"):
            PromptRequest(few_shot_examples=examples)

    def test_prompt_request_accepts_3_examples(self):
        """Test PromptRequest accepts exactly 3 examples."""
        examples = [
            PydanticFewShotExample(user_story="As a user, I want feature A", tasks="1. summary: A\ndescription: Desc A"),
            PydanticFewShotExample(user_story="As a user, I want feature B", tasks="1. summary: B\ndescription: Desc B"),
            PydanticFewShotExample(user_story="As a user, I want feature C", tasks="1. summary: C\ndescription: Desc C"),
        ]
        request = PromptRequest(few_shot_examples=examples)
        assert request.few_shot_examples is not None and len(request.few_shot_examples) == 3

    def test_prompt_request_accepts_none(self):
        """Test PromptRequest accepts None for few_shot_examples."""
        request = PromptRequest(few_shot_examples=None)
        assert request.few_shot_examples is None

    def test_prompt_request_accepts_empty_list(self):
        """Test PromptRequest accepts empty list."""
        request = PromptRequest(few_shot_examples=[])
        assert request.few_shot_examples == []


class TestExtractionServiceExtractWithFewShot:
    """Tests for ExtractionService.extract() with few_shot_examples parameter."""

    def test_extract_accepts_few_shot_examples_param(self):
        """Test extract() method signature accepts few_shot_examples."""
        import inspect
        sig = inspect.signature(ExtractionService.extract)
        params = list(sig.parameters.keys())
        assert "few_shot_examples" in params

    def test_extract_few_shot_examples_default_none(self):
        """Test few_shot_examples defaults to None."""
        import inspect
        sig = inspect.signature(ExtractionService.extract)
        param = sig.parameters["few_shot_examples"]
        assert param.default is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])