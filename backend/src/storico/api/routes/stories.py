"""UserStory CRUD API routes."""

from dataclasses import replace
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from storico.api.dependencies import get_current_user, get_repository
from storico.api.schemas.common import PaginatedResponse, PaginationParams
from storico.api.schemas.story import (
    CreateUserStoryRequest,
    UpdateUserStoryRequest,
    UserStoryResponse,
)
from storico.domain.entities import EntityNotFound, User, UserStory
from storico.infrastructure.database.repositories import (
    SQLAlchemyProjectRepository,
    SQLAlchemyUserStoryRepository,
)
from storico.infrastructure.database.repositories.workspace_member_repository import (
    SQLAlchemyWorkspaceMemberRepository,
)

router = APIRouter(prefix="/api/v1/stories", tags=["stories"])

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


async def _validate_story_workspace_access(
    story_id: UUID,
    current_user: User,
    story_repo: SQLAlchemyUserStoryRepository,
    project_repo: SQLAlchemyProjectRepository,
    member_repo: SQLAlchemyWorkspaceMemberRepository,
) -> UserStory:
    """Find a story and verify the user has access to its workspace.

    Returns the story if access is granted. Raises 404 or 403 otherwise.
    """
    story = await story_repo.find_by_id(story_id)
    if story is None:
        raise EntityNotFound("UserStory", str(story_id))

    project = await project_repo.find_by_id(story.project_id)
    if project is None:
        raise EntityNotFound("UserStory", str(story_id))

    member = await member_repo.find_by_workspace_and_user(
        project.workspace_id, current_user.id
    )
    if member is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not a member of this workspace",
        )
    return story


@router.post("/", status_code=status.HTTP_201_CREATED)
async def create_story(
    body: CreateUserStoryRequest,
    current_user: User = Depends(get_current_user),
    repo: StoryRepoDep = None,  # type: ignore[assignment]
    project_repo: ProjectRepoDep = None,  # type: ignore[assignment]
    member_repo: MemberRepoDep = None,  # type: ignore[assignment]
) -> UserStoryResponse:
    """Create a new user story.

    The story's project must belong to a workspace the user is a member of.
    """
    # Validate the user has access to the project's workspace
    project = await project_repo.find_by_id(body.project_id)
    if project is None:
        raise EntityNotFound("Project", str(body.project_id))

    member = await member_repo.find_by_workspace_and_user(
        project.workspace_id, current_user.id
    )
    if member is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not a member of this project's workspace",
        )

    story = UserStory(
        project_id=body.project_id,
        actor=body.actor,
        feature=body.feature,
        benefit=body.benefit,
        raw_text=body.raw_text,
    )
    result = await repo.save(story)
    return UserStoryResponse(
        id=result.id,
        project_id=result.project_id,
        actor=result.actor,
        feature=result.feature,
        benefit=result.benefit,
        raw_text=result.raw_text,
        created_at=result.created_at,
        status=result.status,
    )


@router.get("/")
async def list_stories(
    params: Annotated[PaginationParams, Depends()],
    current_user: User = Depends(get_current_user),
    repo: StoryRepoDep = None,  # type: ignore[assignment]
    project_id: UUID | None = None,
    workspace_id: UUID | None = None,
) -> PaginatedResponse[UserStoryResponse]:
    """List user stories with optional filters and pagination.

    Filters:
    - ``project_id``: filter by project.
    - ``workspace_id``: filter by workspace (requires auth).
    """
    if workspace_id is not None:
        all_stories = await repo.list_by_workspace(workspace_id)
    elif project_id is not None:
        all_stories = await repo.list_by_project(project_id)
    else:
        all_stories = await repo.list()

    total = len(all_stories)
    start = (params.page - 1) * params.size
    items = [
        UserStoryResponse(
            id=s.id,
            project_id=s.project_id,
            actor=s.actor,
            feature=s.feature,
            benefit=s.benefit,
            raw_text=s.raw_text,
            created_at=s.created_at,
            status=s.status,
        )
        for s in all_stories[start : start + params.size]
    ]
    return PaginatedResponse(
        items=items,
        total=total,
        page=params.page,
        size=params.size,
    )


@router.get("/{story_id}")
async def get_story(
    story_id: UUID,
    current_user: User = Depends(get_current_user),
    repo: StoryRepoDep = None,  # type: ignore[assignment]
    project_repo: ProjectRepoDep = None,  # type: ignore[assignment]
    member_repo: MemberRepoDep = None,  # type: ignore[assignment]
) -> UserStoryResponse:
    """Get a user story by its ID.

    The user must be a member of the workspace that owns the story's project.
    """
    story = await _validate_story_workspace_access(
        story_id, current_user, repo, project_repo, member_repo
    )
    return UserStoryResponse(
        id=story.id,
        project_id=story.project_id,
        actor=story.actor,
        feature=story.feature,
        benefit=story.benefit,
        raw_text=story.raw_text,
        created_at=story.created_at,
        status=story.status,
    )


@router.put("/{story_id}")
async def update_story(
    story_id: UUID,
    body: UpdateUserStoryRequest,
    current_user: User = Depends(get_current_user),
    repo: StoryRepoDep = None,  # type: ignore[assignment]
    project_repo: ProjectRepoDep = None,  # type: ignore[assignment]
    member_repo: MemberRepoDep = None,  # type: ignore[assignment]
) -> UserStoryResponse:
    """Update an existing user story.

    The user must be a member of the workspace that owns the story's project.
    """
    existing = await _validate_story_workspace_access(
        story_id, current_user, repo, project_repo, member_repo
    )

    kwargs: dict = {}
    if body.actor is not None:
        kwargs["actor"] = body.actor
    if body.feature is not None:
        kwargs["feature"] = body.feature
    if body.benefit is not None:
        kwargs["benefit"] = body.benefit
    if body.raw_text is not None:
        kwargs["raw_text"] = body.raw_text

    updated = replace(existing, **kwargs)
    result = await repo.save(updated)
    return UserStoryResponse(
        id=result.id,
        project_id=result.project_id,
        actor=result.actor,
        feature=result.feature,
        benefit=result.benefit,
        raw_text=result.raw_text,
        created_at=result.created_at,
        status=result.status,
    )


@router.delete("/{story_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_story(
    story_id: UUID,
    current_user: User = Depends(get_current_user),
    repo: StoryRepoDep = None,  # type: ignore[assignment]
    project_repo: ProjectRepoDep = None,  # type: ignore[assignment]
    member_repo: MemberRepoDep = None,  # type: ignore[assignment]
) -> None:
    """Delete a user story by its ID.

    The user must be a member of the workspace that owns the story's project.
    """
    await _validate_story_workspace_access(
        story_id, current_user, repo, project_repo, member_repo
    )
    await repo.delete(story_id)
