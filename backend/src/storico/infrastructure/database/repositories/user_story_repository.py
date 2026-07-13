"""SQLAlchemy implementation of the UserStoryRepository port."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from storico.domain.entities import EntityNotFound, RepositoryError, UserStory, UserStoryStatus
from storico.domain.ports import UserStoryRepository
from storico.infrastructure.database.models import UserStoryModel


class SQLAlchemyUserStoryRepository(UserStoryRepository):
    """Repository implementation for UserStory entities using SQLAlchemy async sessions."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save(self, user_story: UserStory) -> UserStory:
        try:
            existing = await self._session.get(UserStoryModel, user_story.id)
            if existing:
                for key, value in self._to_orm_kwargs(user_story).items():
                    setattr(existing, key, value)
            else:
                self._session.add(UserStoryModel(**self._to_orm_kwargs(user_story)))
            await self._session.commit()
            return user_story
        except SQLAlchemyError as e:
            await self._session.rollback()
            raise RepositoryError("Database error saving user story") from e

    async def find_by_id(self, user_story_id: UUID) -> UserStory | None:
        result = await self._session.get(UserStoryModel, user_story_id)
        return self._to_domain(result) if result else None

    async def list_by_project(self, project_id: UUID) -> list[UserStory]:
        stmt = select(UserStoryModel).where(UserStoryModel.project_id == project_id)
        result = await self._session.execute(stmt)
        return [self._to_domain(row) for row in result.scalars()]

    async def list(self) -> list[UserStory]:
        result = await self._session.execute(select(UserStoryModel))
        return [self._to_domain(row) for row in result.scalars()]

    async def delete(self, user_story_id: UUID) -> None:
        stmt = delete(UserStoryModel).where(UserStoryModel.id == user_story_id)
        result = await self._session.execute(stmt)
        await self._session.commit()
        if result.rowcount == 0:
            raise EntityNotFound("UserStory", str(user_story_id))

    def _to_domain(self, model: UserStoryModel) -> UserStory:
        return UserStory(
            project_id=model.project_id,
            actor=model.actor,
            feature=model.feature,
            benefit=model.benefit,
            raw_text=model.raw_text,
            id=model.id,
            created_at=model.created_at,
            status=UserStoryStatus(model.status),
        )

    @staticmethod
    def _to_orm_kwargs(user_story: UserStory) -> dict:
        return {
            "id": user_story.id,
            "project_id": user_story.project_id,
            "actor": user_story.actor,
            "feature": user_story.feature,
            "benefit": user_story.benefit,
            "raw_text": user_story.raw_text,
            "created_at": user_story.created_at,
            "status": user_story.status.value,
        }
