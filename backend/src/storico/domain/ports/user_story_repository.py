from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence
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

    @abstractmethod
    async def list_parts_by_project(self, project_id: UUID) -> list[tuple[str, str, str, UUID]]:
        """Return ``(actor, feature, benefit, story_id)`` for every story in a project.

        One statement covers the whole project: a CSV import checks duplicates
        for many rows at once, and calling ``find_by_parts`` per row would cost
        one round-trip per row before anything was written.

        The strings come back exactly as stored — no normalisation. The
        caller's duplicate rule is an exact match, so folding case here would
        hide differences the rule treats as distinct (``User`` vs ``user``).
        An empty project returns an empty list.
        """
        ...

    @abstractmethod
    async def save_many(self, user_stories: Sequence[UserStory]) -> list[UserStory]:
        """Insert every story in one transaction and return the saved entities.

        A bulk import must not pay one commit per row: ``save`` commits per
        call, so a thousand rows would be a thousand transactions with no
        atomicity at all. Here the whole batch commits once — either every row
        lands or none does.

        An empty input returns an empty list without issuing any statement.
        No rows means no work, not a round-trip — the same rule
        ``list_page`` follows for an empty ``workspace_ids``, and against a
        pooler where one statement costs seconds, an unasked statement is pure
        latency.

        Returns the saved entities with their ids and timestamps populated.
        """
        ...
