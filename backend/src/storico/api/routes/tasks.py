"""Task CRUD API routes."""

from dataclasses import replace
from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from storico.api.dependencies import get_current_user, get_repository
from storico.api.schemas.common import PaginatedResponse, PaginationParams
from storico.api.schemas.task import (
    CreateTaskRequest,
    TaskResponse,
    UpdateTaskRequest,
)
from storico.domain.entities import EntityNotFound, Task, User
from storico.domain.validators.state_machine import (
    VALID_TASK_TRANSITIONS,
    validate_task_transition,
)
from storico.infrastructure.database.repositories import (
    SQLAlchemyProjectRepository,
    SQLAlchemyTaskRepository,
    SQLAlchemyUserStoryRepository,
)
from storico.infrastructure.database.repositories.workspace_member_repository import (
    SQLAlchemyWorkspaceMemberRepository,
)

router = APIRouter(prefix="/api/v1/tasks", tags=["tasks"])

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

MemberRepoDep = Annotated[
    SQLAlchemyWorkspaceMemberRepository,
    Depends(get_repository(SQLAlchemyWorkspaceMemberRepository)),
]


async def _validate_task_workspace_access(
    task_id: UUID,
    current_user: User,
    task_repo: SQLAlchemyTaskRepository,
    story_repo: SQLAlchemyUserStoryRepository,
    project_repo: SQLAlchemyProjectRepository,
    member_repo: SQLAlchemyWorkspaceMemberRepository,
) -> Task:
    """Find a task and verify the user has access to its workspace.

    Returns the task if access is granted. Raises 404 or 403 otherwise.
    """
    task = await task_repo.find_by_id(task_id)
    if task is None:
        raise EntityNotFound("Task", str(task_id))

    story = await story_repo.find_by_id(task.user_story_id)
    if story is None:
        raise EntityNotFound("Task", str(task_id))

    project = await project_repo.find_by_id(story.project_id)
    if project is None:
        raise EntityNotFound("Task", str(task_id))

    member = await member_repo.find_by_workspace_and_user(project.workspace_id, current_user.id)
    if member is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not a member of this workspace",
        )
    return task


@router.post("/", status_code=status.HTTP_201_CREATED)
async def create_task(
    body: CreateTaskRequest,
    current_user: User = Depends(get_current_user),  # noqa: ARG001
    repo: TaskRepoDep = None,  # type: ignore[assignment]
) -> TaskResponse:
    """Create a new task."""
    task = Task(
        user_story_id=body.user_story_id,
        title=body.title,
        description=body.description,
        status=body.status,
        priority=body.priority,
        labels=body.labels,
        dependencies=body.dependencies,
    )
    result = await repo.save(task)
    return TaskResponse(
        id=result.id,
        user_story_id=result.user_story_id,
        title=result.title,
        description=result.description,
        status=result.status,
        priority=result.priority,
        labels=result.labels,
        dependencies=result.dependencies,
        created_at=result.created_at,
        updated_at=result.updated_at,
    )


