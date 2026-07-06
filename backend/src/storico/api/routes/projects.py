"""Project CRUD API routes."""

from dataclasses import replace
from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status

from storico.api.dependencies import get_repository
from storico.api.schemas.common import PaginatedResponse, PaginationParams
from storico.api.schemas.project import (
    CreateProjectRequest,
    ProjectResponse,
    UpdateProjectRequest,
)
from storico.domain.entities import EntityNotFound, Project
from storico.infrastructure.database.repositories import SQLAlchemyProjectRepository

router = APIRouter(prefix="/api/v1/projects", tags=["projects"])

ProjectRepoDep = Annotated[
    SQLAlchemyProjectRepository,
    Depends(get_repository(SQLAlchemyProjectRepository)),
]


@router.post("/", status_code=status.HTTP_201_CREATED)
async def create_project(
    body: CreateProjectRequest,
    repo: ProjectRepoDep,
) -> ProjectResponse:
    """Create a new project."""
    project = Project(
        name=body.name,
        owner_id=body.owner_id,
        description=body.description,
    )
    result = await repo.save(project)
    return ProjectResponse(
        id=result.id,
        name=result.name,
        description=result.description,
        owner_id=result.owner_id,
        created_at=result.created_at,
        updated_at=result.updated_at,
    )


@router.get("/")
async def list_projects(
    params: Annotated[PaginationParams, Depends()],
    repo: ProjectRepoDep,
) -> PaginatedResponse[ProjectResponse]:
    """List all projects with pagination."""
    all_projects = await repo.list()
    total = len(all_projects)
    start = (params.page - 1) * params.size
    items = [
        ProjectResponse(
            id=p.id,
            name=p.name,
            description=p.description,
            owner_id=p.owner_id,
            created_at=p.created_at,
            updated_at=p.updated_at,
        )
        for p in all_projects[start : start + params.size]
    ]
    return PaginatedResponse(
        items=items,
        total=total,
        page=params.page,
        size=params.size,
    )


@router.get("/{project_id}")
async def get_project(
    project_id: UUID,
    repo: ProjectRepoDep,
) -> ProjectResponse:
    """Get a project by its ID."""
    project = await repo.find_by_id(project_id)
    if project is None:
        raise EntityNotFound("Project", str(project_id))
    return ProjectResponse(
        id=project.id,
        name=project.name,
        description=project.description,
        owner_id=project.owner_id,
        created_at=project.created_at,
        updated_at=project.updated_at,
    )


@router.put("/{project_id}")
async def update_project(
    project_id: UUID,
    body: UpdateProjectRequest,
    repo: ProjectRepoDep,
) -> ProjectResponse:
    """Update an existing project."""
    existing = await repo.find_by_id(project_id)
    if existing is None:
        raise EntityNotFound("Project", str(project_id))

    kwargs: dict = {"updated_at": datetime.now(UTC)}
    if body.name is not None:
        kwargs["name"] = body.name
    if body.description is not None:
        kwargs["description"] = body.description

    updated = replace(existing, **kwargs)
    result = await repo.save(updated)
    return ProjectResponse(
        id=result.id,
        name=result.name,
        description=result.description,
        owner_id=result.owner_id,
        created_at=result.created_at,
        updated_at=result.updated_at,
    )


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project(
    project_id: UUID,
    repo: ProjectRepoDep,
) -> None:
    """Delete a project by its ID."""
    await repo.delete(project_id)
