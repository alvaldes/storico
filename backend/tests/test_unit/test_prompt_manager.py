"""Unit tests for PromptManager — EXT-T19."""

import pytest

from storico.domain.entities import PromptTemplateNotFound
from storico.infrastructure.llm.prompt_manager import SYSTEM_PROMPT_TASK_GENERATION, PromptManager


class TestPromptManager:
    """PromptManager loads and renders Jinja2 prompt templates from the
    infrastructure/llm/prompts/ directory.
    """

    def setup_method(self) -> None:
        self.manager = PromptManager()

    # ── task_generation.j2 ──────────────────────────────────────────

    def test_render_task_generation(self) -> None:
        """Renders task_generation.j2 with a user story."""
        result = self.manager.render(
            "task_generation.j2",
            user_story="As a user, I want to log in so that I can access my account",
        )
        assert "As a user, I want to log in so that I can access my account" in result
        assert "summary:" in result
        assert "description:" in result
        # The template includes the formatting instructions
        assert "EXACTLY this format" in result

    def test_render_task_generation_custom_story(self) -> None:
        """Different user story content appears in rendered output."""
        result = self.manager.render(
            "task_generation.j2",
            user_story="As an admin, I want to manage users",
        )
        assert "As an admin, I want to manage users" in result

    # ── System prompt ───────────────────────────────────────────────

    def test_render_system_prompt(self) -> None:
        """System prompt returns the expected role string."""
        result = self.manager.render_system_prompt()
        assert "software development lead" in result
        assert "actionable development tasks" in result

    def test_render_system_prompt_matches_shared_constant(self) -> None:
        """render_system_prompt() returns the shared SYSTEM_PROMPT_TASK_GENERATION constant."""
        assert self.manager.render_system_prompt() == SYSTEM_PROMPT_TASK_GENERATION

    # ── Template source and inline instruction rendering ───────────

    def test_get_template_source_returns_raw_jinja(self) -> None:
        """Raw template source keeps its {{user_story}} placeholder intact."""
        source = self.manager.get_template_source("task_generation.j2")
        assert "{{user_story}}" in source
        assert "summary:" in source

    def test_get_template_source_unknown_template_raises(self) -> None:
        """Missing template raises PromptTemplateNotFound."""
        with pytest.raises(PromptTemplateNotFound):
            self.manager.get_template_source("missing.j2")

    def test_render_instruction_falls_back_to_j2_file(self) -> None:
        """None falls back to rendering the task_generation.j2 file."""
        result = self.manager.render_instruction(None, user_story="Story")
        assert "Story" in result
        assert "EXACTLY this format" in result

    def test_render_instruction_renders_db_template(self) -> None:
        """A DB template is rendered with Jinja2, interpolating placeholders."""
        result = self.manager.render_instruction(
            "Break down: {{user_story}}",
            user_story="As a user, I want X",
        )
        assert result == "Break down: As a user, I want X"

    def test_render_instruction_with_examples_kwarg(self) -> None:
        """DB template renders optional examples kwarg."""
        result = self.manager.render_instruction(
            "Story: {{user_story}}\nExamples:\n{{examples}}",
            user_story="S",
            examples="ex",
        )
        assert "Examples:\nex" in result

    # ── Judge prompt ────────────────────────────────────────────────

    def test_render_judge_prompt(self) -> None:
        """Renders judge prompt with story and tasks."""
        tasks = [{"summary": "Task 1", "description": "Desc 1"}]
        result = self.manager.render_judge_prompt(
            user_story="As a user, I want X",
            tasks=tasks,
        )
        assert "As a user, I want X" in result
        assert "Task 1" in result
        assert "total_score" in result

    def test_render_judge_prompt_multiple_tasks(self) -> None:
        """Multiple tasks are all included in the judge prompt."""
        tasks = [
            {"summary": "Task A", "description": "Desc A"},
            {"summary": "Task B", "description": "Desc B"},
            {"summary": "Task C", "description": "Desc C"},
        ]
        result = self.manager.render_judge_prompt(
            user_story="As a user, I want Y",
            tasks=tasks,
        )
        for t in tasks:
            assert t["summary"] in result

    def test_render_judge_prompt_custom_threshold(self) -> None:
        """Custom approval_threshold appears in rendered judge prompt."""
        tasks = [{"summary": "T", "description": "D"}]
        result = self.manager.render_judge_prompt(
            user_story="Story",
            tasks=tasks,
            approval_threshold=40,
        )
        assert "40" in result

    # ── Unknown template ────────────────────────────────────────────

    def test_unknown_template_raises_error(self) -> None:
        """Missing template should raise PromptTemplateNotFound."""
        with pytest.raises(PromptTemplateNotFound):
            self.manager.render("nonexistent.j2")

    def test_unknown_template_message_contains_name(self) -> None:
        """Error message includes the template name."""
        with pytest.raises(PromptTemplateNotFound) as exc_info:
            self.manager.render("missing_template.j2")
        assert "missing_template.j2" in str(exc_info.value)
