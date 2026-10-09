"""SQLAlchemy implementation of the TrelloExportRepository port."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from storico.domain.entities import RepositoryError
from storico.domain.entities.trello_export import TrelloExport, TrelloExportScope
from storico.domain.ports import TrelloExportRepository
from storico.infrastructure.database.models import TrelloExportModel


class SQLAlchemyTrelloExportRepository(TrelloExportRepository):
    """Repository implementation for TrelloExport entities using SQLAlchemy async sessions."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save(self, export: TrelloExport) -> TrelloExport:
        try:
            existing = await self._session.get(TrelloExportModel, export.id)
            if existing:
                for key, value in self._to_orm_kwargs(export).items():
                    setattr(existing, key, value)
            else:
                self._session.add(TrelloExportModel(**self._to_orm_kwargs(export)))
            await self._session.commit()
            return export
        except SQLAlchemyError as e:
            await self._session.rollback()
            raise RepositoryError("Database error saving Trello export job") from e

    async def find_by_id(self, export_id: UUID) -> TrelloExport | None:
        result = await self._session.get(TrelloExportModel, export_id)
        return self._to_domain(result) if result else None

    @staticmethod
    def _to_domain(model: TrelloExportModel) -> TrelloExport:
        return TrelloExport(
            workspace_id=model.workspace_id,
            scope=TrelloExportScope(model.scope),
            project_id=model.project_id,
            user_story_id=model.user_story_id,
            status=model.status,
            error_code=model.error_code,
            board_id=model.board_id,
            board_url=model.board_url,
            cards_created=model.cards_created,
            id=model.id,
            created_at=model.created_at,
            completed_at=model.completed_at,
        )

    @staticmethod
    def _to_orm_kwargs(export: TrelloExport) -> dict:
        return {
            "id": export.id,
            "workspace_id": export.workspace_id,
            "scope": export.scope.value,
            "project_id": export.project_id,
            "user_story_id": export.user_story_id,
            "status": export.status,
            "error_code": export.error_code,
            "board_id": export.board_id,
            "board_url": export.board_url,
            "cards_created": export.cards_created,
            "created_at": export.created_at,
            "completed_at": export.completed_at,
        }
