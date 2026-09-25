"""SQLAlchemy implementation of the TaskRepository port."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from storico.domain.entities import EntityNotFound, RepositoryError, Task
from storico.domain.entities.task import TaskStatus
from storico.domain.ports import TaskRepository
from storico.infrastructure.database.models import ProjectModel, TaskModel, UserStoryModel
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

    async def list_page(
        self,
        *,
        workspace_id: UUID | None = None,
        user_story_id: UUID | None = None,
        workspace_ids: list[UUID] | None = None,
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
            stmt = select(TaskModel).where(scope)
            count_stmt = select(func.count()).select_from(TaskModel).where(scope)
        elif workspace_id is not None:
            # Tasks have no workspace column: walk ``task → story → project``.
            scope = ProjectModel.workspace_id == workspace_id
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
            "title": task.title,
            "description": task.description,
            "status": task.status.value,
            "priority": task.priority,
            "labels": {"items": task.labels} if task.labels else None,
            "dependencies": {"items": task.dependencies} if task.dependencies else None,
            "created_at": task.created_at,
            "updated_at": task.updated_at,
        }
