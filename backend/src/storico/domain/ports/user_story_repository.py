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
    async def list_by_workspaces(self, workspace_ids: list[UUID]) -> list[UserStory]:
        """Return every user story belonging to any of the workspaces, in one query.

        The fold for callers that used to await ``list_by_workspace`` once per workspace, which
        cost one statement per workspace. Against the dev pooler a statement measures ~2s — a bare
        ``SELECT 1`` already costs 800ms there (``/api/v1/health``) — so 12 of them is how a list
        request reached 25-32s. An empty ``workspace_ids`` returns ``[]`` without querying: no
        memberships is no rows, not a statement.
        """
        ...

    @abstractmethod
    async def list(self) -> list[UserStory]:
        """Return all user stories."""
        ...

    @abstractmethod
    async def delete(self, user_story_id: UUID) -> None:
        """Delete a user story by its unique identifier."""
        ...

    @abstractmethod
    async def find_by_parts(
        self, project_id: UUID, actor: str, feature: str, benefit: str
    ) -> UserStory | None:
        """Find a user story by project_id and its parts (actor, feature, benefit).

        Returns the existing story if found, None otherwise.
        This is used for duplicate detection based on the semantic content
        rather than the raw text format.
        """
        ...
