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
    async def list(self) -> list[Task]:
        """Return all tasks."""
        ...

    @abstractmethod
    async def delete(self, task_id: UUID) -> None:
        """Delete a task by its unique identifier."""
        ...
