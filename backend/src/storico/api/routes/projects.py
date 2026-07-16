"""Project CRUD API routes.

This module provides two routers:

1. ``deprecated_router`` (prefix ``/api/v1/projects``) — legacy routes that
   return 410 Gone, directing clients to the workspace-scoped endpoints.
2. ``projects_router`` (prefix ``/api/v1/workspaces/{workspace_id}/projects``)
   — new workspace-scoped project CRUD routes.
"""

from dataclasses import replace
from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from storico.api.dependencies import (
    get_current_user,
    get_repository,
    get_workspace_for_user,
    require_admin,
)
from storico.api.schemas.common import PaginatedResponse, PaginationParams
from storico.api.schemas.project import (
    CreateProjectRequest,
    ProjectResponse,
    UpdateProjectRequest,
)
from storico.domain.entities import EntityNotFound, Project, User, Workspace, WorkspaceRole
from storico.infrastructure.database.repositories import SQLAlchemyProjectRepository

# ═══════════════════════════════════════════════════════════════════
# Legacy router — 410 Gone
# ═══════════════════════════════════════════════════════════════════

router = APIRouter(prefix="/api/v1/projects", tags=["projects"])


@router.api_route(
    "/{path:path}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"],
    status_code=status.HTTP_410_GONE,
    include_in_schema=False,
)
async def deprecated_projects() -> None:
    """Legacy projects endpoint — permanently removed.

    Projects are now scoped to workspaces. Use:
      POST/GET/PUT/DELETE /api/v1/workspaces/{workspace_id}/projects
    """
    raise HTTPException(
        status_code=status.HTTP_410_GONE,
        detail=(
            "This endpoint has been removed. "
            "Projects are now scoped to workspaces. "
            "Use /api/v1/workspaces/{workspace_id}/projects instead."
        ),
    )


# ═══════════════════════════════════════════════════════════════════
# New workspace-scoped router
# ═══════════════════════════════════════════════════════════════════

projects_router = APIRouter(
    prefix="/api/v1/workspaces/{workspace_id}/projects",
    tags=["projects"],
)

ProjectRepoDep = Annotated[
    SQLAlchemyProjectRepository,
    Depends(get_repository(SQLAlchemyProjectRepository)),
]


async def _verify_project_belongs_to_workspace(
    project_id: UUID,
    workspace_id: UUID,
    repo: SQLAlchemyProjectRepository,
) -> Project:
    """Find a project and verify it belongs to the given workspace.

    Raises ``EntityNotFound`` (404) if the project does not exist or
    does not belong to the workspace.
    """
    project = await repo.find_by_id(project_id)
    if project is None or project.workspace_id != workspace_id:
        raise EntityNotFound("Project", str(project_id))
    return project


@projects_router.post("/", status_code=status.HTTP_201_CREATED)
async def create_project(
    body: CreateProjectRequest,
    ctx: tuple[Workspace, WorkspaceRole] = Depends(get_workspace_for_user),
    current_user: User = Depends(get_current_user),
    repo: ProjectRepoDep = None,  # type: ignore[assignment]
) -> ProjectResponse:
    """Create a new project in the workspace. Workspace member access."""
    workspace, _ = ctx
    project = Project(
        name=body.name,
        workspace_id=workspace.id,
        description=body.description,
        icon=body.icon,
        created_by=current_user.id,
    )
    result = await repo.save(project)
    return ProjectResponse(
        id=result.id,
        name=result.name,
        description=result.description,
        icon=result.icon,
        workspace_id=result.workspace_id,
        created_by=result.created_by,
        created_at=result.created_at,
        updated_at=result.updated_at,
        story_count=0,
    )


@projects_router.get("/")
async def list_projects(
    params: Annotated[PaginationParams, Depends()],
    ctx: tuple[Workspace, WorkspaceRole] = Depends(get_workspace_for_user),
    repo: ProjectRepoDep = None,  # type: ignore[assignment]
) -> PaginatedResponse[ProjectResponse]:
    """List all projects in the workspace. Workspace member access."""
    workspace, _ = ctx
    all_projects = await repo.list_by_workspace(workspace.id)
    total = len(all_projects)
    start = (params.page - 1) * params.size
    items: list[ProjectResponse] = []
    for p in all_projects[start : start + params.size]:
        story_count = await repo.count_stories(p.id)
        items.append(
            ProjectResponse(
                id=p.id,
                name=p.name,
                description=p.description,
                icon=p.icon,
                workspace_id=p.workspace_id,
                created_by=p.created_by,
                created_at=p.created_at,
                updated_at=p.updated_at,
                story_count=story_count,
            )
        )
    return PaginatedResponse(
        items=items,
        total=total,
        page=params.page,
        size=params.size,
    )


@projects_router.get("/{project_id}")
async def get_project(
    project_id: UUID,
    ctx: tuple[Workspace, WorkspaceRole] = Depends(get_workspace_for_user),
    repo: ProjectRepoDep = None,  # type: ignore[assignment]
) -> ProjectResponse:
    """Get a project by its ID. Workspace member access."""
    workspace, _ = ctx
    project = await _verify_project_belongs_to_workspace(
        project_id, workspace.id, repo
    )
    story_count = await repo.count_stories(project_id)
    return ProjectResponse(
        id=project.id,
        name=project.name,
        description=project.description,
        icon=project.icon,
        workspace_id=project.workspace_id,
        created_by=project.created_by,
        created_at=project.created_at,
        updated_at=project.updated_at,
        story_count=story_count,
    )


@projects_router.put("/{project_id}")
async def update_project(
    project_id: UUID,
    body: UpdateProjectRequest,
    ctx: tuple[Workspace, WorkspaceRole] = Depends(get_workspace_for_user),
    repo: ProjectRepoDep = None,  # type: ignore[assignment]
) -> ProjectResponse:
    """Update an existing project. Workspace member access."""
    workspace, _ = ctx
    existing = await _verify_project_belongs_to_workspace(
        project_id, workspace.id, repo
    )

    kwargs: dict = {"updated_at": datetime.now(UTC)}
    if body.name is not None:
        kwargs["name"] = body.name
    if body.description is not None:
        kwargs["description"] = body.description
    if body.icon is not None:
        kwargs["icon"] = body.icon

    updated = replace(existing, **kwargs)
    result = await repo.save(updated)
    story_count = await repo.count_stories(project_id)
    return ProjectResponse(
        id=result.id,
        name=result.name,
        description=result.description,
        icon=result.icon,
        workspace_id=result.workspace_id,
        created_by=result.created_by,
        created_at=result.created_at,
        updated_at=result.updated_at,
        story_count=story_count,
    )


@projects_router.delete(
    "/{project_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_project(
    project_id: UUID,
    ctx: tuple[Workspace, WorkspaceRole] = Depends(get_workspace_for_user),
    repo: ProjectRepoDep = None,  # type: ignore[assignment]
) -> None:
    """Delete a project by its ID. Workspace member access."""
    workspace, _ = ctx
    await _verify_project_belongs_to_workspace(project_id, workspace.id, repo)
    await repo.delete(project_id)
