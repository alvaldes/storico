"""Task Pydantic schemas for Storico API."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class CreateTaskRequest(BaseModel):
    """Request body for creating a new task."""

    model_config = ConfigDict(extra="forbid")

    user_story_id: UUID
    title: str
    description: str = ""
    status: str = Field(default="backlog")
    priority: str = Field(default="medium")
    labels: list[str] = Field(default_factory=list)
    dependencies: list[str] = Field(default_factory=list)


class UpdateTaskRequest(BaseModel):
    """Request body for updating an existing task."""

    model_config = ConfigDict(extra="forbid")

    title: str | None = None
    description: str | None = None
    status: str | None = None
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
    status: str
    priority: str
    labels: list[str]
    dependencies: list[str]
    created_at: datetime
    updated_at: datetime
