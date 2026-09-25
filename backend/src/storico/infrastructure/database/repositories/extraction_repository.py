"""SQLAlchemy implementation of the ExtractionRepository port."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from storico.domain.entities import EntityNotFound, Extraction, RepositoryError
from storico.domain.entities.extraction import ExtractionStatus
from storico.domain.entities.user_story import UserStoryStatus
from storico.domain.ports import ExtractionRepository
from storico.infrastructure.database.models import ExtractionModel, ProjectModel, UserStoryModel
from storico.infrastructure.database.pagination import fetch_page, with_total


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

    async def list_page(
        self,
        *,
        workspace_id: UUID | None = None,
        user_story_id: UUID | None = None,
        workspace_ids: list[UUID] | None = None,
        limit: int,
        offset: int,
    ) -> tuple[list[Extraction], int]:
        """Return one page of extractions for exactly one scope, plus the total.

        The page and its total come from one statement: ``count(*) OVER ()``
        rides on the rows' own query (see ``fetch_page``), so no separate
        ``SELECT COUNT(*)`` is issued on the normal path.

        An empty ``workspace_ids`` is answered here rather than sent as
        ``IN ()``: no memberships means no rows, not a statement — and against
        the dev pooler a statement costs ~2s (a bare ``SELECT 1`` already
        measures 800ms in ``/api/v1/health``), so an unasked statement is pure
        latency. This is also what replaced the old per-workspace fold, whose
        caller in 12 workspaces paid for 12 statements and measured 25-32s.

        Results are ordered by ``created_at DESC, id DESC`` in SQL — a
        requirement, not decoration: ``LIMIT``/``OFFSET`` over an unordered
        set is undefined behaviour and a row could repeat or vanish between
        pages. ``id DESC`` is the tiebreaker, so two rows written in the same
        instant cannot swap.

        More than one scope is refused rather than resolved: the three arguments
        are mutually exclusive, and a plain ``if``/``elif`` chain would let a
        caller pass two and silently get one of them -- a wrong answer that looks
        like a right one, which is the exact failure mode this change removes.
        """
        scopes = [
            value for value in (workspace_ids, user_story_id, workspace_id) if value is not None
        ]
        if len(scopes) != 1:
            raise ValueError(
                "list_page requires exactly one of workspace_id, user_story_id or workspace_ids; "
                f"got {len(scopes)}"
            )

        if workspace_ids is not None:
            if not workspace_ids:
                return [], 0
            scope = ProjectModel.workspace_id.in_(workspace_ids)
            stmt = select(ExtractionModel).join(UserStoryModel).join(ProjectModel).where(scope)
            count_stmt = (
                select(func.count())
                .select_from(ExtractionModel)
                .join(UserStoryModel)
                .join(ProjectModel)
                .where(scope)
            )
        elif user_story_id is not None:
            # No join: extractions carry their own ``user_story_id`` foreign key.
            scope = ExtractionModel.user_story_id == user_story_id
            stmt = select(ExtractionModel).where(scope)
            count_stmt = select(func.count()).select_from(ExtractionModel).where(scope)
        elif workspace_id is not None:
            # Extractions have no workspace column: walk ``extraction → story → project``.
            scope = ProjectModel.workspace_id == workspace_id
            stmt = select(ExtractionModel).join(UserStoryModel).join(ProjectModel).where(scope)
            count_stmt = (
                select(func.count())
                .select_from(ExtractionModel)
                .join(UserStoryModel)
                .join(ProjectModel)
                .where(scope)
            )
        stmt = stmt.order_by(ExtractionModel.created_at.desc(), ExtractionModel.id.desc())
        rows, total = await fetch_page(
            self._session, with_total(stmt), count_stmt, limit=limit, offset=offset
        )
        return [self._to_domain(model) for model, _total in rows], total

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
