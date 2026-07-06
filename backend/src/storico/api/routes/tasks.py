"""Task CRUD API routes."""

from dataclasses import replace
from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status

from storico.api.dependencies import get_repository
from storico.api.schemas.common import PaginatedResponse, PaginationParams
from storico.api.schemas.task import (
    CreateTaskRequest,
    TaskResponse,
    UpdateTaskRequest,
)
from storico.domain.entities import EntityNotFound, Task
from storico.infrastructure.database.repositories import SQLAlchemyTaskRepository

router = APIRouter(prefix="/api/v1/tasks", tags=["tasks"])

TaskRepoDep = Annotated[
    SQLAlchemyTaskRepository,
    Depends(get_repository(SQLAlchemyTaskRepository)),
]


@router.post("/", status_code=status.HTTP_201_CREATED)
async def create_task(
    body: CreateTaskRequest,
    repo: TaskRepoDep,
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
    repo: TaskRepoDep,
    user_story_id: UUID | None = None,
) -> PaginatedResponse[TaskResponse]:
    """List tasks with optional user_story_id filter and pagination."""
    if user_story_id is not None:
        all_tasks = await repo.list_by_story(user_story_id)
    else:
        all_tasks = await repo.list()

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
    repo: TaskRepoDep,
) -> TaskResponse:
    """Get a task by its ID."""
    task = await repo.find_by_id(task_id)
    if task is None:
        raise EntityNotFound("Task", str(task_id))
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
    repo: TaskRepoDep,
) -> TaskResponse:
    """Update an existing task.

    For ``labels`` and ``dependencies``:
    - ``None`` means keep existing values.
    - ``[]`` means clear the list.
    """
    existing = await repo.find_by_id(task_id)
    if existing is None:
        raise EntityNotFound("Task", str(task_id))

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
    repo: TaskRepoDep,
) -> None:
    """Delete a task by its ID."""
    await repo.delete(task_id)
