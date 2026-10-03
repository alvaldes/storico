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


_OTHER_STORY_ID = "11111111-1111-1111-1111-111111111111"


def _context_variables() -> dict[str, object]:
    """The ``project_context`` shape ``render()`` hands the template (JSON-native).

    The same dictionary ``ProjectContext.as_template_variables()`` returns in
    production; built literally here so these cases stay template-only (no
    database, no service).
    """
    return {
        "name": "Payments Platform",
        "description": "Everything the money touches",
        "other_stories": [
            {
                "id": _OTHER_STORY_ID,
                "raw_text": "As a user, I want to reset my password so that I can log back in",
            }
        ],
        "existing_tasks": [
            {
                "user_story_id": _OTHER_STORY_ID,
                "title": "Add password reset endpoint",
                "status": "done",
            }
        ],
    }


class TestTaskGenerationContextBlocks:
    """task_generation.j2 carries the project context and negative-example blocks (WU1 1.5).

    Rendered-prompt cases only: the subject is what the default template does
    with the five ``template_variables`` entries, not who composed them.
    """

    def setup_method(self) -> None:
        self.manager = PromptManager()

    def _render(self, **overrides: object) -> str:
        """Render the default template with the full 0.9.0 variable set."""
        base: dict[str, object] = {
            "user_story": "As a user, I want to log in",
            "project_context": _context_variables(),
            "negative_examples": [],
            "negative_examples_omitted": 0,
            "few_shots": [],
        }
        base.update(overrides)
        return self.manager.render_instruction(None, **base)

    def test_the_context_block_carries_the_project(self) -> None:
        """The block names the project, its description, the other story and its tasks."""
        result = self._render()

        assert "## Project Context" in result
        assert "Payments Platform" in result
        assert "Everything the money touches" in result
        assert "As a user, I want to reset my password so that I can log back in" in result
        assert "Add password reset endpoint" in result
        # Each task is paired with the story it came from.
        assert f"(story: {_OTHER_STORY_ID})" in result

    def test_the_block_order_is_context_negative_few_shot_story(self) -> None:
        """Context, then the negative block, then few-shots, then the story."""
        result = self._render(
            negative_examples=[
                {"title": "Implement login retry", "reason": "duplicates", "version_number": 1}
            ],
            few_shots=[{"user_story_text": "Previous story"}],
            examples="Example 1:\nUser story: Previous story\nTasks:\n1. Task A",
        )

        context_at = result.index("## Project Context")
        negative_at = result.index("## Do Not Produce These Tasks (Previously Marked Invalid)")
        few_shot_at = result.index("## Few-Shot Examples")
        story_at = result.index("User story:")
        assert context_at < negative_at < few_shot_at < story_at

    def test_the_negative_block_lists_marks_and_announces_omissions(self) -> None:
        """Each mark reads ``- title — reason: reason (version N)`` and the omission is announced."""
        result = self._render(
            negative_examples=[
                {
                    "title": "Implement login retry",
                    "reason": "duplicates the auth task",
                    "version_number": 1,
                }
            ],
            negative_examples_omitted=2,
        )

        assert "## Do Not Produce These Tasks (Previously Marked Invalid)" in result
        assert "- Implement login retry — reason: duplicates the auth task (version 1)" in result
        assert "2 older marks were omitted." in result

    def test_no_negative_block_when_nothing_is_marked(self) -> None:
        """No marks (the WU1 production state) → the block and the sentence are absent."""
        result = self._render()

        assert "## Do Not Produce These Tasks (Previously Marked Invalid)" not in result
        assert "older marks were omitted" not in result

    def test_a_workspace_template_without_the_variables_renders_neither_block(self) -> None:
        """A template referencing only ``{{ user_story }}`` renders neither new block.

        C8's opt-out half: Jinja ignores the extra kwargs, so a workspace-authored
        template keeps the provider's input free of both blocks.
        """
        result = self.manager.render_instruction(
            "Story: {{user_story}}",
            user_story="As a user, I want to log in",
            project_context=_context_variables(),
            negative_examples=[],
            negative_examples_omitted=0,
            few_shots=[],
        )

        assert result == "Story: As a user, I want to log in"
        assert "## Project Context" not in result
        assert "## Do Not Produce These Tasks (Previously Marked Invalid)" not in result
