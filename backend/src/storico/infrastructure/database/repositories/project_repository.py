"""SQLAlchemy implementation of the ProjectRepository port."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from storico.domain.entities import EntityNotFound, Project, ProjectWithCount, RepositoryError
from storico.domain.ports import ProjectRepository
from storico.infrastructure.database.models import ProjectModel, UserStoryModel
from storico.infrastructure.database.pagination import fetch_page, with_total


class SQLAlchemyProjectRepository(ProjectRepository):
    """Repository implementation for Project entities using SQLAlchemy async sessions."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save(self, project: Project) -> Project:
        try:
            existing = await self._session.get(ProjectModel, project.id)
            if existing:
                kwargs = self._to_orm_kwargs(project)
                kwargs["updated_at"] = datetime.now(UTC)
                for key, value in kwargs.items():
                    setattr(existing, key, value)
            else:
                self._session.add(ProjectModel(**self._to_orm_kwargs(project)))
            await self._session.commit()
            return project
        except SQLAlchemyError as e:
            await self._session.rollback()
            raise RepositoryError("Database error saving project") from e

    async def find_by_id(self, project_id: UUID) -> Project | None:
        result = await self._session.get(ProjectModel, project_id)
        return self._to_domain(result) if result else None

    async def find_by_id_with_count(self, project_id: UUID) -> ProjectWithCount | None:
        """Fetch a single project plus its user-story count in one round-trip.

        Uses a LEFT OUTER JOIN + GROUP BY on ``ProjectModel.id`` so the
        caller gets ``(project, story_count)`` without a second
        ``count_stories`` query. Left outer join keeps projects that have
        no user stories yet (count == 0).
        """
        stmt = (
            select(ProjectModel, func.count(UserStoryModel.id).label("story_count"))
            .outerjoin(UserStoryModel, UserStoryModel.project_id == ProjectModel.id)
            .where(ProjectModel.id == project_id)
            .group_by(ProjectModel.id)
        )
        result = await self._session.execute(stmt)
        row = result.first()
        if row is None:
            return None
        model, story_count = row
        return ProjectWithCount(project=self._to_domain(model), story_count=story_count)

    async def list_page(
        self, workspace_id: UUID, *, limit: int, offset: int
    ) -> tuple[list[ProjectWithCount], int]:
        """Return one page of projects with their story counts, plus the total.

        The LEFT OUTER JOIN + GROUP BY folds the per-project story count into
        the same round-trip as the rows — the N+1 pattern where the list was
        followed by a ``count_stories`` call per project stays dead. That
        matters against a remote Supabase/Neon pool where each round-trip
        costs network latency.

        The page and its total come from one statement: ``count(*) OVER ()``
        rides on the rows' own query (see ``fetch_page``), so no separate
        ``SELECT COUNT(*)`` is issued on the normal path.

        Results are ordered by ``created_at DESC, id DESC`` in SQL — a
        requirement, not decoration: ``LIMIT``/``OFFSET`` over an unordered
        set is undefined behaviour and a row could repeat or vanish between
        pages. ``id DESC`` is the tiebreaker, so two rows written in the same
        instant cannot swap.
        """
        stmt = (
            select(ProjectModel, func.count(UserStoryModel.id).label("story_count"))
            .outerjoin(UserStoryModel, UserStoryModel.project_id == ProjectModel.id)
            .where(ProjectModel.workspace_id == workspace_id)
            .group_by(ProjectModel.id)
            .order_by(ProjectModel.created_at.desc(), ProjectModel.id.desc())
        )
        count_stmt = (
            select(func.count())
            .select_from(ProjectModel)
            .where(ProjectModel.workspace_id == workspace_id)
        )
        rows, total = await fetch_page(
            self._session, with_total(stmt), count_stmt, limit=limit, offset=offset
        )
        return [
            ProjectWithCount(project=self._to_domain(model), story_count=story_count)
            for model, story_count, _total in rows
        ], total

    async def list(self) -> list[Project]:
        result = await self._session.execute(select(ProjectModel))
        return [self._to_domain(row) for row in result.scalars()]

    async def delete(self, project_id: UUID) -> None:
        stmt = delete(ProjectModel).where(ProjectModel.id == project_id)
        result = await self._session.execute(stmt)
        await self._session.commit()
        if result.rowcount == 0:
            raise EntityNotFound("Project", str(project_id))

    async def count_stories(self, project_id: UUID) -> int:
        stmt = (
            select(func.count())
            .select_from(UserStoryModel)
            .where(UserStoryModel.project_id == project_id)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one()

    async def count_by_workspace(self, workspace_id: UUID) -> int:
        stmt = (
            select(func.count())
            .select_from(ProjectModel)
            .where(ProjectModel.workspace_id == workspace_id)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one()

    def _to_domain(self, model: ProjectModel) -> Project:
        return Project(
            name=model.name,
            workspace_id=model.workspace_id,
            description=model.description,
            icon=model.icon,
            created_by=model.created_by,
            id=model.id,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )

    @staticmethod
    def _to_orm_kwargs(project: Project) -> dict:
        return {
            "id": project.id,
            "name": project.name,
            "workspace_id": project.workspace_id,
            "description": project.description,
            "icon": project.icon,
            "created_by": project.created_by,
            "created_at": project.created_at,
            "updated_at": project.updated_at,
        }
