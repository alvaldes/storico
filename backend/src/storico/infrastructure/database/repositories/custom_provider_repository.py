"""SQLAlchemy implementation of the CustomProviderRepository port."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from storico.domain.entities import CustomProvider, RepositoryError
from storico.domain.ports import CustomProviderRepository
from storico.infrastructure.database.models import CustomProviderModel


class SQLAlchemyCustomProviderRepository(CustomProviderRepository):
    """Repository implementation for CustomProvider entities using SQLAlchemy async sessions."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_by_workspace(self, workspace_id: UUID) -> list[CustomProvider]:
        stmt = (
            select(CustomProviderModel)
            .where(CustomProviderModel.workspace_id == workspace_id)
            .order_by(CustomProviderModel.name)
        )
        result = await self._session.execute(stmt)  # nosemgrep: parameterized ORM select
        return [self._to_domain(row) for row in result.scalars().all()]

    async def get(self, provider_id: UUID) -> CustomProvider | None:
        stmt = select(CustomProviderModel).where(CustomProviderModel.id == provider_id)
        result = await self._session.execute(stmt)  # nosemgrep: parameterized ORM select
        row = result.scalar_one_or_none()
        return self._to_domain(row) if row else None

    async def find_by_workspace_and_name(
        self, workspace_id: UUID, name: str
    ) -> CustomProvider | None:
        stmt = select(CustomProviderModel).where(
            CustomProviderModel.workspace_id == workspace_id,
            CustomProviderModel.name == name,
        )
        result = await self._session.execute(stmt)  # nosemgrep: parameterized ORM select
        row = result.scalar_one_or_none()
        return self._to_domain(row) if row else None

    async def create(self, provider: CustomProvider) -> CustomProvider:
        try:
            self._session.add(CustomProviderModel(**self._to_orm_kwargs(provider)))
            await self._session.commit()
            return provider
        except SQLAlchemyError as e:
            await self._session.rollback()
            raise RepositoryError("Database error creating custom provider") from e

    async def rename(self, provider_id: UUID, name: str) -> CustomProvider | None:
        try:
            stmt = select(CustomProviderModel).where(CustomProviderModel.id == provider_id)
            result = await self._session.execute(stmt)  # nosemgrep: parameterized ORM select
            row = result.scalar_one_or_none()
            if row is None:
                return None
            row.name = name
            row.updated_at = datetime.now(UTC)
            await self._session.commit()
            await self._session.refresh(row)
            return self._to_domain(row)
        except SQLAlchemyError as e:
            await self._session.rollback()
            raise RepositoryError("Database error renaming custom provider") from e

    @staticmethod
    def _to_domain(model: CustomProviderModel) -> CustomProvider:
        return CustomProvider(
            workspace_id=model.workspace_id,
            name=model.name,
            id=model.id,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )

    @staticmethod
    def _to_orm_kwargs(provider: CustomProvider) -> dict:
        return {
            "id": provider.id,
            "workspace_id": provider.workspace_id,
            "name": provider.name,
            "created_at": provider.created_at,
            "updated_at": provider.updated_at,
        }
