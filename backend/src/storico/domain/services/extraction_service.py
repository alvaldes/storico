"""ExtractionService — domain orchestrator for LLM-based task extraction."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from uuid import UUID

from storico.domain.entities import Extraction, ParseError, Task
from storico.domain.entities.exceptions import LLMError
from storico.domain.entities.extraction import ExtractionStatus
from storico.domain.entities.user_story import UserStoryStatus
from storico.domain.ports import (
    ExtractionExample,
    ExtractionRepository,
    LLMConfig,
    LLMPort,
    ParsedTask,
    TaskRepository,
    VectorStorePort,
)
from storico.infrastructure.llm.prompt_manager import PromptManager
from storico.infrastructure.llm.task_parser import TaskParser

from .extraction_judge_service import LLMJudgeService

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


class ExtractionService:
    """Orchestrates the full extraction pipeline.

    Flow:
        1. Render the instruction prompt from the workspace-configured
           template (system prompt and instruction template are resolved
           upstream, never chosen by the service).
        2. Optionally retrieve few-shot examples from the vector store,
           workspace-scoped, when ``few_shot_config.enabled`` is true.
        3. Call the LLM via ``LLMPort`` with the system prompt delivered
           separately.
        4. Parse the raw response into ``ParsedTask`` objects.
        5. Persist the ``Extraction`` (completed or failed) + ``Task`` entities.
        6. Optionally validate results via ``LLMJudgeService``.
        7. Optionally store extraction in vector store for future retrieval.
        8. Return the extraction entity.
    """

    def __init__(
        self,
        llm_port: LLMPort,
        prompt_manager: PromptManager,
        task_parser: TaskParser,
        extraction_repo: ExtractionRepository,
        task_repo: TaskRepository,
        judge_service: LLMJudgeService | None = None,
        vector_store: VectorStorePort | None = None,
        few_shot_config: FewShotConfig | None = None,
    ) -> None:
        self._llm = llm_port
        self._prompt_manager = prompt_manager
        self._task_parser = task_parser
        self._extraction_repo = extraction_repo
        self._task_repo = task_repo
        self._judge_service = judge_service
        self._vector_store = vector_store
        self._few_shot_config = few_shot_config or FewShotConfig()

    async def extract(
        self,
        user_story: object,
        config: LLMConfig,
        system_prompt: str | None = None,
        instruction_template: str | None = None,
        workspace_id: UUID | None = None,
        few_shot_config: FewShotConfig | None = None,
    ) -> tuple[list[ParsedTask], str]:
        """Run the extraction pipeline (prompt → LLM → parse) without persistence.

        The system prompt and instruction template are resolved upstream
        (workspace prompt config) and passed in — the service never decides
        which prompts to use, it only renders and sends them.

        Few-shot examples are retrieved from the vector store, scoped to
        ``workspace_id``, when the resolved ``few_shot_config.enabled`` is true.
        When disabled, a cold start, or a search failure yields no examples, the
        examples section is omitted (instruction-only prompt).

        Args:
            user_story: A domain entity with a ``raw_text`` attribute.
            config: LLM configuration to use for generation.
            system_prompt: Workspace system prompt. Passed separately to the
                LLM port (``None`` sends no system message).
            instruction_template: Workspace instruction template (Jinja2
                text). ``None`` falls back to ``task_generation.j2``.
            workspace_id: Workspace the extraction belongs to (for scoped
                retrieval and storage).
            few_shot_config: Workspace few-shot retrieval config. ``None``
                falls back to the service-level default.

        Returns:
            Tuple of (parsed_tasks, raw_response).

        Raises:
            LLMError: If the LLM call fails.
            ParseError: If the response cannot be parsed.
        """
        raw_text = getattr(user_story, "raw_text", str(user_story))

        resolved_config = few_shot_config or self._few_shot_config

        # Retrieve workspace-scoped few-shot examples (best-effort)
        examples = await self._fetch_rag_examples(raw_text, workspace_id, resolved_config)

        # Render with or without examples
        prompt_kwargs: dict[str, object] = {"user_story": raw_text}
        if examples:
            prompt_kwargs["examples"] = self._format_examples(examples)

        instruction_prompt = self._prompt_manager.render_instruction(
            instruction_template,
            **prompt_kwargs,
        )

        # 2. Call LLM
        try:
            raw_response = await self._llm.generate(
                instruction_prompt,
                config,
                system_prompt=system_prompt,
            )
        except LLMError:
            raise
        except Exception as exc:
            raise LLMError(f"Unexpected error during LLM generation: {exc}") from exc

        # 3. Parse response
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

    async def extract_and_persist(
        self,
        user_story: object,
        config: LLMConfig,
        prompt_config: dict | None = None,
        system_prompt: str | None = None,
        instruction_template: str | None = None,
        workspace_id: UUID | None = None,
        few_shot_config: FewShotConfig | None = None,
    ) -> Extraction:
        """Run the full extraction pipeline and persist results.

        Creates an ``Extraction`` entity (status ``completed`` or ``failed``)
        and ``Task`` entities for each parsed task.

        Args:
            user_story: Domain entity with ``raw_text``, ``id`` attributes.
            config: LLM configuration.
            prompt_config: Optional metadata about the prompts used.
            system_prompt: Workspace system prompt, forwarded to ``extract``
                and the judge service.
            instruction_template: Workspace instruction template (Jinja2
                text), forwarded to ``extract``.
            workspace_id: Workspace the extraction belongs to (for scoped
                retrieval and vector storage).
            few_shot_config: Workspace few-shot retrieval config.

        Returns:
            The persisted ``Extraction`` entity.
        """
        story_id = getattr(user_story, "id", None)

        try:
            parsed_tasks, raw_response = await self.extract(
                user_story,
                config,
                system_prompt=system_prompt,
                instruction_template=instruction_template,
                workspace_id=workspace_id,
                few_shot_config=few_shot_config,
            )

            # Determine confidence from optional judge
            confidence: float | None = None
            if self._judge_service is not None:
                try:
                    judge_result = await self._judge_service.validate(
                        user_story=getattr(user_story, "raw_text", str(user_story)),
                        tasks=[
                            {"summary": pt.summary, "description": pt.description}
                            for pt in parsed_tasks
                        ],
                        config=config,
                        system_prompt=system_prompt,
                    )
                    confidence = judge_result.total_score / 50.0
                    if not judge_result.approved and confidence is not None and confidence > 0.5:
                        confidence = 0.5
                except LLMError as exc:
                    # Judge failure should not break extraction, but log it explicitly
                    logger.warning(
                        "LLM judge validation failed, skipping confidence scoring",
                        extra={"error": str(exc), "error_type": type(exc).__name__},
                    )

            # 4. Persist Extraction (completed)
            effective_prompt_config = prompt_config or {}
            if story_id is None:
                raise LLMError("User story ID is required for extraction persistence")
            extraction = Extraction(
                user_story_id=story_id,
                model_used=config.model,
                raw_response=raw_response,
                status=ExtractionStatus.COMPLETED,
                user_story_status=UserStoryStatus.EXTRACTED,
                prompt_config=effective_prompt_config,
                confidence_score=confidence,
            )
            extraction = await self._extraction_repo.save(extraction)

            # 5. Persist Task entities
            for pt in parsed_tasks:
                task = Task(
                    user_story_id=story_id,
                    title=pt.summary,
                    description=pt.description,
                    labels=list(pt.labels),
                    dependencies=list(pt.dependencies),
                )
                await self._task_repo.save(task)

            # 6. Store in vector store for future few-shot retrieval
            await self._store_rag(user_story, extraction, parsed_tasks, workspace_id)

            return extraction

        except (LLMError, ParseError) as exc:
            # Persist failed extraction with error info
            if story_id is None:
                logger.error(
                    "Cannot persist failed extraction: user_story_id is None",
                    extra={"error": str(exc)},
                )
                raise
            extraction = Extraction(
                user_story_id=story_id,
                model_used=config.model,
                raw_response="",
                status=ExtractionStatus.FAILED,
                user_story_status=UserStoryStatus.FAILED_EXTRACTION,
                error_info=str(exc),
                prompt_config=prompt_config,
            )
            return await self._extraction_repo.save(extraction)

    async def _store_rag(
        self,
        user_story: object,
        extraction: Extraction,
        parsed_tasks: list[ParsedTask],
        workspace_id: UUID | None,
    ) -> None:
        """Store extraction in vector store for future few-shot retrieval."""
        if self._vector_store is None:
            logger.debug("Vector store skipped: no vector store configured")
            return
        if workspace_id is None:
            logger.debug("Vector store skipped: no workspace_id supplied")
            return
        try:
            tasks_summary = "\n".join(
                f"{i + 1}. {t.summary}: {t.description}" for i, t in enumerate(parsed_tasks)
            )
            await self._vector_store.store_extraction(
                extraction_id=str(extraction.id),
                user_story_text=getattr(user_story, "raw_text", str(user_story)),
                tasks_summary=tasks_summary,
                model_used=extraction.model_used,
                workspace_id=workspace_id,
                confidence_score=extraction.confidence_score,
                user_story_id=str(getattr(user_story, "id", "")),
            )
        except Exception as exc:
            logger.warning(
                "Vector store failed, extraction already saved in database",
                extra={
                    "error": str(exc),
                    "error_type": type(exc).__name__,
                    "extraction_id": str(extraction.id),
                },
            )
