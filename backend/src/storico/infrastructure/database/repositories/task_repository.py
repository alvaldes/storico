"""SQLAlchemy implementation of the TaskRepository port."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from storico.domain.entities import EntityNotFound, RepositoryError, Task
from storico.domain.ports import TaskRepository
from storico.infrastructure.database.models import TaskModel


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
            status=model.status,
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
            "status": task.status,
            "priority": task.priority,
            "labels": {"items": task.labels} if task.labels else None,
            "dependencies": {"items": task.dependencies} if task.dependencies else None,
            "created_at": task.created_at,
            "updated_at": task.updated_at,
        }
