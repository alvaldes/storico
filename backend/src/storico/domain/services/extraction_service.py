"""ExtractionService — domain orchestrator for LLM-based task extraction."""

from __future__ import annotations

from storico.domain.entities import Extraction, ParseError, Task
from storico.domain.entities.exceptions import LLMError
from storico.domain.ports import (
    ExtractionRepository,
    LLMConfig,
    LLMPort,
    ParsedTask,
    TaskRepository,
)
from storico.infrastructure.llm.prompt_manager import PromptManager
from storico.infrastructure.llm.task_parser import TaskParser

from .extraction_judge_service import LLMJudgeService


class ExtractionService:
    """Orchestrates the full extraction pipeline.

    Flow:
        1. Render system + task-generation prompts from the user story.
        2. Call the LLM via ``LLMPort``.
        3. Parse the raw response into ``ParsedTask`` objects.
        4. Persist the ``Extraction`` (completed or failed) + ``Task`` entities.
        5. Optionally validate results via ``LLMJudgeService``.
        6. Return the extraction entity.
    """

    def __init__(
        self,
        llm_port: LLMPort,
        prompt_manager: PromptManager,
        task_parser: TaskParser,
        extraction_repo: ExtractionRepository,
        task_repo: TaskRepository,
        judge_service: LLMJudgeService | None = None,
    ) -> None:
        self._llm = llm_port
        self._prompt_manager = prompt_manager
        self._task_parser = task_parser
        self._extraction_repo = extraction_repo
        self._task_repo = task_repo
        self._judge_service = judge_service

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
        instruction_prompt = self._prompt_manager.render(
            "task_generation.j2",
            user_story=raw_text,
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
