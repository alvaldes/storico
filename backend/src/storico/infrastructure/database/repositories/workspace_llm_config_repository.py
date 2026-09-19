"""SQLAlchemy implementation of the WorkspaceLLMConfigRepository port."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from storico.domain.entities import RepositoryError, WorkspaceLLMConfig
from storico.domain.ports import CipherPort, WorkspaceLLMConfigRepository
from storico.infrastructure.database.models import WorkspaceLLMConfigModel


class SQLAlchemyWorkspaceLLMConfigRepository(WorkspaceLLMConfigRepository):
    """Repository implementation for WorkspaceLLMConfig entities using SQLAlchemy async sessions.

    The credential is encrypted on the way into the column and decrypted on the way out,
    and these are the only two points that touch it. Every caller — the settings routes,
    the model probe, the extraction route that passes the key into the background task —
    works with the domain entity, so no caller ever holds ciphertext and no caller can
    forget to convert it.
    """

    def __init__(self, session: AsyncSession, cipher: CipherPort) -> None:
        self._session = session
        self._cipher = cipher

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
                self._session.add(WorkspaceLLMConfigModel(**self._to_orm_kwargs(config)))
            await self._session.commit()
            return config
        except SQLAlchemyError as e:
            await self._session.rollback()
            raise RepositoryError("Database error upserting workspace LLM config") from e

    def _to_domain(self, model: WorkspaceLLMConfigModel) -> WorkspaceLLMConfig:
        """Build the entity with the credential decrypted.

        Decryption tolerates a value that is not ciphertext, so a row written before
        encryption existed reads back as the plaintext it holds.
        """
        return WorkspaceLLMConfig(
            workspace_id=model.workspace_id,
            provider=model.provider,
            model=model.model,
            temperature=model.temperature,
            max_tokens=model.max_tokens,
            base_url=model.base_url,
            api_key=self._decrypt(model.api_key),
            id=model.id,
            updated_at=model.updated_at,
        )

    def _to_orm_kwargs(self, config: WorkspaceLLMConfig) -> dict:
        """Build the column values with the credential encrypted."""
        return {
            "id": config.id,
            "workspace_id": config.workspace_id,
            "provider": config.provider,
            "model": config.model,
            "temperature": config.temperature,
            "max_tokens": config.max_tokens,
            "base_url": config.base_url,
            "api_key": self._encrypt(config.api_key),
            "updated_at": config.updated_at,
        }

    def _encrypt(self, value: str | None) -> str | None:
        """Encrypt a credential, and leave an absent one absent.

        ``None`` and the empty string are the two spellings of "no credential". Neither
        reaches the cipher: there is no secret to protect, and the route layer already
        normalizes a blank to ``None`` before a write, so encrypting it would only spend a
        token to store a value that has to be decrypted back to nothing.
        """
        if not value:
            return value
        return self._cipher.encrypt(value)

    def _decrypt(self, value: str | None) -> str | None:
        """Decrypt a stored credential, and leave an absent one absent."""
        if not value:
            return value
        return self._cipher.decrypt(value)
