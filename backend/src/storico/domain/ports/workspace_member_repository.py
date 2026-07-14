"""WorkspaceMemberRepository port — defines the contract for workspace member persistence."""

from __future__ import annotations

from abc import ABC, abstractmethod
from uuid import UUID

from storico.domain.entities.workspace_member import WorkspaceMember, WorkspaceRole


class WorkspaceMemberRepository(ABC):
    """Repository port for WorkspaceMember entities."""

    @abstractmethod
    async def add(self, member: WorkspaceMember) -> WorkspaceMember:
        """Add a member to a workspace."""
        ...

    @abstractmethod
    async def remove(self, workspace_id: UUID, user_id: UUID) -> None:
        """Remove a member from a workspace."""
        ...

    @abstractmethod
    async def update_role(
        self, workspace_id: UUID, user_id: UUID, role: WorkspaceRole
    ) -> WorkspaceMember:
        """Update the role of a workspace member."""
        ...

    @abstractmethod
    async def find_by_workspace_and_user(
        self, workspace_id: UUID, user_id: UUID
    ) -> WorkspaceMember | None:
        """Find a specific member by workspace and user IDs."""
        ...

    @abstractmethod
    async def list_by_workspace(
        self, workspace_id: UUID
    ) -> list[WorkspaceMember]:
        """Return all members of a workspace."""
        ...

    @abstractmethod
    async def list_by_user(self, user_id: UUID) -> list[WorkspaceMember]:
        """Return all workspace memberships for a user."""
        ...

    @abstractmethod
    async def transfer_ownership(
        self,
        workspace_id: UUID,
        current_owner_id: UUID,
        new_owner_id: UUID,
    ) -> None:
        """Transfer workspace ownership from one user to another."""
        ...

    @abstractmethod
    async def count_admins(self, workspace_id: UUID) -> int:
        """Return the number of admin members in a workspace."""
        ...
