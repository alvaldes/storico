"""TransferOwnershipUseCase — transfers workspace ownership between admins."""

from __future__ import annotations

from uuid import UUID

from storico.domain.ports import WorkspaceMemberRepository


class TransferOwnershipUseCase:
    """Use case: transfer workspace ownership to another admin member.

    This delegates the atomic transaction (update workspace.owner_id +
    demote old owner to admin) to the member repository's
    ``transfer_ownership`` method, which handles validation and the
    transactional boundary.
    """

    def __init__(
        self,
        member_repo: WorkspaceMemberRepository,
    ) -> None:
        self._member_repo = member_repo

    async def execute(
        self,
        workspace_id: UUID,
        current_owner_id: UUID,
        new_owner_id: UUID,
    ) -> None:
        """Transfer workspace ownership from the current owner to another admin.

        Args:
            workspace_id: The workspace whose ownership is being transferred.
            current_owner_id: UUID of the current owner (must match
                ``workspace.owner_id``).
            new_owner_id: UUID of the user who will become the new owner
                (must be an admin member).

        Raises:
            EntityNotFound: If the workspace does not exist.
            OwnerTransferError: If the current owner does not match, the
                new owner is not a member, or the new owner is not an admin.
        """
        await self._member_repo.transfer_ownership(
            workspace_id=workspace_id,
            current_owner_id=current_owner_id,
            new_owner_id=new_owner_id,
        )
