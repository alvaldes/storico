"""Task Pydantic schemas for Storico API."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from storico.domain.entities.task import TaskStatus


class UpdateTaskRequest(BaseModel):
    """Request body for updating an existing task."""

    model_config = ConfigDict(extra="forbid")

    title: str | None = None
    description: str | None = None
    status: TaskStatus | None = None
    priority: str | None = None
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
