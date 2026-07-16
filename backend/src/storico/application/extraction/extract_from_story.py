"""ExtractFromStoryUseCase — loads a user story and runs extraction."""

from __future__ import annotations

from uuid import UUID

from storico.domain.entities import EntityNotFound
from storico.domain.entities.exceptions import LLMError, ParseError
from storico.domain.ports import LLMConfig, UserStoryRepository
from storico.domain.services.extraction_service import ExtractionService


class ExtractFromStoryUseCase:
    """Use case: extract tasks from a user story.

    Loads the user story from the repository, configures the LLM, and
    delegates to ``ExtractionService`` for the actual extraction.
    """

    def __init__(
        self,
        extraction_service: ExtractionService,
        story_repo: UserStoryRepository,
    ) -> None:
        self._extraction_service = extraction_service
        self._story_repo = story_repo

    async def execute(
        self,
        story_id: UUID,
        model: str | None = None,
        temperature: float | None = None,
        validate: bool = False,
    ) -> dict:
        """Load a user story and extract tasks from it.

        Args:
            story_id: UUID of the user story to extract from.
            model: Override for the LLM model name. Falls back to settings.
            temperature: Override for generation temperature.
                Falls back to ``LLMConfig`` default (0.1).
            validate: Whether to run LLM-as-a-Judge validation after extraction.

        Returns:
            Dict with extraction result metadata (extraction_id, status,
            error_info, model_used, confidence_score, created_at).

        Raises:
            EntityNotFound: If the user story does not exist.
            LLMError: If the LLM call fails and persistence also fails.
            ParseError: If the LLM response cannot be parsed and persistence
                also fails.
        """
        # 1. Load user story
        story = await self._story_repo.find_by_id(story_id)
        if story is None:
            raise EntityNotFound("UserStory", str(story_id))

        # 2. Build LLM config
        if model is None:
            raise ValueError("model is required for extraction")
        llm_config = LLMConfig(
            model=model,
            temperature=temperature if temperature is not None else 0.1,
            max_tokens=2048,
            timeout=120,
        )

        # 3. Run extraction (includes persistence)
        extraction = await self._extraction_service.extract_and_persist(
            user_story=story,
            config=llm_config,
            prompt_config={
                "validate": validate,
                "temperature": llm_config.temperature,
                "max_tokens": llm_config.max_tokens,
            },
        )

        # 4. Return extraction metadata
        return {
            "extraction_id": extraction.id,
            "status": extraction.status,
            "error_info": extraction.error_info,
            "model_used": extraction.model_used,
            "confidence_score": extraction.confidence_score,
            "created_at": extraction.created_at,
        }
