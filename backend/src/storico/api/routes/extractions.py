"""Extraction read-only API routes."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from storico.api.dependencies import (
    get_current_user,
    get_repository,
    require_story_workspace_access,
)
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

    # Delegate the rest of the walk so a missing story, project or membership is
    # still reported as a miss of this route's own head entity ("Extraction").
    await require_story_workspace_access(
        extraction.user_story_id,
        current_user,
        story_repo=story_repo,
        project_repo=project_repo,
        member_repo=member_repo,
        reported_as=("Extraction", extraction_id),
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

    The page and its total come from one statement in the database —
    ``count(*) OVER ()`` rides on the rows' own query, so no separate
    ``SELECT COUNT(*)`` is issued. The order is ``created_at DESC, id DESC``,
    which makes the paging deterministic.
    """
    offset = (params.page - 1) * params.size
    # Validate workspace access
    if workspace_id is not None:
        # Validate user is a member of the specified workspace
        member = await member_repo.find_by_workspace_and_user(workspace_id, current_user.id)
        if member is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not a member of this workspace",
            )
        page, total = await repo.list_page(
            workspace_id=workspace_id, limit=params.size, offset=offset
        )
    elif user_story_id is not None:
        # Validate user has access to the user story's workspace
        await require_story_workspace_access(
            user_story_id,
            current_user,
            story_repo=story_repo,
            project_repo=project_repo,
            member_repo=member_repo,
        )
        page, total = await repo.list_page(
            user_story_id=user_story_id, limit=params.size, offset=offset
        )
    else:
        # No filter provided: return extractions from all workspaces the user is a member of
        memberships = await member_repo.list_by_user(current_user.id)
        workspace_ids = [m.workspace_id for m in memberships]
        # One statement for all the workspaces, not one per workspace: this branch used to await
        # `list_by_workspace` in a loop, which cost a statement each (~2s against the dev pooler,
        # where even a bare SELECT 1 measures 800ms). The order is the statement's
        # `created_at DESC, id DESC`, shared by every branch of this route.
        page, total = await repo.list_page(
            workspace_ids=workspace_ids, limit=params.size, offset=offset
        )

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
            completed_at=e.completed_at,
        )
        for e in page
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
        completed_at=extraction.completed_at,
    )
