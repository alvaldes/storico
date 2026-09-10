"""Extraction read-only API routes."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from storico.api.dependencies import get_current_user, get_repository
from storico.api.schemas.common import PaginatedResponse, PaginationParams
from storico.api.schemas.extraction import ExtractionResponse
from storico.domain.entities import EntityNotFound, User
from storico.infrastructure.database.repositories import (
    SQLAlchemyExtractionRepository,
    SQLAlchemyProjectRepository,
    SQLAlchemyUserStoryRepository,
)
from storico.infrastructure.database.repositories.workspace_member_repository import (
    SQLAlchemyWorkspaceMemberRepository,
)

router = APIRouter(prefix="/api/v1/extractions", tags=["extractions"])

ExtractionRepoDep = Annotated[
    SQLAlchemyExtractionRepository,
    Depends(get_repository(SQLAlchemyExtractionRepository)),
]

StoryRepoDep = Annotated[
    SQLAlchemyUserStoryRepository,
    Depends(get_repository(SQLAlchemyUserStoryRepository)),
]

ProjectRepoDep = Annotated[
    SQLAlchemyProjectRepository,
    Depends(get_repository(SQLAlchemyProjectRepository)),
]

MemberRepoDep = Annotated[
    SQLAlchemyWorkspaceMemberRepository,
    Depends(get_repository(SQLAlchemyWorkspaceMemberRepository)),
]


async def _validate_extraction_workspace_access(
    extraction_id: UUID,
    current_user: User,
    extraction_repo: SQLAlchemyExtractionRepository,
    story_repo: SQLAlchemyUserStoryRepository,
    project_repo: SQLAlchemyProjectRepository,
    member_repo: SQLAlchemyWorkspaceMemberRepository,
):
    """Find an extraction and verify the user has access to its workspace.

    Returns the extraction if access is granted. Raises 404 or 403 otherwise.
    """
    extraction = await extraction_repo.find_by_id(extraction_id)
    if extraction is None:
        raise EntityNotFound("Extraction", str(extraction_id))

    story = await story_repo.find_by_id(extraction.user_story_id)
    if story is None:
        raise EntityNotFound("Extraction", str(extraction_id))

    project = await project_repo.find_by_id(story.project_id)
    if project is None:
        raise EntityNotFound("Extraction", str(extraction_id))

    member = await member_repo.find_by_workspace_and_user(
        project.workspace_id, current_user.id
    )
    if member is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not a member of this workspace",
        )
    return extraction


@router.get("/")
async def list_extractions(
    params: Annotated[PaginationParams, Depends()],
    current_user: User = Depends(get_current_user),
    repo: ExtractionRepoDep = None,  # type: ignore[assignment]
    story_repo: StoryRepoDep = None,  # type: ignore[assignment]
    project_repo: ProjectRepoDep = None,  # type: ignore[assignment]
    member_repo: MemberRepoDep = None,  # type: ignore[assignment]
    user_story_id: UUID | None = None,
    workspace_id: UUID | None = None,
) -> PaginatedResponse[ExtractionResponse]:
    """List extractions with optional filters and pagination.

    Filters:
    - ``user_story_id``: filter by user story (requires workspace membership).
    - ``workspace_id``: filter by workspace (requires workspace membership).

    If neither filter is provided, returns extractions from all workspaces
    the current user is a member of.
    """
    # Validate workspace access
    if workspace_id is not None:
        # Validate user is a member of the specified workspace
        member = await member_repo.find_by_workspace_and_user(workspace_id, current_user.id)
        if member is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not a member of this workspace",
            )
        all_extractions = await repo.list_by_workspace(workspace_id)
    elif user_story_id is not None:
        # Validate user has access to the user story's workspace
        story = await story_repo.find_by_id(user_story_id)
        if story is None:
            raise EntityNotFound("UserStory", str(user_story_id))
        project = await project_repo.find_by_id(story.project_id)
        if project is None:
            raise EntityNotFound("UserStory", str(user_story_id))
        member = await member_repo.find_by_workspace_and_user(project.workspace_id, current_user.id)
        if member is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not a member of this workspace",
            )
        all_extractions = await repo.list_by_story(user_story_id)
    else:
        # No filter provided: return extractions from all workspaces the user is a member of
        memberships = await member_repo.list_by_user(current_user.id)
        workspace_ids = [m.workspace_id for m in memberships]
        if not workspace_ids:
            all_extractions = []
        else:
            # Collect extractions from all user's workspaces
            all_extractions = []
            for ws_id in workspace_ids:
                ws_extractions = await repo.list_by_workspace(ws_id)
                all_extractions.extend(ws_extractions)
            # Sort by created_at descending for consistent ordering
            all_extractions.sort(key=lambda e: e.created_at, reverse=True)

    total = len(all_extractions)
    start = (params.page - 1) * params.size
    items = [
        ExtractionResponse(
            id=e.id,
            user_story_id=e.user_story_id,
            model_used=e.model_used,
            status=e.status,
            user_story_status=e.user_story_status,
            error_info=e.error_info,
            prompt_config=e.prompt_config,
            raw_response=e.raw_response,
            confidence_score=e.confidence_score,
            created_at=e.created_at,
            completed_at=None,
        )
        for e in all_extractions[start : start + params.size]
    ]
    return PaginatedResponse(
        items=items,
        total=total,
        page=params.page,
        size=params.size,
    )


@router.get("/{extraction_id}")
async def get_extraction(
    extraction_id: UUID,
    current_user: User = Depends(get_current_user),
    repo: ExtractionRepoDep = None,  # type: ignore[assignment]
    story_repo: StoryRepoDep = None,  # type: ignore[assignment]
    project_repo: ProjectRepoDep = None,  # type: ignore[assignment]
    member_repo: MemberRepoDep = None,  # type: ignore[assignment]
) -> ExtractionResponse:
    """Get an extraction by its ID.

    The user must be a member of the workspace that owns the extraction's user story project.
    """
    extraction = await _validate_extraction_workspace_access(
        extraction_id, current_user, repo, story_repo, project_repo, member_repo
    )
    return ExtractionResponse(
        id=extraction.id,
        user_story_id=extraction.user_story_id,
        model_used=extraction.model_used,
        status=extraction.status,
        user_story_status=extraction.user_story_status,
        error_info=extraction.error_info,
        prompt_config=extraction.prompt_config,
        raw_response=extraction.raw_response,
        confidence_score=extraction.confidence_score,
        created_at=extraction.created_at,
        completed_at=None,
    )