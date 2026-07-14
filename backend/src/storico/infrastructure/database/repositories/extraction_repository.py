"""SQLAlchemy implementation of the ExtractionRepository port."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from storico.domain.entities import EntityNotFound, Extraction, RepositoryError
from storico.domain.ports import ExtractionRepository
from storico.infrastructure.database.models import ExtractionModel, ProjectModel, UserStoryModel


class SQLAlchemyExtractionRepository(ExtractionRepository):
    """Repository implementation for Extraction entities using SQLAlchemy async sessions."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save(self, extraction: Extraction) -> Extraction:
        try:
            existing = await self._session.get(ExtractionModel, extraction.id)
            if existing:
                for key, value in self._to_orm_kwargs(extraction).items():
                    setattr(existing, key, value)
            else:
                self._session.add(ExtractionModel(**self._to_orm_kwargs(extraction)))
            await self._session.commit()
            return extraction
        except SQLAlchemyError as e:
            await self._session.rollback()
            raise RepositoryError("Database error saving extraction") from e

    async def find_by_id(self, extraction_id: UUID) -> Extraction | None:
        result = await self._session.get(ExtractionModel, extraction_id)
        return self._to_domain(result) if result else None

    async def list_by_story(self, user_story_id: UUID) -> list[Extraction]:
        stmt = select(ExtractionModel).where(ExtractionModel.user_story_id == user_story_id)
        result = await self._session.execute(stmt)
        return [self._to_domain(row) for row in result.scalars()]

    async def list_by_workspace(self, workspace_id: UUID) -> list[Extraction]:
        stmt = (
            select(ExtractionModel)
            .join(UserStoryModel)
            .join(ProjectModel)
            .where(ProjectModel.workspace_id == workspace_id)
        )
        result = await self._session.execute(stmt)
        return [self._to_domain(row) for row in result.scalars()]

    async def list(self) -> list[Extraction]:
        result = await self._session.execute(select(ExtractionModel))
        return [self._to_domain(row) for row in result.scalars()]

    async def delete(self, extraction_id: UUID) -> None:
        stmt = delete(ExtractionModel).where(ExtractionModel.id == extraction_id)
        result = await self._session.execute(stmt)
        await self._session.commit()
        if result.rowcount == 0:
            raise EntityNotFound("Extraction", str(extraction_id))

    def _to_domain(self, model: ExtractionModel) -> Extraction:
        return Extraction(
            user_story_id=model.user_story_id,
            model_used=model.model_used,
            raw_response=model.raw_response,
            status=model.status,
            error_info=model.error_info,
            prompt_config=model.prompt_config,
            confidence_score=model.confidence_score,
            id=model.id,
            created_at=model.created_at,
        )

    @staticmethod
    def _to_orm_kwargs(extraction: Extraction) -> dict:
        return {
            "id": extraction.id,
            "user_story_id": extraction.user_story_id,
            "model_used": extraction.model_used,
            "status": extraction.status,
            "error_info": extraction.error_info,
            "raw_response": extraction.raw_response,
            "prompt_config": extraction.prompt_config,
            "confidence_score": extraction.confidence_score,
            "created_at": extraction.created_at,
        }
