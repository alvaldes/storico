"""SQLAlchemy implementation of the WorkspaceLLMConfigRepository port."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from storico.domain.entities import RepositoryError, WorkspaceLLMConfig
from storico.domain.ports import WorkspaceLLMConfigRepository
from storico.infrastructure.database.models import WorkspaceLLMConfigModel


class SQLAlchemyWorkspaceLLMConfigRepository(WorkspaceLLMConfigRepository):
    """Repository implementation for WorkspaceLLMConfig entities using SQLAlchemy async sessions."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, workspace_id: UUID) -> WorkspaceLLMConfig | None:
        stmt = select(WorkspaceLLMConfigModel).where(
            WorkspaceLLMConfigModel.workspace_id == workspace_id
        )
        result = await self._session.execute(stmt)
        row = result.scalar_one_or_none()
        return self._to_domain(row) if row else None

    async def upsert(self, config: WorkspaceLLMConfig) -> WorkspaceLLMConfig:
        try:
            existing = await self._session.execute(
                select(WorkspaceLLMConfigModel).where(
                    WorkspaceLLMConfigModel.workspace_id == config.workspace_id
                )
            )
            existing_row = existing.scalar_one_or_none()
            if existing_row:
                for key, value in self._to_orm_kwargs(config).items():
                    setattr(existing_row, key, value)
            else:
                self._session.add(
                    WorkspaceLLMConfigModel(**self._to_orm_kwargs(config))
                )
            await self._session.commit()
            return config
        except SQLAlchemyError as e:
            await self._session.rollback()
            raise RepositoryError(
                "Database error upserting workspace LLM config"
            ) from e

    @staticmethod
    def _to_domain(model: WorkspaceLLMConfigModel) -> WorkspaceLLMConfig:
        return WorkspaceLLMConfig(
            workspace_id=model.workspace_id,
            provider=model.provider,
            model=model.model,
            temperature=model.temperature,
            max_tokens=model.max_tokens,
            base_url=model.base_url,
            api_key=model.api_key,
            id=model.id,
            updated_at=model.updated_at,
        )

    @staticmethod
    def _to_orm_kwargs(config: WorkspaceLLMConfig) -> dict:
        return {
            "id": config.id,
            "workspace_id": config.workspace_id,
            "provider": config.provider,
            "model": config.model,
            "temperature": config.temperature,
            "max_tokens": config.max_tokens,
            "base_url": config.base_url,
            "api_key": config.api_key,
            "updated_at": config.updated_at,
        }
