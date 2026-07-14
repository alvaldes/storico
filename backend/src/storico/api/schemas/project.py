"""Project Pydantic schemas for Storico API."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class CreateProjectRequest(BaseModel):
    """Request body for creating a new project.

    workspace_id is derived from the URL path, created_by from auth context.
    """

    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., min_length=1, max_length=120)
    description: str = Field(default="", max_length=500)


class UpdateProjectRequest(BaseModel):
    """Request body for updating an existing project."""

    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(None, min_length=1, max_length=120)
    description: str | None = Field(None, max_length=500)


class ProjectResponse(BaseModel):
    """Response body representing a project."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    description: str
    workspace_id: UUID
    created_by: UUID | None = None
    created_at: datetime
    updated_at: datetime
    story_count: int = 0
