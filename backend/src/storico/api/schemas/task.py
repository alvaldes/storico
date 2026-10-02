"""Task Pydantic schemas for Storico API."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from storico.domain.entities.task import TaskStatus


class UpdateTaskRequest(BaseModel):
    """Request body for updating an existing task.

    The D5/D21 field matrix: only ``status``, ``labels`` and ``dependencies``
    are writable. ``title``, ``description`` and ``priority`` are deleted, not
    ignored — ``extra="forbid"`` refuses them with 422 during body validation,
    and ``dependencies`` is only accepted while the task's version is the
    story's current one (the route refuses the write with 409 otherwise).
    """

    model_config = ConfigDict(extra="forbid")

    status: TaskStatus | None = None
    labels: list[str] | None = None
    dependencies: list[str] | None = None


class TaskResponse(BaseModel):
    """Response body representing a task."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_story_id: UUID
    title: str
    description: str
    status: TaskStatus
    priority: str
    labels: list[str]
    dependencies: list[str]
    created_at: datetime
    updated_at: datetime
