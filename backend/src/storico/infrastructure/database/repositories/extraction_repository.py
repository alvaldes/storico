"""SQLAlchemy implementation of the ExtractionRepository port."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from storico.domain.entities import EntityNotFound, Extraction, RepositoryError
from storico.domain.entities.extraction import ExtractionStatus
from storico.domain.entities.user_story import UserStoryStatus
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

    async def list_by_workspaces(self, workspace_ids: list[UUID]) -> list[Extraction]:
        """One ``IN`` statement instead of one per workspace.

        The caller that needed this fans out over the workspaces a user belongs to. Against the
        dev pooler a statement costs ~2s — a bare ``SELECT 1`` already measures 800ms in
        ``/api/v1/health`` — so a caller in 12 workspaces paid for 12 of them and the request
        measured 25-32s. An empty list is answered here rather than sent as ``IN ()``: no
        memberships means no rows, not a statement.
        """
        if not workspace_ids:
            return []

        stmt = (
            select(ExtractionModel)
            .join(UserStoryModel)
            .join(ProjectModel)
            .where(ProjectModel.workspace_id.in_(workspace_ids))
        )
        result = await self._session.execute(stmt)
        return [self._to_domain(row) for row in result.scalars()]

    async def list(self) -> list[Extraction]:
        result = await self._session.execute(select(ExtractionModel))
        return [self._to_domain(row) for row in result.scalars()]

    async def delete(self, extraction_id: UUID) -> None:
        # Through the session's identity map rather than a `DELETE` plus a row count. The count was
        # correct — an earlier form was proved to raise `EntityNotFound` on the real path — but it
        # has to be read off a `CursorResult` that `Session.execute` does not admit to returning,
        # and stating the missing type invited a false alarm about the statement being unparameterized.
        # Two analyzer findings, either way, over a statement whose only value travels as a bound
        # parameter: going through the ORM says the same thing without either opening.
        existing = await self._session.get(ExtractionModel, extraction_id)
        if existing is None:
            raise EntityNotFound("Extraction", str(extraction_id))
        await self._session.delete(existing)
        await self._session.commit()

    def _to_domain(self, model: ExtractionModel) -> Extraction:
        return Extraction(
            user_story_id=model.user_story_id,
            model_used=model.model_used,
            raw_response=model.raw_response,
            status=ExtractionStatus(model.status),
            user_story_status=UserStoryStatus(model.user_story_status),
            error_info=model.error_info,
            prompt_config=model.prompt_config,
            confidence_score=model.confidence_score,
            id=model.id,
            created_at=model.created_at,
            completed_at=model.completed_at,
        )

    @staticmethod
    def _to_orm_kwargs(extraction: Extraction) -> dict:
        return {
            "id": extraction.id,
            "user_story_id": extraction.user_story_id,
            "model_used": extraction.model_used,
            "status": extraction.status.value,
            "user_story_status": extraction.user_story_status.value,
            "error_info": extraction.error_info,
            "raw_response": extraction.raw_response,
            "prompt_config": extraction.prompt_config,
            "confidence_score": extraction.confidence_score,
            "created_at": extraction.created_at,
            "completed_at": extraction.completed_at,
        }
