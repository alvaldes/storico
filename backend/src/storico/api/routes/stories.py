"""UserStory CRUD API routes."""

from dataclasses import replace
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status

from storico.api.dependencies import get_repository
from storico.api.schemas.common import PaginatedResponse, PaginationParams
from storico.api.schemas.story import (
    CreateUserStoryRequest,
    UpdateUserStoryRequest,
    UserStoryResponse,
)
from storico.domain.entities import EntityNotFound, UserStory
from storico.infrastructure.database.repositories import SQLAlchemyUserStoryRepository

router = APIRouter(prefix="/api/v1/stories", tags=["stories"])

StoryRepoDep = Annotated[
    SQLAlchemyUserStoryRepository,
    Depends(get_repository(SQLAlchemyUserStoryRepository)),
]


@router.post("/", status_code=status.HTTP_201_CREATED)
async def create_story(
    body: CreateUserStoryRequest,
    repo: StoryRepoDep,
) -> UserStoryResponse:
    """Create a new user story."""
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
    )


@router.get("/")
async def list_stories(
    params: Annotated[PaginationParams, Depends()],
    repo: StoryRepoDep,
    project_id: UUID | None = None,
) -> PaginatedResponse[UserStoryResponse]:
    """List user stories with optional project_id filter and pagination."""
    if project_id is not None:
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
    repo: StoryRepoDep,
) -> UserStoryResponse:
    """Get a user story by its ID."""
    story = await repo.find_by_id(story_id)
    if story is None:
        raise EntityNotFound("UserStory", str(story_id))
    return UserStoryResponse(
        id=story.id,
        project_id=story.project_id,
        actor=story.actor,
        feature=story.feature,
        benefit=story.benefit,
        raw_text=story.raw_text,
        created_at=story.created_at,
    )


@router.put("/{story_id}")
async def update_story(
    story_id: UUID,
    body: UpdateUserStoryRequest,
    repo: StoryRepoDep,
) -> UserStoryResponse:
    """Update an existing user story."""
    existing = await repo.find_by_id(story_id)
    if existing is None:
        raise EntityNotFound("UserStory", str(story_id))

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
    )


@router.delete("/{story_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_story(
    story_id: UUID,
    repo: StoryRepoDep,
) -> None:
    """Delete a user story by its ID."""
    await repo.delete(story_id)
