"""SQLAlchemy implementation of the TaskRepository port."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from storico.domain.entities import EntityNotFound, RepositoryError, Task
from storico.domain.entities.task import TaskStatus
from storico.domain.ports import TaskRepository
from storico.infrastructure.database.models import ProjectModel, TaskModel, UserStoryModel


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

    async def list_by_workspaces(self, workspace_ids: list[UUID]) -> list[Task]:
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
            select(TaskModel)
            .join(UserStoryModel)
            .join(ProjectModel)
            .where(ProjectModel.workspace_id.in_(workspace_ids))
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
