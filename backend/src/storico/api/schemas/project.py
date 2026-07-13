"""Project Pydantic schemas for Storico API."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class CreateProjectRequest(BaseModel):
    """Request body for creating a new project."""

    model_config = ConfigDict(extra="forbid")

    name: str
    description: str = ""
    owner_id: UUID


class UpdateProjectRequest(BaseModel):
    """Request body for updating an existing project."""

    model_config = ConfigDict(extra="forbid")

    name: str | None = None
    description: str | None = None


class ProjectResponse(BaseModel):
    """Response body representing a project."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    description: str
    owner_id: UUID
    created_at: datetime
    updated_at: datetime
    story_count: int = 0
