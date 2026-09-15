"""UserStory state-machine services for the extraction flow."""

from __future__ import annotations

from uuid import UUID

from storico.domain.entities import EntityNotFound, UserStory
from storico.domain.entities.user_story import UserStoryStatus
from storico.domain.ports import UserStoryRepository


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