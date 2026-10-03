"""ExtractionService — domain orchestrator for LLM-based task extraction."""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING
from uuid import UUID

from storico.domain.entities.exceptions import LLMError
from storico.domain.entities.task import TaskStatus
from storico.domain.ports import (
    ExtractionExample,
    LLMConfig,
    LLMPort,
    ParsedTask,
    StoryContextRow,
    TaskContextRow,
    VectorStorePort,
)
from storico.infrastructure.llm.prompt_manager import PromptManager
from storico.infrastructure.llm.task_parser import TaskParser

from .extraction_judge_service import LLMJudgeService

if TYPE_CHECKING:
    # WU2 lands this module with the negative-example composer; the field is
    # always empty until then, so the runtime annotation stays a string.
    from storico.domain.services.negative_examples import NegativeExample

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class FewShotConfig:
    """Configuration for automatic few-shot retrieval from the vector store.

    Replaces the previous global RAG settings and the manual ``few_shot_examples``
    input. ``limit`` and ``threshold`` are resolved per workspace.
    """

    enabled: bool = True
    limit: int = 3
    threshold: float = 0.85


@dataclass(frozen=True, slots=True)
class ProjectContext:
    """The project state one prompt render is composed from.

    Built by the runner between the story load and the ``render()`` call from
    the project row and the two unbounded context reads; consumed by
    ``render()`` as one value so this service stays repository-free. Every
    value that reaches ``as_template_variables()`` is JSON-native, because the
    same dictionary is what ``RenderedPrompt.template_variables`` carries and
    what the version's snapshot records.
    """

    name: str  # project name at render time
    description: str  # description at render time
    other_stories: tuple[StoryContextRow, ...]  # the project's OTHER stories, id + raw_text
    existing_tasks: tuple[TaskContextRow, ...]  # current-version, valid tasks only
    negative_examples: tuple[NegativeExample, ...] = ()  # composed by WU2; empty until then
    negative_examples_omitted: int = 0

    def as_template_variables(self) -> dict[str, object]:
        """Project the context into the JSON-native shape the template reads.

        The boundary conversion: ``UUID → str`` and ``TaskStatus → str`` happen
        here and nowhere else, so everything that reaches the template and the
        snapshot is directly serializable.
        """
        return {
            "name": self.name,
            "description": self.description,
            "other_stories": [
                {"id": str(story.id), "raw_text": story.raw_text} for story in self.other_stories
            ],
            "existing_tasks": [
                {
                    "user_story_id": str(task.user_story_id),
                    "title": task.title,
                    "status": (
                        task.status.value
                        if isinstance(task.status, TaskStatus)
                        else str(task.status)
                    ),
                }
                for task in self.existing_tasks
            ],
        }


@dataclass(frozen=True, slots=True)
class RenderedPrompt:
    """The composed prompt as it left the renderer, frozen before the provider is asked.

    ``text`` is the one definition of "the composed text the provider received, system
    block included" — the value the runner snapshots into ``prompt_rendered`` between
    ``render()`` and ``generate()``, so the column and the call it documents cannot
    drift. ``template_variables`` carries exactly the kwargs ``render_instruction`` was
    called with (``{"user_story": ...}`` today; slice (c) reads it to fill the
    ``prompt_config`` context keys without widening the render signature).
    """

    instruction: str
    system_prompt: str | None
    template_variables: dict[str, object]

    @property
    def text(self) -> str:
        return (self.system_prompt or "") + "\n\n" + self.instruction


