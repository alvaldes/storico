"""SQLAlchemy implementation of the TaskInvalidationRepository port."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from storico.domain.entities import EntityNotFound, RepositoryError
from storico.domain.entities.task_invalidation import TaskInvalidation
from storico.domain.ports.task_invalidation_repository import (
    StandingRevocation,
    TaskInvalidationCandidate,
    TaskInvalidationRepository,
)
from storico.infrastructure.database.models import (
    ExtractionModel,
    TaskInvalidationModel,
    TaskModel,
)


class SQLAlchemyTaskInvalidationRepository(TaskInvalidationRepository):
    """Repository implementation for TaskInvalidation using SQLAlchemy async sessions."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, mark: TaskInvalidation) -> TaskInvalidation:
        """Insert the mark and return the entity as the table now holds it.

        A second active mark on one task is refused by the table's partial
        unique index (``uq_task_invalidations_active_task``); the refusal
        surfaces as the driver's integrity error wrapped in ``RepositoryError``
        — the caller resolves the 409 through ``find_active_by_task`` first, so
        reaching the index here is a lost race, not a normal path.
        """
        model = TaskInvalidationModel(
            id=mark.id,
            task_id=mark.task_id,
            reason=mark.reason,
            marked_by=mark.marked_by,
            marked_at=mark.marked_at,
            revoked_by=mark.revoked_by,
            revoked_at=mark.revoked_at,
        )
        try:
            self._session.add(model)
            await self._session.commit()
            await self._session.refresh(model)
        except SQLAlchemyError as e:
            await self._session.rollback()
            raise RepositoryError("Database error creating task invalidation") from e
        return self._to_domain(model)

    async def find_active_by_task(self, task_id: UUID) -> TaskInvalidation | None:
        """Return the task's active mark, or ``None`` when it has none.

        At most one row can match: the partial unique index allows one
        ``revoked_at IS NULL`` row per task. A revoked mark is history, not an
        active mark, and never answers here.
        """
        stmt = select(TaskInvalidationModel).where(
            TaskInvalidationModel.task_id == task_id,
            TaskInvalidationModel.revoked_at.is_(None),
        )
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        return self._to_domain(model) if model else None

    async def list_by_task(self, task_id: UUID) -> list[TaskInvalidation]:
        """The task's full mark history, active mark first, then ``marked_at DESC``.

        The active-first key leads because the history is read for the mark
        controls: the active mark is the row the endpoints act on. Revoked rows
        come back with their revoke attribution intact.
        """
        stmt = (
            select(TaskInvalidationModel)
            .where(TaskInvalidationModel.task_id == task_id)
            .order_by(
                TaskInvalidationModel.revoked_at.is_(None).desc(),
                TaskInvalidationModel.marked_at.desc(),
            )
        )
        result = await self._session.execute(stmt)
        return [self._to_domain(model) for model in result.scalars()]

    async def revoke(self, mark_id: UUID, *, revoked_by: UUID, revoked_at: datetime) -> None:
        """Set ``revoked_by``/``revoked_at`` on the mark's row — an UPDATE, never a DELETE.

        The statement names exactly the two revoke columns and matches only a
        still-active row, so a revoked mark can never be re-revoked silently;
        when no active row matches it raises ``EntityNotFound``.
        """
        stmt = (
            update(TaskInvalidationModel)
            .where(
                TaskInvalidationModel.id == mark_id,
                TaskInvalidationModel.revoked_at.is_(None),
            )
            .values(revoked_by=revoked_by, revoked_at=revoked_at)
        )
        try:
            result = await self._session.execute(stmt)
        except SQLAlchemyError as e:
            await self._session.rollback()
            raise RepositoryError("Database error revoking task invalidation") from e
        if result.rowcount == 0:
            await self._session.rollback()
            raise EntityNotFound("TaskInvalidation", str(mark_id))
        await self._session.commit()

    async def count_active_for_extraction(
        self, *, extraction_id: UUID, exclude_mark_id: UUID | None = None
    ) -> int:
        """The computed active-mark count, as the port documents it.

        One statement: the mark → task join scoped by the task's
        ``extraction_id``, filtered to still-active rows, with the mark being
        revoked excluded when its id is given. The value answers the revoke
        handler's pre-revoke question, so the refresh can run before the
        internally-committing ``revoke`` is called.
        """
        stmt = (
            select(func.count())
            .select_from(TaskInvalidationModel)
            .join(TaskModel, TaskModel.id == TaskInvalidationModel.task_id)
            .where(
                TaskModel.extraction_id == extraction_id,
                TaskInvalidationModel.revoked_at.is_(None),
            )
        )
        if exclude_mark_id is not None:
            stmt = stmt.where(TaskInvalidationModel.id != exclude_mark_id)
        result = await self._session.execute(stmt)
        return int(result.scalar_one())

    async def list_active_on_other_versions(
        self, *, user_story_id: UUID, exclude_extraction_id: UUID | None
    ) -> list[TaskInvalidationCandidate]:
        """The D16 candidate read, as the port documents it.

        ``extraction_id IS DISTINCT FROM`` is SQLAlchemy's ``is_distinct_from``,
        portable between the SQLite unit schema and Postgres — the same predicate
        ``!=`` would get wrong on the NULL arm. ``exclude_extraction_id=None``
        skips the predicate entirely: it excludes nothing, it does not mean
        "exclude null extraction ids" (the column is ``NOT NULL`` anyway).
        """
        stmt = (
            select(
                ExtractionModel.version_number,
                TaskModel.title,
                TaskInvalidationModel.reason,
                TaskInvalidationModel.marked_at,
            )
            .join(TaskModel, TaskModel.id == TaskInvalidationModel.task_id)
            .join(ExtractionModel, ExtractionModel.id == TaskModel.extraction_id)
            .where(
                TaskModel.user_story_id == user_story_id,
                TaskInvalidationModel.revoked_at.is_(None),
            )
            .order_by(
                ExtractionModel.version_number.desc(),
                TaskInvalidationModel.marked_at.desc(),
            )
        )
        if exclude_extraction_id is not None:
            stmt = stmt.where(TaskModel.extraction_id.is_distinct_from(exclude_extraction_id))
        result = await self._session.execute(stmt)
        return [
            TaskInvalidationCandidate(
                version_number=row.version_number,
                title=row.title,
                reason=row.reason,
                marked_at=row.marked_at,
            )
            for row in result
        ]

    async def list_standing_revocations_by_user(self, revoked_by: UUID) -> list[StandingRevocation]:
        """The account-delete pre-check's read, as the port documents it.

        A plain read over the same join the D16 candidate read uses, filtered
        the other way: by the revoker instead of the story. No wrapping — the
        statement cannot fail beyond the driver-level failures every read in
        this file shares.
        """
        stmt = (
            select(
                TaskModel.user_story_id,
                ExtractionModel.version_number,
                TaskModel.title,
            )
            .select_from(TaskInvalidationModel)
            .join(TaskModel, TaskModel.id == TaskInvalidationModel.task_id)
            .join(ExtractionModel, ExtractionModel.id == TaskModel.extraction_id)
            .where(
                TaskInvalidationModel.revoked_by == revoked_by,
                TaskInvalidationModel.revoked_at.is_not(None),
            )
            .order_by(ExtractionModel.version_number.asc(), TaskModel.title.asc())
        )
        result = await self._session.execute(stmt)
        return [
            StandingRevocation(
                user_story_id=row.user_story_id,
                version_number=row.version_number,
                title=row.title,
            )
            for row in result
        ]

    def _to_domain(self, model: TaskInvalidationModel) -> TaskInvalidation:
        return TaskInvalidation(
            task_id=model.task_id,
            reason=model.reason,
            marked_by=model.marked_by,
            marked_at=model.marked_at,
            id=model.id,
            revoked_by=model.revoked_by,
            revoked_at=model.revoked_at,
        )
