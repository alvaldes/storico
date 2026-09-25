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
    async def list_page(
        self,
        *,
        workspace_id: UUID | None = None,
        project_id: UUID | None = None,
        workspace_ids: list[UUID] | None = None,
        limit: int,
        offset: int,
    ) -> tuple[list[UserStory], int]:
        """Return one page of stories matching exactly one scope, plus the total.

        Exactly one of ``workspace_id``, ``project_id`` or ``workspace_ids``
        must be given; calling with none raises ``ValueError``. An empty
        ``workspace_ids`` returns an empty page without issuing any statement:
        no memberships means no rows, not ``IN ()`` — and against the dev
        pooler, where one statement costs ~2s (a bare ``SELECT 1`` already
        measures 800ms in ``/api/v1/health``), an unasked statement is pure
        latency.

        The total rides on the rows' own statement as ``count(*) OVER ()``,
        so no separate ``SELECT COUNT(*)`` is issued on the normal path, and
        results are ordered by ``created_at DESC, id DESC`` in SQL.
        """
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
