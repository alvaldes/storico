"""SQLAlchemy implementation of the WorkspaceRepository port."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from storico.domain.entities import EntityNotFound, RepositoryError, Workspace
from storico.domain.ports import WorkspaceRepository
from storico.infrastructure.database.models import WorkspaceMemberModel, WorkspaceModel


class SQLAlchemyWorkspaceRepository(WorkspaceRepository):
    """Repository implementation for Workspace entities using SQLAlchemy async sessions."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save(self, workspace: Workspace) -> Workspace:
        try:
            existing = await self._session.get(WorkspaceModel, workspace.id)
            if existing:
                kwargs = self._to_orm_kwargs(workspace)
                kwargs["updated_at"] = datetime.now(UTC)
                for key, value in kwargs.items():
                    setattr(existing, key, value)
            else:
                self._session.add(WorkspaceModel(**self._to_orm_kwargs(workspace)))
            await self._session.commit()
            return workspace
        except SQLAlchemyError as e:
            await self._session.rollback()
            raise RepositoryError("Database error saving workspace") from e

    async def find_by_id(self, workspace_id: UUID) -> Workspace | None:
        result = await self._session.get(WorkspaceModel, workspace_id)
        return self._to_domain(result) if result else None

    async def list_by_user(self, user_id: UUID) -> list[Workspace]:
        stmt = (
            select(WorkspaceModel)
            .join(WorkspaceMemberModel)
            .where(WorkspaceMemberModel.user_id == user_id)
        )
        result = await self._session.execute(stmt)
        return [self._to_domain(row) for row in result.scalars()]

    async def find_by_slug(self, slug: str) -> Workspace | None:
        stmt = select(WorkspaceModel).where(WorkspaceModel.slug == slug)
        result = await self._session.execute(stmt)
        row = result.scalar_one_or_none()
        return self._to_domain(row) if row else None

    async def delete(self, workspace_id: UUID) -> None:
        stmt = delete(WorkspaceModel).where(WorkspaceModel.id == workspace_id)
        result = await self._session.execute(stmt)
        await self._session.commit()
        if result.rowcount == 0:
            raise EntityNotFound("Workspace", str(workspace_id))

    async def count_members(self, workspace_id: UUID) -> int:
        stmt = select(func.count()).select_from(WorkspaceMemberModel).where(
            WorkspaceMemberModel.workspace_id == workspace_id
        )
        result = await self._session.execute(stmt)
        return result.scalar_one()

    async def list_slugs(self) -> list[str]:
        stmt = select(WorkspaceModel.slug)
        result = await self._session.execute(stmt)
        return list(result.scalars())

    def _to_domain(self, model: WorkspaceModel) -> Workspace:
        return Workspace(
            name=model.name,
            slug=model.slug,
            owner_id=model.owner_id,
            icon=model.icon,
            id=model.id,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )

    @staticmethod
    def _to_orm_kwargs(workspace: Workspace) -> dict:
        return {
            "id": workspace.id,
            "name": workspace.name,
            "slug": workspace.slug,
            "owner_id": workspace.owner_id,
            "icon": workspace.icon,
            "created_at": workspace.created_at,
            "updated_at": workspace.updated_at,
        }
