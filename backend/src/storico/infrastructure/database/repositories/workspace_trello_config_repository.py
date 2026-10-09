"""SQLAlchemy implementation of the WorkspaceTrelloConfigRepository port."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from storico.domain.entities import RepositoryError, WorkspaceTrelloConfig
from storico.domain.ports import CipherPort, WorkspaceTrelloConfigRepository
from storico.infrastructure.database.models import WorkspaceTrelloConfigModel


class SQLAlchemyWorkspaceTrelloConfigRepository(WorkspaceTrelloConfigRepository):
    """Repository implementation for WorkspaceTrelloConfig entities using SQLAlchemy async sessions.

    The credentials are encrypted on the way into the columns and decrypted on the way
    out, and these are the only two points that touch them. Every caller — the settings
    routes, and later the Trello export adapter — works with the domain entity, so no
    caller ever holds ciphertext and no caller can forget to convert it.
    """

    def __init__(self, session: AsyncSession, cipher: CipherPort) -> None:
        self._session = session
        self._cipher = cipher

    async def get(self, workspace_id: UUID) -> WorkspaceTrelloConfig | None:
        stmt = select(WorkspaceTrelloConfigModel).where(
            WorkspaceTrelloConfigModel.workspace_id == workspace_id
        )
        result = await self._session.execute(stmt)
        row = result.scalar_one_or_none()
        return self._to_domain(row) if row else None

    async def upsert(self, config: WorkspaceTrelloConfig) -> WorkspaceTrelloConfig:
        try:
            existing = await self._session.execute(
                select(WorkspaceTrelloConfigModel).where(
                    WorkspaceTrelloConfigModel.workspace_id == config.workspace_id
                )
            )
            existing_row = existing.scalar_one_or_none()
            if existing_row:
                for key, value in self._to_orm_kwargs(config).items():
                    setattr(existing_row, key, value)
            else:
                self._session.add(WorkspaceTrelloConfigModel(**self._to_orm_kwargs(config)))
            await self._session.commit()
            return config
        except SQLAlchemyError as e:
            await self._session.rollback()
            raise RepositoryError("Database error upserting workspace Trello config") from e

    def _to_domain(self, model: WorkspaceTrelloConfigModel) -> WorkspaceTrelloConfig:
        """Build the entity with the credentials decrypted.

        Decryption tolerates a value that is not ciphertext, which ``FernetCipher``
        provides and the sibling relies on for rows written before encryption existed.
        This table is new in ``0030``, so no such row can exist here: the tolerance is
        inherited, and it is what keeps a value inserted straight into the column
        readable instead of raising on the way out.
        """
        return WorkspaceTrelloConfig(
            workspace_id=model.workspace_id,
            api_key=self._decrypt(model.api_key),
            token=self._decrypt(model.token),
            id=model.id,
            updated_at=model.updated_at,
        )

    def _to_orm_kwargs(self, config: WorkspaceTrelloConfig) -> dict:
        """Build the column values with the credentials encrypted."""
        return {
            "id": config.id,
            "workspace_id": config.workspace_id,
            "api_key": self._encrypt(config.api_key),
            "token": self._encrypt(config.token),
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
