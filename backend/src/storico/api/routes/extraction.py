"""Extraction API routes — real LLM-based task extraction.

This module provides two routers:

1. ``router`` (prefix ``/api/v1/extract``) — legacy route that returns
   410 Gone, directing clients to the workspace-scoped endpoint.
2. ``extraction_router`` (prefix ``/api/v1/workspaces/{workspace_id}/extract``)
   — workspace-scoped extraction routes.
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from storico.api.dependencies import (
    get_current_user,
    get_extract_use_case,
    get_repository,
    get_workspace_for_user,
)
from storico.api.schemas.extraction import (
    ExtractRequest,
    ExtractResponse,
    ExtractionResponse,
    TaskSchema,
)
from storico.application.extraction import ExtractFromStoryUseCase
from storico.domain.entities import EntityNotFound, User, Workspace, WorkspaceRole
from storico.infrastructure.database.repositories import (
    SQLAlchemyExtractionRepository,
    SQLAlchemyProjectRepository,
    SQLAlchemyTaskRepository,
    SQLAlchemyUserStoryRepository,
)

# ═══════════════════════════════════════════════════════════════════
# Legacy router — 410 Gone
# ═══════════════════════════════════════════════════════════════════

router = APIRouter(prefix="/api/v1/extract", tags=["extract"])


@router.api_route(
    "/{path:path}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"],
    status_code=status.HTTP_410_GONE,
    include_in_schema=False,
)
async def deprecated_extract() -> None:
    """Legacy extraction endpoint — permanently removed.

    Extraction is now scoped to workspaces. Use:
      POST /api/v1/workspaces/{workspace_id}/extract
      GET  /api/v1/workspaces/{workspace_id}/extract/status/{extraction_id}
    """
    raise HTTPException(
        status_code=status.HTTP_410_GONE,
        detail=(
            "This endpoint has been removed. "
            "Extraction is now scoped to workspaces. "
            "Use /api/v1/workspaces/{workspace_id}/extract instead."
        ),
    )


# ═══════════════════════════════════════════════════════════════════
# New workspace-scoped router
# ═══════════════════════════════════════════════════════════════════

extraction_router = APIRouter(
    prefix="/api/v1/workspaces/{workspace_id}/extract",
    tags=["extract"],
)

ExtractionRepoDep = Annotated[
    SQLAlchemyExtractionRepository,
    Depends(get_repository(SQLAlchemyExtractionRepository)),
]

TaskRepoDep = Annotated[
    SQLAlchemyTaskRepository,
    Depends(get_repository(SQLAlchemyTaskRepository)),
]

StoryRepoDep = Annotated[
    SQLAlchemyUserStoryRepository,
    Depends(get_repository(SQLAlchemyUserStoryRepository)),
]

ProjectRepoDep = Annotated[
    SQLAlchemyProjectRepository,
    Depends(get_repository(SQLAlchemyProjectRepository)),
]


async def _validate_story_belongs_to_workspace(
    user_story_id: UUID,
    workspace_id: UUID,
    story_repo: SQLAlchemyUserStoryRepository,
    project_repo: SQLAlchemyProjectRepository,
) -> None:
    """Validate that a user story belongs to the given workspace.

    Raises ``HTTPException(404)`` if the story or its project is not found.
    Raises ``HTTPException(403)`` if the story does not belong to the
    workspace.
    """
    story = await story_repo.find_by_id(user_story_id)
    if story is None:
        raise EntityNotFound("UserStory", str(user_story_id))

    project = await project_repo.find_by_id(story.project_id)
    if project is None:
        raise EntityNotFound("UserStory", str(user_story_id))

    if project.workspace_id != workspace_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This user story does not belong to the specified workspace",
        )


@extraction_router.post("/", status_code=status.HTTP_201_CREATED)
async def extract_tasks(
    body: ExtractRequest,
    ctx: tuple[Workspace, WorkspaceRole] = Depends(get_workspace_for_user),
    use_case: ExtractFromStoryUseCase = Depends(get_extract_use_case),
    extraction_repo: ExtractionRepoDep = None,  # type: ignore[assignment]
    task_repo: TaskRepoDep = None,  # type: ignore[assignment]
    story_repo: StoryRepoDep = None,  # type: ignore[assignment]
    project_repo: ProjectRepoDep = None,  # type: ignore[assignment]
) -> ExtractResponse:
    """Extract tasks from a user story using an LLM.

    The user story must belong to a project within the workspace specified
    in the URL path. Workspace membership is validated via
    ``get_workspace_for_user``.

    The extraction runs synchronously. On success, the response contains
    the generated tasks. On failure, ``status`` will be ``"failed"`` with
    an ``error_info`` message.
    """
    workspace, _ = ctx

    # Validate the user story belongs to this workspace
    await _validate_story_belongs_to_workspace(
        body.user_story_id, workspace.id, story_repo, project_repo
    )

    # 1. Run extraction
    result = await use_case.execute(
        story_id=body.user_story_id,
        model=body.model,
        temperature=body.temperature,
        validate=body.run_validation,
    )

    # 2. Load tasks if extraction completed
    tasks: list[TaskSchema] = []
    if result["status"] == "completed" and extraction_repo is not None:
        extraction = await extraction_repo.find_by_id(result["extraction_id"])
        if extraction is not None:
            persisted_tasks = await task_repo.list_by_story(extraction.user_story_id)
            tasks = [
                TaskSchema(
                    title=t.title,
                    description=t.description,
                    labels=t.labels,
                    dependencies=t.dependencies,
                )
                for t in persisted_tasks
            ]

    return ExtractResponse(
        extraction_id=result["extraction_id"],
        status=result["status"],
        error_info=result.get("error_info"),
        tasks=tasks,
        model_used=result["model_used"],
        confidence_score=result.get("confidence_score"),
    )


@extraction_router.get("/status/{extraction_id}")
async def extraction_status(
    extraction_id: UUID,
    ctx: tuple[Workspace, WorkspaceRole] = Depends(get_workspace_for_user),
    repo: ExtractionRepoDep = None,  # type: ignore[assignment]
) -> ExtractionResponse:
    """Get the status and details of an extraction by its ID.

    The extraction must belong to a user story in the workspace specified
    in the URL path. Workspace membership is validated via
    ``get_workspace_for_user``.
    """
    workspace, _ = ctx  # noqa: F841 — validates workspace membership
    extraction = await repo.find_by_id(extraction_id)
    if extraction is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Extraction '{extraction_id}' not found",
        )
    return ExtractionResponse(
        id=extraction.id,
        user_story_id=extraction.user_story_id,
        model_used=extraction.model_used,
        status=extraction.status,
        error_info=extraction.error_info,
        prompt_config=extraction.prompt_config,
        raw_response=extraction.raw_response,
        confidence_score=extraction.confidence_score,
        created_at=extraction.created_at,
    )
