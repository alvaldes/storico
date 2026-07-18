"""Use cases for adding and removing workspace members."""

from __future__ import annotations

from uuid import UUID

from storico.domain.entities import (
    CannotRemoveOwnerError,
    DuplicateEntity,
    EntityNotFound,
    LastAdminError,
    NotWorkspaceMember,
    WorkspaceMember,
    WorkspaceRole,
)
from storico.domain.ports import (
    UserRepository,
    WorkspaceMemberRepository,
    WorkspaceRepository,
)


class AddMemberUseCase:
    """Use case: add a user as a member of a workspace.

    The caller must already be validated as an admin of the workspace
    (done at the route layer via ``require_admin``).
    """

    def __init__(
        self,
        ws_repo: WorkspaceRepository,
        member_repo: WorkspaceMemberRepository,
        user_repo: UserRepository,
    ) -> None:
        self._ws_repo = ws_repo
        self._member_repo = member_repo
        self._user_repo = user_repo

    async def execute(
        self,
        workspace_id: UUID,
        target_user_email: str,
    ) -> WorkspaceMember:
        """Add a user to a workspace with role ``member``.

        Args:
            workspace_id: The workspace to add the user to.
            target_user_email: Email of the user to add.

        Returns:
            The newly created ``WorkspaceMember`` entity.

        Raises:
            EntityNotFound: If the workspace or target user does not exist.
            DuplicateEntity: If the user is already a member of the workspace.
        """
        # Validate workspace exists
        workspace = await self._ws_repo.find_by_id(workspace_id)
        if workspace is None:
            raise EntityNotFound("Workspace", str(workspace_id))

        # Validate target user exists by email
        user = await self._user_repo.find_by_email(target_user_email)
        if user is None:
            raise EntityNotFound("User", target_user_email)

        # Validate not already a member
        existing = await self._member_repo.find_by_workspace_and_user(
            workspace_id, user.id
        )
        if existing is not None:
            raise DuplicateEntity(
                "WorkspaceMember",
                "user_email",
                target_user_email,
            )

        member = WorkspaceMember(
            workspace_id=workspace_id,
            user_id=user.id,
            role=WorkspaceRole.MEMBER,
        )
        return await self._member_repo.add(member)


class RemoveMemberUseCase:
    """Use case: remove a member from a workspace.

    The caller must already be validated as an admin (done at the route
    layer). The use case enforces two business rules:

    1. The workspace owner cannot be removed.
    2. An admin cannot remove themselves if they are the last admin.
    """

    def __init__(
        self,
        ws_repo: WorkspaceRepository,
        member_repo: WorkspaceMemberRepository,
    ) -> None:
        self._ws_repo = ws_repo
        self._member_repo = member_repo

    async def execute(
        self,
        workspace_id: UUID,
        caller_id: UUID,
        target_user_id: UUID,
    ) -> None:
        """Remove a member from a workspace.

        Args:
            workspace_id: The workspace to remove the member from.
            caller_id: UUID of the authenticated admin performing the action.
            target_user_id: UUID of the member to remove.

        Raises:
            EntityNotFound: If the workspace or membership record does not
                exist.
            CannotRemoveOwnerError: If ``target_user_id`` is the workspace
                owner.
            LastAdminError: If the target is an admin removing themselves
                and they are the last admin of the workspace.
        """
        # Validate workspace exists
        workspace = await self._ws_repo.find_by_id(workspace_id)
        if workspace is None:
            raise EntityNotFound("Workspace", str(workspace_id))

        # Cannot remove the workspace owner
        if target_user_id == workspace.owner_id:
            raise CannotRemoveOwnerError()

        # Validate membership record exists
        member = await self._member_repo.find_by_workspace_and_user(
            workspace_id, target_user_id
        )
        if member is None:
            raise NotWorkspaceMember(workspace_id, target_user_id)

        # Cannot remove self if last admin
        if target_user_id == caller_id and member.role == WorkspaceRole.ADMIN:
            admin_count = await self._member_repo.count_admins(workspace_id)
            if admin_count <= 1:
                raise LastAdminError(
                    "Cannot remove yourself as the last admin. "
                    "Promote another member first."
                )

        await self._member_repo.remove(workspace_id, target_user_id)
