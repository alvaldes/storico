from __future__ import annotations

from abc import ABC, abstractmethod
from uuid import UUID

from storico.domain.entities.task import Task


class TaskRepository(ABC):
    """Repository port for Task entities."""

    @abstractmethod
    async def save(self, task: Task) -> Task:
        """Persist a task. Creates or updates as needed."""
        ...

    @abstractmethod
    async def find_by_id(self, task_id: UUID) -> Task | None:
        """Find a task by its unique identifier."""
        ...

    @abstractmethod
    async def list_by_story(self, user_story_id: UUID) -> list[Task]:
        """Return all tasks belonging to a user story."""
        ...

    @abstractmethod
    async def list_page(
        self,
        *,
        workspace_id: UUID | None = None,
        user_story_id: UUID | None = None,
        workspace_ids: list[UUID] | None = None,
        limit: int,
        offset: int,
    ) -> tuple[list[Task], int]:
        """Return one page of tasks matching exactly one scope, plus the total.

        Exactly one of ``workspace_id``, ``user_story_id`` or ``workspace_ids``
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
    async def list_by_workspace(self, workspace_id: UUID) -> list[Task]:
        """Return all tasks belonging to a workspace."""
        ...

    @abstractmethod
    async def list(self) -> list[Task]:
        """Return all tasks."""
        ...

    @abstractmethod
    async def delete(self, task_id: UUID) -> None:
        """Delete a task by its unique identifier."""
        ...
