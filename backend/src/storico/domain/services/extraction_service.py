"""ExtractionService — domain orchestrator for LLM-based task extraction."""

from __future__ import annotations

import logging

from dataclasses import dataclass

from storico.domain.entities import Extraction, ParseError, Task
from storico.domain.entities.exceptions import LLMError
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
class RAGConfig:
    """Configuration for RAG (Retrieval-Augmented Generation) behavior."""

    max_examples: int = 3
    similarity_threshold: float = 0.85


class ExtractionService:
    """Orchestrates the full extraction pipeline.

    Flow:
        1. Render system + task-generation prompts from the user story.
        2. Optionally inject RAG examples from past extractions.
        3. Call the LLM via ``LLMPort``.
        4. Parse the raw response into ``ParsedTask`` objects.
        5. Persist the ``Extraction`` (completed or failed) + ``Task`` entities.
        6. Optionally validate results via ``LLMJudgeService``.
        7. Optionally store extraction in vector store for future RAG.
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
        rag_config: RAGConfig | None = None,
    ) -> None:
        self._llm = llm_port
        self._prompt_manager = prompt_manager
        self._task_parser = task_parser
        self._extraction_repo = extraction_repo
        self._task_repo = task_repo
        self._judge_service = judge_service
        self._vector_store = vector_store
        self._rag_config = rag_config or RAGConfig()

    async def extract(
        self,
        user_story: object,
        config: LLMConfig,
    ) -> tuple[list[ParsedTask], str]:
        """Run the extraction pipeline (prompt → LLM → parse) without persistence.

        Args:
            user_story: A domain entity with a ``raw_text`` attribute.
            config: LLM configuration to use for generation.

        Returns:
            Tuple of (parsed_tasks, raw_response).

        Raises:
            LLMError: If the LLM call fails.
            ParseError: If the response cannot be parsed.
        """
        # 1. Render prompts
        system_prompt = self._prompt_manager.render_system_prompt()
        raw_text = getattr(user_story, "raw_text", str(user_story))

        # RAG: search for similar past extractions
        examples = await self._fetch_rag_examples(raw_text)

        # Render with or without examples
        prompt_kwargs: dict[str, object] = {"user_story": raw_text}
        if examples:
            prompt_kwargs["examples"] = self._format_examples(examples)

        instruction_prompt = self._prompt_manager.render(
            "task_generation.j2",
            **prompt_kwargs,
        )
        full_prompt = f"{system_prompt}\n\n{instruction_prompt}"

        # 2. Call LLM
        try:
            raw_response = await self._llm.generate(full_prompt, config)
        except LLMError:
            raise
        except Exception as exc:
            raise LLMError(f"Unexpected error during LLM generation: {exc}") from exc

        # 3. Parse response
        parsed_tasks = self._task_parser.parse(raw_response)

        return parsed_tasks, raw_response

    async def _fetch_rag_examples(self, text: str) -> list[ExtractionExample]:
        """Search for similar past extractions. Returns empty list on failure."""
        if self._vector_store is None:
            return []
        try:
            return await self._vector_store.search_similar(
                text=text,
                limit=self._rag_config.max_examples,
                threshold=self._rag_config.similarity_threshold,
            )
        except Exception:
            logger.warning("RAG search failed, proceeding without examples")
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
    ) -> Extraction:
        """Run the full extraction pipeline and persist results.

        Creates an ``Extraction`` entity (status ``completed`` or ``failed``)
        and ``Task`` entities for each parsed task.

        Args:
            user_story: Domain entity with ``raw_text``, ``id`` attributes.
            config: LLM configuration.
            prompt_config: Optional metadata about the prompts used.

        Returns:
            The persisted ``Extraction`` entity.
        """
        story_id = getattr(user_story, "id", None)

        try:
            parsed_tasks, raw_response = await self.extract(user_story, config)

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
                    )
                    confidence = judge_result.total_score / 50.0
                    if not judge_result.approved and confidence is not None and confidence > 0.5:
                        confidence = 0.5
                except LLMError:
                    # Judge failure should not break extraction
                    pass

            # 4. Persist Extraction (completed)
            effective_prompt_config = prompt_config or {}
            extraction = Extraction(
                user_story_id=story_id,
                model_used=config.model,
                raw_response=raw_response,
                status="completed",
                prompt_config=effective_prompt_config,
                confidence_score=confidence,
            )
            extraction = await self._extraction_repo.save(extraction)

            # 5. Persist Task entities
            for pt in parsed_tasks:
                task = Task(
                    user_story_id=story_id or extraction.user_story_id,
                    title=pt.summary,
                    description=pt.description,
                    labels=list(pt.labels),
                    dependencies=list(pt.dependencies),
                )
                await self._task_repo.save(task)

            # 6. Store in vector store for future RAG
            await self._store_rag(user_story, extraction, parsed_tasks)

            return extraction

        except (LLMError, ParseError) as exc:
            # Persist failed extraction with error info
            extraction = Extraction(
                user_story_id=story_id,
                model_used=config.model,
                raw_response="",
                status="failed",
                error_info=str(exc),
                prompt_config=prompt_config,
            )
            return await self._extraction_repo.save(extraction)

    async def _store_rag(
        self,
        user_story: object,
        extraction: Extraction,
        parsed_tasks: list[ParsedTask],
    ) -> None:
        """Store extraction in vector store for future RAG searches."""
        if self._vector_store is None:
            return
        try:
            tasks_summary = "\n".join(
                f"{i+1}. {t.summary}: {t.description}"
                for i, t in enumerate(parsed_tasks)
            )
            await self._vector_store.store_extraction(
                extraction_id=str(extraction.id),
                user_story_text=getattr(user_story, "raw_text", str(user_story)),
                tasks_summary=tasks_summary,
                model_used=extraction.model_used,
                confidence_score=extraction.confidence_score,
                user_story_id=str(getattr(user_story, "id", "")),
            )
        except Exception:
            logger.warning("RAG store failed, extraction already saved")
