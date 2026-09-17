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
    async def list_by_workspace(self, workspace_id: UUID) -> list[Project]:
        """Return all projects scoped to a workspace."""
        ...

    @abstractmethod
    async def list_by_workspace_with_counts(self, workspace_id: UUID) -> list[ProjectWithCount]:
        """Return all projects in a workspace with their story counts.

        Folds the per-project story count into a single JOIN+GROUP_BY query
        so the caller avoids one extra round-trip per project (N+1).
        """
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
