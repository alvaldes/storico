"""ExtractFromStoryUseCase — orchestrates extraction with UserStory state machine."""

from __future__ import annotations

from uuid import UUID

from storico.domain.entities import EntityNotFound, UserStory
from storico.domain.entities.exceptions import LLMError, ParseError
from storico.domain.entities.user_story import UserStoryStatus
from storico.domain.ports import LLMConfig, UserStoryRepository
from storico.domain.services.extraction_service import ExtractionService


class ExtractFromStoryUseCase:
    """Use case: extract tasks from a user story with state machine transitions.

    Orchestrates the full extraction flow with proper UserStoryStatus transitions:
    1. PENDING_EXTRACTION → EXTRACTING (when background task starts)
    2. EXTRACTING → EXTRACTED (on LLM success) or EXTRACTING → FAILED_EXTRACTION (on failure)

    The background worker handles the actual LLM call and final state transition.
    This use case creates the initial extraction record and transitions to EXTRACTING.
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
        """Load a user story and start extraction.

        Args:
            story_id: UUID of the user story to extract from.
            model: Override for the LLM model name. Falls back to settings.
            temperature: Override for generation temperature.
                Falls back to ``LLMConfig`` default (0.1).
            validate: Whether to run LLM-as-a-Judge validation after extraction.

        Returns:
            Dict with extraction result metadata (extraction_id, status,
            user_story_status, error_info, model_used, confidence_score, created_at).

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

        # 3. Run extraction (includes persistence and state transitions)
        extraction = await self._extraction_service.extract_and_persist(
            user_story=story,
            config=llm_config,
            prompt_config={
                "validate": validate,
                "temperature": llm_config.temperature,
                "max_tokens": llm_config.max_tokens,
            },
        )

        # 4. Return extraction metadata including user_story_status
        return {
            "extraction_id": extraction.id,
            "status": extraction.status,
            "user_story_status": extraction.user_story_status,
            "error_info": extraction.error_info,
            "model_used": extraction.model_used,
            "confidence_score": extraction.confidence_score,
            "created_at": extraction.created_at,
        }

    async def start_extraction(
        self,
        story_id: UUID,
        model: str,
        temperature: float | None = None,
        validate: bool = False,
    ) -> tuple[UUID, UserStoryStatus]:
        """Start extraction by transitioning story to EXTRACTING.

        This is called by the API to create the extraction record and
        transition the story to EXTRACTING before launching the background task.

        Returns:
            Tuple of (extraction_id, user_story_status_after_transition)
        """
        story = await self._story_repo.find_by_id(story_id)
        if story is None:
            raise EntityNotFound("UserStory", str(story_id))

        # Transition story to EXTRACTING (from PENDING_EXTRACTION)
        from dataclasses import replace
        from datetime import UTC, datetime

        updated_story = replace(
            story,
            status=UserStoryStatus.EXTRACTING,
            updated_at=datetime.now(UTC),
        )
        await self._story_repo.save(updated_story)

        # Create pending extraction record
        from storico.domain.entities.extraction import Extraction, ExtractionStatus
        from uuid_utils.compat import uuid7

        extraction = Extraction(
            id=uuid7(),
            user_story_id=story_id,
            model_used=model,
            raw_response="",
            status=ExtractionStatus.PENDING,
            user_story_status=UserStoryStatus.EXTRACTING,
            prompt_config={
                "validate": validate,
                "temperature": temperature if temperature is not None else 0.1,
                "max_tokens": 2048,
            },
        )
        extraction = await self._extraction_service._extraction_repo.save(extraction)

        return extraction.id, UserStoryStatus.EXTRACTING


class UserStoryStateService:
    """Service for managing UserStory state transitions."""

    def __init__(self, story_repo: UserStoryRepository) -> None:
        self._story_repo = story_repo

    async def transition_to_extracting(self, story_id: UUID) -> UserStory:
        """Transition a story from PENDING_EXTRACTION to EXTRACTING."""
        story = await self._story_repo.find_by_id(story_id)
        if story is None:
            raise EntityNotFound("UserStory", str(story_id))

        if story.status != UserStoryStatus.PENDING_EXTRACTION:
            raise InvalidUserStoryTransition(
                current_state=story.status,
                attempted_state=UserStoryStatus.EXTRACTING,
            )

        from dataclasses import replace
        from datetime import UTC, datetime

        updated = replace(
            story,
            status=UserStoryStatus.EXTRACTING,
            updated_at=datetime.now(UTC),
        )
        return await self._story_repo.save(updated)

    async def transition_to_extracted(self, story_id: UUID) -> UserStory:
        """Transition a story from EXTRACTING to EXTRACTED."""
        story = await self._story_repo.find_by_id(story_id)
        if story is None:
            raise EntityNotFound("UserStory", str(story_id))

        if story.status != UserStoryStatus.EXTRACTING:
            raise InvalidUserStoryTransition(
                current_state=story.status,
                attempted_state=UserStoryStatus.EXTRACTED,
            )

        from dataclasses import replace
        from datetime import UTC, datetime

        updated = replace(
            story,
            status=UserStoryStatus.EXTRACTED,
            updated_at=datetime.now(UTC),
        )
        return await self._story_repo.save(updated)

    async def transition_to_failed_extraction(self, story_id: UUID) -> UserStory:
        """Transition a story from EXTRACTING to FAILED_EXTRACTION."""
        story = await self._story_repo.find_by_id(story_id)
        if story is None:
            raise EntityNotFound("UserStory", str(story_id))

        if story.status != UserStoryStatus.EXTRACTING:
            raise InvalidUserStoryTransition(
                current_state=story.status,
                attempted_state=UserStoryStatus.FAILED_EXTRACTION,
            )

        from dataclasses import replace
        from datetime import UTC, datetime

        updated = replace(
            story,
            status=UserStoryStatus.FAILED_EXTRACTION,
            updated_at=datetime.now(UTC),
        )
        return await self._story_repo.save(updated)


class InvalidUserStoryTransition(Exception):
    """Raised when a UserStory state transition is not allowed."""

    def __init__(
        self,
        current_state: UserStoryStatus,
        attempted_state: UserStoryStatus,
    ) -> None:
        self.current_state = current_state
        self.attempted_state = attempted_state
        from storico.domain.validators.state_machine import (
            get_allowed_user_story_transitions,
        )

        allowed = get_allowed_user_story_transitions(current_state)
        super().__init__(
            f"Invalid UserStory transition from {current_state.value} to {attempted_state.value}. "
            f"Allowed: {[s.value for s in allowed]}"
        )