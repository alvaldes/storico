"""PromptManager — loads and renders Jinja2 prompt templates."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from jinja2 import Environment, FileSystemLoader, Template, TemplateNotFound

from storico.domain.entities import PromptTemplateNotFound

if TYPE_CHECKING:
    from storico.domain.ports import FewShotExample

# Shared system prompt for task generation. All LLM adapters (Ollama, Gemini)
# must send exactly this string as the system message so every model performs
# the extraction with the same expert role.
SYSTEM_PROMPT_TASK_GENERATION = (
    "You are an expert software development lead who excels at "
    "breaking down user stories into clear, actionable development tasks."
)


class PromptManager:
    """Manages prompt templates for LLM interaction.

    Loads Jinja2 templates from the ``infrastructure/llm/prompts/`` directory
    and renders them with provided context variables.

    Available templates:
        - ``task_generation.j2``: Instruction prompt for generating tasks.
        - ``single_judge.j2``: Judge prompt for evaluating generated tasks.
    """

    _PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"

    def __init__(self) -> None:
        self._env = Environment(
            loader=FileSystemLoader(str(self._PROMPTS_DIR)),
            autoescape=False,
        )

    def render(self, template_name: str, **kwargs: object) -> str:
        """Render a prompt template with the given keyword arguments.

        Args:
            template_name: Name of the template file (e.g. ``task_generation.j2``).
            **kwargs: Variables to pass to the template.

        Returns:
            Rendered prompt string.

        Raises:
            PromptTemplateNotFound: If the template file does not exist.
        """
        try:
            template = self._env.get_template(template_name)
            return template.render(**kwargs)
        except TemplateNotFound as e:
            raise PromptTemplateNotFound(template_name) from e

    def render_system_prompt(self) -> str:
        """Render the system prompt for task generation.

        Returns:
            The system prompt string describing the LLM's role.
        """
        return SYSTEM_PROMPT_TASK_GENERATION

    def get_template_source(self, template_name: str) -> str:
        """Return the raw source text of a prompt template.

        Used to seed the ``workspace_prompts.instruction_template`` column
        with the default instruction (``task_generation.j2``) so the file
        remains the single source of truth.

        Args:
            template_name: Name of the template file (e.g. ``task_generation.j2``).

        Returns:
            The template source as a string.

        Raises:
            PromptTemplateNotFound: If the template file does not exist.
        """
        try:
            source, _, _ = self._env.loader.get_source(  # type: ignore[union-attr]
                self._env, template_name
            )
            return source
        except TemplateNotFound as e:
            raise PromptTemplateNotFound(template_name) from e

    def render_instruction(
        self,
        instruction_template: str | None,
        few_shot_examples: list["FewShotExample"] | None = None,
        **kwargs: object,
    ) -> str:
        """Render the task-generation instruction prompt.

        When ``instruction_template`` is provided (e.g. a workspace override
        stored in ``workspace_prompts``), it is rendered with Jinja2 so its
        ``{{user_story}}``/``{{examples}}`` placeholders interpolate. When it
        is ``None``, falls back to rendering the ``task_generation.j2`` file.

        Args:
            instruction_template: Inline Jinja2 template text, or ``None`` to
                use the default ``task_generation.j2``.
            few_shot_examples: Optional few-shot examples for style reference.
            **kwargs: Variables to pass to the template.

        Returns:
            Rendered instruction prompt string.

        Raises:
            PromptTemplateNotFound: If the default template file is missing
                and no inline template was provided.
        """
        # Include few_shot_examples in template context if provided
        if few_shot_examples is not None:
            kwargs["few_shot_examples"] = few_shot_examples

        if instruction_template is None:
            return self.render("task_generation.j2", **kwargs)
        return Template(instruction_template).render(**kwargs)

    def render_judge_prompt(
        self,
        user_story: str,
        tasks: list[dict[str, object]],
        approval_threshold: int = 35,
    ) -> str:
        """Render the judge prompt for evaluating generated tasks.

        Args:
            user_story: The original user story text.
            tasks: List of task dicts with ``summary`` and ``description`` keys.
            approval_threshold: Minimum total score for approval (default 35).

        Returns:
            Rendered judge prompt string.

        Raises:
            PromptTemplateNotFound: If the ``single_judge.j2`` template is missing.
        """
        return self.render(
            "single_judge.j2",
            user_story=user_story,
            tasks=tasks,
            approval_threshold=approval_threshold,
        )