class ExtractionService:
    """Orchestrates prompt rendering and LLM generation for task extraction.

    Flow:
        1. Render the instruction prompt from the workspace-configured
           template (system prompt and instruction template are resolved
           upstream, never chosen by the service).
        2. Optionally retrieve few-shot examples from the vector store,
           workspace-scoped, when ``few_shot_config.enabled`` is true.
        3. Call the LLM via ``LLMPort`` with the system prompt delivered
           separately.
        4. Parse the raw response into ``ParsedTask`` objects.

    Persistence is not this service's job: ``run_background_extraction``
    (infrastructure/tasks/extraction_task.py) owns the render-time snapshot,
    the terminal marks, and the task and vector-store writes around these two
    calls.
    """

    def __init__(
        self,
        llm_port: LLMPort,
        prompt_manager: PromptManager,
        task_parser: TaskParser,
        judge_service: LLMJudgeService | None = None,
        vector_store: VectorStorePort | None = None,
        few_shot_config: FewShotConfig | None = None,
    ) -> None:
        self._llm = llm_port
        self._prompt_manager = prompt_manager
        self._task_parser = task_parser
        self._judge_service = judge_service
        self._vector_store = vector_store
        self._few_shot_config = few_shot_config or FewShotConfig()

    async def render(
        self,
        user_story: object,
        *,
        system_prompt: str | None = None,
        instruction_template: str | None = None,
        workspace_id: UUID | None = None,
        few_shot_config: FewShotConfig | None = None,
        context: ProjectContext,
    ) -> RenderedPrompt:
        """Compose the prompt the provider will receive, without contacting it.

        The system prompt and instruction template are resolved upstream
        (workspace prompt config) and passed in — the service never decides
        which prompts to use, it only renders them.

        Few-shot examples are retrieved from the vector store, scoped to
        ``workspace_id``, when the resolved ``few_shot_config.enabled`` is true.
        When disabled, a cold start, or a search failure yields no examples, the
        examples section is omitted (instruction-only prompt).

        Args:
            user_story: A domain entity with a ``raw_text`` attribute.
            system_prompt: Workspace system prompt (``None`` sends no system message).
            instruction_template: Workspace instruction template (Jinja2
                text). ``None`` falls back to ``task_generation.j2``.
            workspace_id: Workspace the extraction belongs to (for scoped retrieval).
            few_shot_config: Workspace few-shot retrieval config. ``None``
                falls back to the service-level default.
            context: The project state this prompt is composed from — required,
                with no default: a caller able to omit it could render the
                two-variable prompt of 0.8.0 while the row claimed to be a
                0.9.0 version. The type carries the requirement.

        Returns:
            The frozen ``RenderedPrompt`` — ``text`` is what the provider receives.
        """
        raw_text = getattr(user_story, "raw_text", str(user_story))

        resolved_config = few_shot_config or self._few_shot_config

        # Retrieve workspace-scoped few-shot examples (best-effort)
        examples = await self._fetch_rag_examples(raw_text, workspace_id, resolved_config)

        if examples:
            # Observability only: numbers and the workspace id, never user
            # content (story text, task summaries, rendered prompt).
            logger.info(
                "Few-shot examples injected from the vector store",
                extra={
                    "workspace_id": str(workspace_id),
                    "examples_count": len(examples),
                    "limit": resolved_config.limit,
                    "threshold": resolved_config.threshold,
                    "similarity_scores": [
                        round(example.similarity_score, 4) for example in examples
                    ],
                },
            )

        # Render with or without examples. ``prompt_kwargs`` IS
        # ``RenderedPrompt.template_variables``: the same dictionary the
        # template receives is what the snapshot records, so the two cannot
        # drift. ``negative_examples`` is rendered, never snapshotted — the
        # block itself is in ``prompt_rendered`` and re-derivable from the
        # marks; WU2 replaces the raw list with the composed rendering.
        prompt_kwargs: dict[str, object] = {
            "user_story": raw_text,
            "project_context": context.as_template_variables(),
            "negative_examples": list(context.negative_examples),
            "negative_examples_omitted": context.negative_examples_omitted,
            "few_shots": [asdict(example) for example in examples],
        }
        if examples:
            prompt_kwargs["examples"] = self._format_examples(examples)

        instruction_prompt = self._prompt_manager.render_instruction(
            instruction_template,
            **prompt_kwargs,
        )

        return RenderedPrompt(
            instruction=instruction_prompt,
            system_prompt=system_prompt,
            template_variables=prompt_kwargs,
        )

    async def generate(
        self,
        rendered: RenderedPrompt,
        config: LLMConfig,
    ) -> tuple[list[ParsedTask], str]:
        """Send a rendered prompt to the LLM and parse the answer.

        Args:
            rendered: The frozen prompt returned by ``render()``.
            config: LLM configuration to use for generation.

        Returns:
            Tuple of (parsed_tasks, raw_response).

        Raises:
            LLMError: If the LLM call fails.
            ParseError: If the response cannot be parsed.
        """
        try:
            raw_response = await self._llm.generate(
                rendered.instruction,
                config,
                system_prompt=rendered.system_prompt,
            )
        except LLMError:
            raise
        except Exception as exc:
            raise LLMError(f"Unexpected error during LLM generation: {exc}") from exc

        parsed_tasks = self._task_parser.parse(raw_response)

        return parsed_tasks, raw_response

    async def _fetch_rag_examples(
        self,
        text: str,
        workspace_id: UUID | None,
        few_shot_config: FewShotConfig,
    ) -> list[ExtractionExample]:
        """Search for similar past extractions, workspace-scoped and best-effort.

        Returns an empty list when retrieval is disabled, no vector store is
        configured, the extraction has no workspace scope, or the search fails
        — extraction never fails on retrieval.
        """
        if not few_shot_config.enabled:
            logger.debug("Few-shot retrieval disabled, skipping search")
            return []
        if self._vector_store is None:
            logger.debug("Few-shot retrieval disabled: no vector store configured")
            return []
        if workspace_id is None:
            # Fail closed. An unscoped lookup would reach every workspace, so
            # other workspaces' user stories would leak into this prompt.
            # Skipping retrieval is strictly better than widening the search.
            logger.warning(
                "Few-shot retrieval skipped: extraction has no workspace scope",
                extra={"reason": "missing_workspace_id"},
            )
            return []
        try:
            return await self._vector_store.search_similar(
                text=text,
                limit=few_shot_config.limit,
                threshold=few_shot_config.threshold,
                workspace_id=workspace_id,
            )
        except Exception as exc:
            logger.warning(
                "Few-shot retrieval failed, proceeding without examples",
                extra={"error": str(exc), "error_type": type(exc).__name__},
            )
            return []

    def _format_examples(self, examples: list[ExtractionExample]) -> str:
        """Format extraction examples for injection into the prompt template."""
        blocks: list[str] = []
        for i, ex in enumerate(examples, start=1):
            confidence = f" (confidence: {ex.confidence_score:.2f})" if ex.confidence_score else ""
            blocks.append(
                f"Example {i}:{confidence}\n"
                f"User story: {ex.user_story_text}\n"
                f"Tasks:\n{ex.tasks_summary}"
            )
        return "\n\n".join(blocks)
