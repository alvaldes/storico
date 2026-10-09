"""SQLAlchemy implementation of the TaskRepository port."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import and_, delete, exists, func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from storico.domain.entities import EntityNotFound, RepositoryError, Task
from storico.domain.entities.extraction import ExtractionStatus
from storico.domain.entities.task import TaskStatus
from storico.domain.ports import TaskContextRow, TaskRepository
from storico.infrastructure.database.models import (
    ExtractionModel,
    ProjectModel,
    TaskInvalidationModel,
    TaskModel,
    UserStoryModel,
)
from storico.infrastructure.database.pagination import fetch_page, with_total


class SQLAlchemyTaskRepository(TaskRepository):
    """Repository implementation for Task entities using SQLAlchemy async sessions."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save(self, task: Task) -> Task:
        try:
            existing = await self._session.get(TaskModel, task.id)
            if existing:
                kwargs = self._to_orm_kwargs(task)
                kwargs["updated_at"] = datetime.now(UTC)
                for key, value in kwargs.items():
                    setattr(existing, key, value)
            else:
                self._session.add(TaskModel(**self._to_orm_kwargs(task)))
            await self._session.commit()
            return task
        except SQLAlchemyError as e:
            await self._session.rollback()
            raise RepositoryError("Database error saving task") from e

    async def find_by_id(self, task_id: UUID) -> Task | None:
        result = await self._session.get(TaskModel, task_id)
        return self._to_domain(result) if result else None

    @staticmethod
    def _current_version_only(scope):
        """Join the current-version predicate to an existing scope clause.

        The "no higher-numbered completed version of this story" form, served
        by ``uq_extractions_story_version`` and needing no ``MAX``. It is
        joined to the same ``scope`` the page statement and its fallback
        count share, so both halves of a read answer one question and the
        total cannot keep counting superseded rows. Currency is derived —
        ``status == completed`` plus the highest ``version_number`` — never
        stored (slice (a)'s decision: no flag, no trigger, no matview).
        """
        current = aliased(ExtractionModel)
        return and_(
            scope,
            TaskModel.extraction_id == current.id,
            current.status == ExtractionStatus.COMPLETED,
            ~exists(
                select(1).where(
                    ExtractionModel.user_story_id == current.user_story_id,
                    ExtractionModel.status == ExtractionStatus.COMPLETED,
                    ExtractionModel.version_number > current.version_number,
                )
            ),
        )

    async def list_page(
        self,
        *,
        workspace_id: UUID | None = None,
        user_story_id: UUID | None = None,
        workspace_ids: list[UUID] | None = None,
        extraction_id: UUID | None = None,
        project_id: UUID | None = None,
        limit: int,
        offset: int,
    ) -> tuple[list[Task], int]:
        """Return one page of tasks for exactly one scope, plus the total.

        The page and its total come from one statement: ``count(*) OVER ()``
        rides on the rows' own query (see ``fetch_page``), so no separate
        ``SELECT COUNT(*)`` is issued on the normal path.

        An empty ``workspace_ids`` is answered here rather than sent as
        ``IN ()``: no memberships means no rows, not a statement — and against
        the dev pooler a statement costs ~2s (a bare ``SELECT 1`` already
        measures 800ms in ``/api/v1/health``), so an unasked statement is pure
        latency.

        Results are ordered by ``created_at DESC, id DESC`` in SQL — a
        requirement, not decoration: ``LIMIT``/``OFFSET`` over an unordered
        set is undefined behaviour and a row could repeat or vanish between
        pages. ``id DESC`` is the tiebreaker, so two rows written in the same
        instant cannot swap.

        More than one scope is refused rather than resolved: the four arguments
        are mutually exclusive, and a plain ``if``/``elif`` chain would let a
        caller pass two and silently get one of them -- a wrong answer that looks
        like a right one, which is the exact failure mode this change removes.

        Reads answer the story's current version only (D-a-5 item 2): the
        story scope pins ``extraction_id`` to the highest-numbered
        ``completed`` run, the workspace, ``workspace_ids`` and ``project_id``
        scopes drop any task whose story has a higher-numbered ``completed``
        run. Both predicates are joined to the ``scope`` clause below, so the
        page and its ``total`` — the window count and the past-the-end
        fallback count alike — are filtered together. An explicit
        ``extraction_id`` (story scope only; anything else raises
        ``ValueError``) bypasses the predicate and reads exactly that version.
        """
        scopes = [
            value
            for value in (workspace_ids, user_story_id, workspace_id, project_id)
            if value is not None
        ]
        if len(scopes) != 1:
            raise ValueError(
                "list_page requires exactly one of workspace_id, user_story_id, "
                f"workspace_ids or project_id; got {len(scopes)}"
            )
        if extraction_id is not None and user_story_id is None:
            raise ValueError(
                "extraction_id requires user_story_id: reading a named version "
                "is a story-scoped question"
            )

        if workspace_ids is not None:
            if not workspace_ids:
                return [], 0
            scope = self._current_version_only(ProjectModel.workspace_id.in_(workspace_ids))
            stmt = select(TaskModel).join(UserStoryModel).join(ProjectModel).where(scope)
            count_stmt = (
                select(func.count())
                .select_from(TaskModel)
                .join(UserStoryModel)
                .join(ProjectModel)
                .where(scope)
            )
        elif user_story_id is not None:
            # No join: tasks carry their own ``user_story_id`` foreign key.
            scope = TaskModel.user_story_id == user_story_id
            if extraction_id is not None:
                # Reading a named version on purpose: no currency predicate, or
                # the selector could never show a superseded version's tasks.
                scope = and_(scope, TaskModel.extraction_id == extraction_id)
            else:
                # The current version only. An empty subquery yields NULL and
                # matches no row, so a story with no completed run reads no
                # tasks — the honest answer to "what is the current output?".
                scope = and_(
                    scope,
                    TaskModel.extraction_id
                    == select(ExtractionModel.id)
                    .where(
                        ExtractionModel.user_story_id == user_story_id,
                        ExtractionModel.status == ExtractionStatus.COMPLETED,
                    )
                    .order_by(ExtractionModel.version_number.desc())
                    .limit(1)
                    .scalar_subquery(),
                )
            stmt = select(TaskModel).where(scope)
            count_stmt = select(func.count()).select_from(TaskModel).where(scope)
        elif workspace_id is not None:
            # Tasks have no workspace column: walk ``task → story → project``.
            scope = self._current_version_only(ProjectModel.workspace_id == workspace_id)
            stmt = select(TaskModel).join(UserStoryModel).join(ProjectModel).where(scope)
            count_stmt = (
                select(func.count())
                .select_from(TaskModel)
                .join(UserStoryModel)
                .join(ProjectModel)
                .where(scope)
            )
        elif project_id is not None:
            # Tasks have no project column either: the same ``task → story →
            # project`` walk, filtered on the project itself. The currency
            # predicate rides along (D6 of feature ``versioning-visibility``),
            # so a project-scoped board obeys the same contract as the
            # workspace board: each story's current version only.
            scope = self._current_version_only(ProjectModel.id == project_id)
            stmt = select(TaskModel).join(UserStoryModel).join(ProjectModel).where(scope)
            count_stmt = (
                select(func.count())
                .select_from(TaskModel)
                .join(UserStoryModel)
                .join(ProjectModel)
                .where(scope)
            )
        stmt = stmt.order_by(TaskModel.created_at.desc(), TaskModel.id.desc())
        rows, total = await fetch_page(
            self._session, with_total(stmt), count_stmt, limit=limit, offset=offset
        )
        return [self._to_domain(model) for model, _total in rows], total

    async def list_for_context(
        self, project_id: UUID, *, exclude_story_id: UUID
    ) -> list[TaskContextRow]:
        """Current-version, valid tasks of the project except one story, unpaginated.

        One statement, no ``LIMIT``: the story → project walk (``task →``
        ``story``), the currency predicate reused from ``_current_version_only``
        — the same "no higher-numbered completed version" shape (b)'s page and
        export reads carry, so currency is never spelled twice in this file —
        the active-mark exclusion (``NOT EXISTS`` a ``task_invalidations`` row
        with ``revoked_at IS NULL``, the predicate (a)'s partial unique index
        backs), and the excluded story. All four live in the ``WHERE``: a
        Python filter would reintroduce the silent truncation the unbounded
        read exists to prevent. Only the three columns the prompt block reads
        are selected, and the ``ORDER BY`` is the ascending ``created_at, id``
        the port documents.
        """
        stmt = (
            select(TaskModel.title, TaskModel.status, TaskModel.user_story_id)
            .join(UserStoryModel, UserStoryModel.id == TaskModel.user_story_id)
            .where(
                self._current_version_only(UserStoryModel.project_id == project_id),
                TaskModel.user_story_id != exclude_story_id,
                ~exists(
                    select(1).where(
                        TaskInvalidationModel.task_id == TaskModel.id,
                        TaskInvalidationModel.revoked_at.is_(None),
                    )
                ),
            )
            .order_by(TaskModel.created_at, TaskModel.id)
        )
        result = await self._session.execute(stmt)
        return [
            TaskContextRow(
                title=row.title,
                status=TaskStatus(row.status),
                user_story_id=row.user_story_id,
            )
            for row in result
        ]

    async def list_by_story(self, user_story_id: UUID) -> list[Task]:
        stmt = select(TaskModel).where(TaskModel.user_story_id == user_story_id)
        result = await self._session.execute(stmt)
        return [self._to_domain(row) for row in result.scalars()]

    async def list_by_workspace(self, workspace_id: UUID) -> list[Task]:
        stmt = (
            select(TaskModel)
            .join(UserStoryModel)
            .join(ProjectModel)
            .where(ProjectModel.workspace_id == workspace_id)
        )
        result = await self._session.execute(stmt)
        return [self._to_domain(row) for row in result.scalars()]

    async def list_current_by_workspace(self, workspace_id: UUID) -> list[Task]:
        """The export's read: current-version tasks, unpaginated.

        Same ``NOT EXISTS`` predicate as the workspace scope of ``list_page``,
        without the page window — the export serializes the whole workspace,
        so the filter rides the serializing statement itself.
        """
        stmt = (
            select(TaskModel)
            .join(UserStoryModel)
            .join(ProjectModel)
            .where(self._current_version_only(ProjectModel.workspace_id == workspace_id))
        )
        result = await self._session.execute(stmt)
        return [self._to_domain(row) for row in result.scalars()]

    async def list_current_by_project(self, project_id: UUID) -> list[Task]:
        """The Trello export's project-scope read: the same predicate, one project."""
        stmt = (
            select(TaskModel)
            .join(UserStoryModel)
            .where(self._current_version_only(UserStoryModel.project_id == project_id))
        )
        result = await self._session.execute(stmt)
        return [self._to_domain(row) for row in result.scalars()]

    async def list_current_by_story(self, user_story_id: UUID) -> list[Task]:
        """The Trello export's story-scope read: the story's current version only.

        No join: tasks carry their own ``user_story_id`` foreign key, and the
        currency predicate correlates on ``TaskModel.extraction_id`` itself.
        """
        stmt = select(TaskModel).where(
            self._current_version_only(TaskModel.user_story_id == user_story_id)
        )
        result = await self._session.execute(stmt)
        return [self._to_domain(row) for row in result.scalars()]

    async def list(self) -> list[Task]:
        result = await self._session.execute(select(TaskModel))
        return [self._to_domain(row) for row in result.scalars()]

    async def delete(self, task_id: UUID) -> None:
        stmt = delete(TaskModel).where(TaskModel.id == task_id)
        result = await self._session.execute(stmt)
        await self._session.commit()
        if result.rowcount == 0:
            raise EntityNotFound("Task", str(task_id))

    def _to_domain(self, model: TaskModel) -> Task:
        return Task(
            user_story_id=model.user_story_id,
            extraction_id=model.extraction_id,
            title=model.title,
            description=model.description,
            status=TaskStatus(model.status),
            priority=model.priority,
            labels=model.labels.get("items", []) if model.labels else [],
            dependencies=model.dependencies.get("items", []) if model.dependencies else [],
            id=model.id,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )

    @staticmethod
    def _to_orm_kwargs(task: Task) -> dict:
        return {
            "id": task.id,
            "user_story_id": task.user_story_id,
            "extraction_id": task.extraction_id,
            "title": task.title,
            "description": task.description,
            "status": task.status.value,
            "priority": task.priority,
            "labels": {"items": task.labels} if task.labels else None,
            "dependencies": {"items": task.dependencies} if task.dependencies else None,
            "created_at": task.created_at,
            "updated_at": task.updated_at,
        }
