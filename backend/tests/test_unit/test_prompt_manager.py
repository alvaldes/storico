"""Unit tests for PromptManager — EXT-T19."""

import pytest

from storico.domain.entities import PromptTemplateNotFound
from storico.infrastructure.llm.prompt_manager import PromptManager


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
