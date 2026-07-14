"""WorkspaceRepository port — defines the contract for workspace persistence."""

from __future__ import annotations

from abc import ABC, abstractmethod
from uuid import UUID

from storico.domain.entities.workspace import Workspace


class WorkspaceRepository(ABC):
    """Repository port for Workspace entities."""

    @abstractmethod
    async def save(self, workspace: Workspace) -> Workspace:
        """Persist a workspace. Creates or updates as needed."""
        ...

    @abstractmethod
    async def find_by_id(self, workspace_id: UUID) -> Workspace | None:
        """Find a workspace by its unique identifier."""
        ...

    @abstractmethod
    async def list_by_user(self, user_id: UUID) -> list[Workspace]:
        """Return all workspaces a user belongs to."""
        ...

    @abstractmethod
    async def find_by_slug(self, slug: str) -> Workspace | None:
        """Find a workspace by its slug."""
        ...

    @abstractmethod
    async def delete(self, workspace_id: UUID) -> None:
        """Delete a workspace by its unique identifier."""
        ...

    @abstractmethod
    async def count_members(self, workspace_id: UUID) -> int:
        """Return the number of members in a workspace."""
        ...

    @abstractmethod
    async def list_slugs(self) -> list[str]:
        """Return all workspace slugs (used for uniqueness validation)."""
        ...
