"""SQLAlchemy implementation of the WorkspaceMemberRepository port."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from storico.domain.entities import (
    EntityNotFound,
    OwnerTransferError,
    RepositoryError,
    WorkspaceMember,
    WorkspaceRole,
)
from storico.domain.ports import WorkspaceMemberRepository
from storico.infrastructure.database.models import WorkspaceMemberModel, WorkspaceModel


class SQLAlchemyWorkspaceMemberRepository(WorkspaceMemberRepository):
    """Repository implementation for WorkspaceMember entities using SQLAlchemy async sessions."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, member: WorkspaceMember) -> WorkspaceMember:
        try:
            self._session.add(WorkspaceMemberModel(**self._to_orm_kwargs(member)))
            await self._session.commit()
            return member
        except SQLAlchemyError as e:
            await self._session.rollback()
            raise RepositoryError("Database error adding workspace member") from e

    async def remove(self, workspace_id: UUID, user_id: UUID) -> None:
        try:
            stmt = delete(WorkspaceMemberModel).where(
                WorkspaceMemberModel.workspace_id == workspace_id,
                WorkspaceMemberModel.user_id == user_id,
            )
            result = await self._session.execute(stmt)
            await self._session.commit()
            if result.rowcount == 0:
                raise EntityNotFound(
                    "WorkspaceMember", f"{workspace_id}/{user_id}"
                )
        except SQLAlchemyError as e:
            await self._session.rollback()
            raise RepositoryError("Database error removing workspace member") from e

    async def update_role(
        self, workspace_id: UUID, user_id: UUID, role: WorkspaceRole
    ) -> WorkspaceMember:
        try:
            stmt = (
                update(WorkspaceMemberModel)
                .where(
                    WorkspaceMemberModel.workspace_id == workspace_id,
                    WorkspaceMemberModel.user_id == user_id,
                )
                .values(role=role.value)
                .returning(WorkspaceMemberModel)
            )
            result = await self._session.execute(stmt)
            await self._session.commit()
            row = result.scalar_one_or_none()
            if not row:
                raise EntityNotFound(
                    "WorkspaceMember", f"{workspace_id}/{user_id}"
                )
            return self._to_domain(row)
        except SQLAlchemyError as e:
            await self._session.rollback()
            raise RepositoryError(
                "Database error updating workspace member role"
            ) from e

    async def find_by_workspace_and_user(
        self, workspace_id: UUID, user_id: UUID
    ) -> WorkspaceMember | None:
        stmt = select(WorkspaceMemberModel).where(
            WorkspaceMemberModel.workspace_id == workspace_id,
            WorkspaceMemberModel.user_id == user_id,
        )
        result = await self._session.execute(stmt)
        row = result.scalar_one_or_none()
        return self._to_domain(row) if row else None

    async def list_by_workspace(
        self, workspace_id: UUID
    ) -> list[WorkspaceMember]:
        stmt = select(WorkspaceMemberModel).where(
            WorkspaceMemberModel.workspace_id == workspace_id
        )
        result = await self._session.execute(stmt)
        return [self._to_domain(row) for row in result.scalars()]

    async def list_by_user(self, user_id: UUID) -> list[WorkspaceMember]:
        stmt = select(WorkspaceMemberModel).where(
            WorkspaceMemberModel.user_id == user_id
        )
        result = await self._session.execute(stmt)
        return [self._to_domain(row) for row in result.scalars()]

    async def transfer_ownership(
        self,
        workspace_id: UUID,
        current_owner_id: UUID,
        new_owner_id: UUID,
    ) -> None:
        try:
            # Verify current owner matches
            workspace = await self._session.get(WorkspaceModel, workspace_id)
            if not workspace:
                raise EntityNotFound("Workspace", str(workspace_id))
            if workspace.owner_id != current_owner_id:
                raise OwnerTransferError(
                    "Current owner does not match workspace owner"
                )

            # Verify new owner is an admin member
            member_stmt = select(WorkspaceMemberModel).where(
                WorkspaceMemberModel.workspace_id == workspace_id,
                WorkspaceMemberModel.user_id == new_owner_id,
            )
            member_result = await self._session.execute(member_stmt)
            new_owner_member = member_result.scalar_one_or_none()
            if not new_owner_member:
                raise OwnerTransferError(
                    "New owner must be a member of the workspace"
                )
            if new_owner_member.role != WorkspaceRole.ADMIN.value:
                raise OwnerTransferError(
                    "New owner must have admin role"
                )

            # Update workspace owner
            workspace.owner_id = new_owner_id

            # Demote old owner to admin
            demote_stmt = (
                update(WorkspaceMemberModel)
                .where(
                    WorkspaceMemberModel.workspace_id == workspace_id,
                    WorkspaceMemberModel.user_id == current_owner_id,
                )
                .values(role=WorkspaceRole.ADMIN.value)
            )
            await self._session.execute(demote_stmt)
            await self._session.commit()
        except (SQLAlchemyError, OwnerTransferError, EntityNotFound) as e:
            await self._session.rollback()
            if isinstance(e, (OwnerTransferError, EntityNotFound)):
                raise
            raise RepositoryError(
                "Database error transferring workspace ownership"
            ) from e

    async def count_admins(self, workspace_id: UUID) -> int:
        stmt = select(func.count()).select_from(WorkspaceMemberModel).where(
            WorkspaceMemberModel.workspace_id == workspace_id,
            WorkspaceMemberModel.role == WorkspaceRole.ADMIN.value,
        )
        result = await self._session.execute(stmt)
        return result.scalar_one()

    @staticmethod
    def _to_domain(model: WorkspaceMemberModel) -> WorkspaceMember:
        return WorkspaceMember(
            workspace_id=model.workspace_id,
            user_id=model.user_id,
            role=WorkspaceRole(model.role),
            id=model.id,
            created_at=model.created_at,
        )

    @staticmethod
    def _to_orm_kwargs(member: WorkspaceMember) -> dict:
        return {
            "id": member.id,
            "workspace_id": member.workspace_id,
            "user_id": member.user_id,
            "role": member.role.value,
            "created_at": member.created_at,
        }
