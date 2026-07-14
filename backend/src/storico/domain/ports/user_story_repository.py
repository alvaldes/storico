from __future__ import annotations

from abc import ABC, abstractmethod
from uuid import UUID

from storico.domain.entities.user_story import UserStory


class UserStoryRepository(ABC):
    """Repository port for UserStory entities."""

    @abstractmethod
    async def save(self, user_story: UserStory) -> UserStory:
        """Persist a user story. Creates or updates as needed."""
        ...

    @abstractmethod
    async def find_by_id(self, user_story_id: UUID) -> UserStory | None:
        """Find a user story by its unique identifier."""
        ...

    @abstractmethod
    async def list_by_project(self, project_id: UUID) -> list[UserStory]:
        """Return all user stories belonging to a project."""
        ...

    @abstractmethod
    async def list_by_workspace(self, workspace_id: UUID) -> list[UserStory]:
        """Return all user stories belonging to a workspace."""
        ...

    @abstractmethod
    async def list(self) -> list[UserStory]:
        """Return all user stories."""
        ...

    @abstractmethod
    async def delete(self, user_story_id: UUID) -> None:
        """Delete a user story by its unique identifier."""
        ...
