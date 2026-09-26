"""SQLAlchemy implementation of the UserStoryRepository port."""

from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from storico.domain.entities import EntityNotFound, RepositoryError, UserStory, UserStoryStatus
from storico.domain.ports import UserStoryRepository
from storico.infrastructure.database.models import ProjectModel, UserStoryModel
from storico.infrastructure.database.pagination import fetch_page, with_total


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

    async def list_page(
        self,
        *,
        workspace_id: UUID | None = None,
        project_id: UUID | None = None,
        workspace_ids: list[UUID] | None = None,
        limit: int,
        offset: int,
    ) -> tuple[list[UserStory], int]:
        """Return one page of stories for exactly one scope, plus the total.

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
        scopes = [value for value in (workspace_ids, project_id, workspace_id) if value is not None]
        if len(scopes) != 1:
            raise ValueError(
                "list_page requires exactly one of workspace_id, project_id or workspace_ids; "
                f"got {len(scopes)}"
            )

        if workspace_ids is not None:
            if not workspace_ids:
                return [], 0
            scope = ProjectModel.workspace_id.in_(workspace_ids)
            stmt = select(UserStoryModel).join(ProjectModel).where(scope)
            count_stmt = (
                select(func.count()).select_from(UserStoryModel).join(ProjectModel).where(scope)
            )
        elif project_id is not None:
            scope = UserStoryModel.project_id == project_id
            stmt = select(UserStoryModel).where(scope)
            count_stmt = select(func.count()).select_from(UserStoryModel).where(scope)
        elif workspace_id is not None:
            scope = ProjectModel.workspace_id == workspace_id
            stmt = select(UserStoryModel).join(ProjectModel).where(scope)
            count_stmt = (
                select(func.count()).select_from(UserStoryModel).join(ProjectModel).where(scope)
            )
        stmt = stmt.order_by(UserStoryModel.created_at.desc(), UserStoryModel.id.desc())
        rows, total = await fetch_page(
            self._session, with_total(stmt), count_stmt, limit=limit, offset=offset
        )
        return [self._to_domain(model) for model, _total in rows], total

    async def list_by_workspace(self, workspace_id: UUID) -> list[UserStory]:
        stmt = (
            select(UserStoryModel)
            .join(ProjectModel)
            .where(ProjectModel.workspace_id == workspace_id)
        )
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

    async def find_by_parts(
        self, project_id: UUID, actor: str, feature: str, benefit: str
    ) -> UserStory | None:
        stmt = select(UserStoryModel).where(
            UserStoryModel.project_id == project_id,
            UserStoryModel.actor == actor,
            UserStoryModel.feature == feature,
            UserStoryModel.benefit == benefit,
        )
        result = await self._session.execute(stmt)
        model = result.scalars().first()
        return self._to_domain(model) if model else None

    async def list_parts_by_project(self, project_id: UUID) -> list[tuple[str, str, str, UUID]]:
        # Only the four columns are selected, not full ORM entities: the caller
        # compares parts in Python to find duplicates, so loading whole rows
        # would pay hydration cost for fields it never reads.
        stmt = select(
            UserStoryModel.actor,
            UserStoryModel.feature,
            UserStoryModel.benefit,
            UserStoryModel.id,
        ).where(UserStoryModel.project_id == project_id)
        result = await self._session.execute(stmt)
        return list(result.all())

    async def save_many(self, user_stories: Sequence[UserStory]) -> list[UserStory]:
        # Empty input is answered before any statement: no rows means no work,
        # not a round-trip (same rule as ``list_page`` with an empty
        # ``workspace_ids``).
        if not user_stories:
            return []
        try:
            # One flush and one commit for the whole batch: per-row ``save``
            # calls would commit per row and lose atomicity — the exact reason
            # this method exists.
            self._session.add_all(
                UserStoryModel(**self._to_orm_kwargs(story)) for story in user_stories
            )
            await self._session.commit()
            return list(user_stories)
        except SQLAlchemyError as e:
            await self._session.rollback()
            raise RepositoryError("Database error saving user stories") from e

    def _to_domain(self, model: UserStoryModel) -> UserStory:
        return UserStory(
            project_id=model.project_id,
            actor=model.actor,
            feature=model.feature,
            benefit=model.benefit,
            raw_text=model.raw_text,
            id=model.id,
            created_at=model.created_at,
            updated_at=model.updated_at,
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
            "updated_at": user_story.updated_at,
            "status": user_story.status.value,
        }
