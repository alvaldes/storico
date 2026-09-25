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
    async def list_by_workspace(self, workspace_id: UUID) -> list[Task]:
        """Return all tasks belonging to a workspace."""
        ...

    @abstractmethod
    async def list_by_workspaces(self, workspace_ids: list[UUID]) -> list[Task]:
        """Return every task belonging to any of the workspaces, in one query.

        The fold for callers that used to await ``list_by_workspace`` once per workspace, which
        cost one statement per workspace. Against the dev pooler a statement measures ~2s — a bare
        ``SELECT 1`` already costs 800ms there (``/api/v1/health``) — so 12 of them is how a list
        request reached 25-32s. An empty ``workspace_ids`` returns ``[]`` without querying: no
        memberships is no rows, not a statement.
        """
        ...

    @abstractmethod
    async def list(self) -> list[Task]:
        """Return all tasks."""
        ...

    @abstractmethod
    async def delete(self, task_id: UUID) -> None:
        """Delete a task by its unique identifier."""
        ...
