"""SQLAlchemy implementation of the ProjectRepository port."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from storico.domain.entities import EntityNotFound, Project, ProjectWithCount, RepositoryError
from storico.domain.ports import ProjectRepository
from storico.infrastructure.database.models import ProjectModel, UserStoryModel, WorkspaceModel


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

    async def find_by_id_with_count(
        self, project_id: UUID
    ) -> ProjectWithCount | None:
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

    async def list_by_workspace(self, workspace_id: UUID) -> list[Project]:
        stmt = select(ProjectModel).where(
            ProjectModel.workspace_id == workspace_id
        )
        result = await self._session.execute(stmt)
        return [self._to_domain(row) for row in result.scalars()]

    async def list_by_workspace_with_counts(
        self, workspace_id: UUID
    ) -> list[ProjectWithCount]:
        """List all projects in a workspace with their story counts.

        Replaces the N+1 pattern where ``list_by_workspace`` is followed
        by a ``count_stories`` call per project. The LEFT OUTER JOIN +
        GROUP BY folds it into a single round-trip — important against a
        remote Supabase/Neon pool where each round-trip costs ~5-50ms of
        network latency.

        Returns items in the same order ``list_by_workspace`` would
        (no extra ``ORDER BY`` is added).
        """
        stmt = (
            select(
                ProjectModel, func.count(UserStoryModel.id).label("story_count")
            )
            .outerjoin(UserStoryModel, UserStoryModel.project_id == ProjectModel.id)
            .where(ProjectModel.workspace_id == workspace_id)
            .group_by(ProjectModel.id)
        )
        result = await self._session.execute(stmt)
        return [
            ProjectWithCount(project=self._to_domain(model), story_count=story_count)
            for model, story_count in result.all()
        ]

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
        stmt = select(func.count()).select_from(UserStoryModel).where(
            UserStoryModel.project_id == project_id
        )
        result = await self._session.execute(stmt)
        return result.scalar_one()

    async def count_by_workspace(self, workspace_id: UUID) -> int:
        stmt = select(func.count()).select_from(ProjectModel).where(
            ProjectModel.workspace_id == workspace_id
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
