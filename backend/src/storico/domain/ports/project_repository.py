from __future__ import annotations

from abc import ABC, abstractmethod
from uuid import UUID

from storico.domain.entities.project import Project


class ProjectRepository(ABC):
    """Repository port for Project entities."""

    @abstractmethod
    async def save(self, project: Project) -> Project:
        """Persist a project. Creates or updates as needed."""
        ...

    @abstractmethod
    async def find_by_id(self, project_id: UUID) -> Project | None:
        """Find a project by its unique identifier."""
        ...

    @abstractmethod
    async def list_by_owner(self, owner_id: UUID) -> list[Project]:
        """Return all projects owned by a specific user."""
        ...

    @abstractmethod
    async def list(self) -> list[Project]:
        """Return all projects."""
        ...

    @abstractmethod
    async def delete(self, project_id: UUID) -> None:
        """Delete a project by its unique identifier."""
        ...
