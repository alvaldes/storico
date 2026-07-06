"""PromptManager — loads and renders Jinja2 prompt templates."""

from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, FileSystemLoader, TemplateNotFound

from storico.domain.entities import PromptTemplateNotFound


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
        return (
            "You are an expert software development lead who excels at "
            "breaking down user stories into clear, actionable development tasks."
        )

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