@router.get("/")
async def list_tasks(
    params: Annotated[PaginationParams, Depends()],
    current_user: User = Depends(get_current_user),
    repo: TaskRepoDep = None,  # type: ignore[assignment]
    story_repo: StoryRepoDep = None,  # type: ignore[assignment]
    project_repo: ProjectRepoDep = None,  # type: ignore[assignment]
    member_repo: MemberRepoDep = None,  # type: ignore[assignment]
    user_story_id: UUID | None = None,
    workspace_id: UUID | None = None,
) -> PaginatedResponse[TaskResponse]:
    """List tasks with optional filters and pagination.

    Filters:
    - ``user_story_id``: filter by user story (requires workspace membership).
    - ``workspace_id``: filter by workspace (requires workspace membership).

    If neither filter is provided, returns tasks from all workspaces
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
        all_tasks = await repo.list_by_workspace(workspace_id)
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
        all_tasks = await repo.list_by_story(user_story_id)
    else:
        # No filter provided: return tasks from all workspaces the user is a member of
        memberships = await member_repo.list_by_user(current_user.id)
        workspace_ids = [m.workspace_id for m in memberships]
        if not workspace_ids:
            all_tasks = []
        else:
            # Collect tasks from all user's workspaces
            all_tasks = []
            for ws_id in workspace_ids:
                ws_tasks = await repo.list_by_workspace(ws_id)
                all_tasks.extend(ws_tasks)
            # Sort by created_at descending for consistent ordering
            all_tasks.sort(key=lambda t: t.created_at, reverse=True)

    total = len(all_tasks)
    start = (params.page - 1) * params.size
    items = [
        TaskResponse(
            id=t.id,
            user_story_id=t.user_story_id,
            title=t.title,
            description=t.description,
            status=t.status,
            priority=t.priority,
            labels=t.labels,
            dependencies=t.dependencies,
            created_at=t.created_at,
            updated_at=t.updated_at,
        )
        for t in all_tasks[start : start + params.size]
    ]
    return PaginatedResponse(
        items=items,
        total=total,
        page=params.page,
        size=params.size,
    )


@router.get("/{task_id}")
async def get_task(
    task_id: UUID,
    current_user: User = Depends(get_current_user),
    repo: TaskRepoDep = None,  # type: ignore[assignment]
    story_repo: StoryRepoDep = None,  # type: ignore[assignment]
    project_repo: ProjectRepoDep = None,  # type: ignore[assignment]
    member_repo: MemberRepoDep = None,  # type: ignore[assignment]
) -> TaskResponse:
    """Get a task by its ID.

    The user must be a member of the workspace that owns the task's user story project.
    """
    task = await _validate_task_workspace_access(
        task_id, current_user, repo, story_repo, project_repo, member_repo
    )
    return TaskResponse(
        id=task.id,
        user_story_id=task.user_story_id,
        title=task.title,
        description=task.description,
        status=task.status,
        priority=task.priority,
        labels=task.labels,
        dependencies=task.dependencies,
        created_at=task.created_at,
        updated_at=task.updated_at,
    )


@router.put("/{task_id}")
async def update_task(
    task_id: UUID,
    body: UpdateTaskRequest,
    current_user: User = Depends(get_current_user),
    repo: TaskRepoDep = None,  # type: ignore[assignment]
    story_repo: StoryRepoDep = None,  # type: ignore[assignment]
    project_repo: ProjectRepoDep = None,  # type: ignore[assignment]
    member_repo: MemberRepoDep = None,  # type: ignore[assignment]
) -> TaskResponse:
    """Update an existing task.

    For ``labels`` and ``dependencies``:
    - ``None`` means keep existing values.
    - ``[]`` means clear the list.

    The user must be a member of the workspace that owns the task's user story project.
    """
    existing = await _validate_task_workspace_access(
        task_id, current_user, repo, story_repo, project_repo, member_repo
    )

    # Validate status transition if status is being updated
    if body.status is not None and not validate_task_transition(existing.status, body.status):
        allowed = VALID_TASK_TRANSITIONS.get(existing.status, set())
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "detail": "Invalid state transition",
                "error_code": "INVALID_STATE_TRANSITION",
                "current_state": existing.status.value,
                "attempted_state": body.status.value,
                "allowed_transitions": [s.value for s in sorted(allowed, key=lambda s: s.value)],
            },
        )

    kwargs: dict = {"updated_at": datetime.now(UTC)}
    if body.title is not None:
        kwargs["title"] = body.title
    if body.description is not None:
        kwargs["description"] = body.description
    if body.status is not None:
        kwargs["status"] = body.status
    if body.priority is not None:
        kwargs["priority"] = body.priority
    if body.labels is not None:
        kwargs["labels"] = body.labels
    if body.dependencies is not None:
        kwargs["dependencies"] = body.dependencies

    updated = replace(existing, **kwargs)
    result = await repo.save(updated)
    return TaskResponse(
        id=result.id,
        user_story_id=result.user_story_id,
        title=result.title,
        description=result.description,
        status=result.status,
        priority=result.priority,
        labels=result.labels,
        dependencies=result.dependencies,
        created_at=result.created_at,
        updated_at=result.updated_at,
    )


@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_task(
    task_id: UUID,
    current_user: User = Depends(get_current_user),
    repo: TaskRepoDep = None,  # type: ignore[assignment]
    story_repo: StoryRepoDep = None,  # type: ignore[assignment]
    project_repo: ProjectRepoDep = None,  # type: ignore[assignment]
    member_repo: MemberRepoDep = None,  # type: ignore[assignment]
) -> None:
    """Delete a task by its ID.

    The user must be a member of the workspace that owns the task's user story project.
    """
    await _validate_task_workspace_access(
        task_id, current_user, repo, story_repo, project_repo, member_repo
    )
    await repo.delete(task_id)
