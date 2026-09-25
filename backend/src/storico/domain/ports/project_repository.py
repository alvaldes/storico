from __future__ import annotations

from abc import ABC, abstractmethod
from uuid import UUID

from storico.domain.entities.project import Project, ProjectWithCount


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
    async def find_by_id_with_count(self, project_id: UUID) -> ProjectWithCount | None:
        """Find a project and the count of its user stories in one query."""
        ...

    @abstractmethod
    async def list_page(
        self, workspace_id: UUID, *, limit: int, offset: int
    ) -> tuple[list[ProjectWithCount], int]:
        """Return one page of projects with their story counts, plus the total."""
        ...

    @abstractmethod
    async def list(self) -> list[Project]:
        """Return all projects."""
        ...

    @abstractmethod
    async def delete(self, project_id: UUID) -> None:
        """Delete a project by its unique identifier."""
        ...

    @abstractmethod
    async def count_stories(self, project_id: UUID) -> int:
        """Return the number of user stories in a project."""
        ...

    @abstractmethod
    async def count_by_workspace(self, workspace_id: UUID) -> int:
        """Return the number of projects in a workspace."""
        ...
