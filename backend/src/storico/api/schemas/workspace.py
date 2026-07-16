"""Workspace Pydantic schemas for Storico API."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


WORKSPACE_NAME_MAX = 100


class CreateWorkspaceRequest(BaseModel):
    """Request body for creating a new workspace."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., min_length=1, max_length=WORKSPACE_NAME_MAX)
    slug: str | None = Field(None, max_length=100)
    icon: str | None = Field(None, max_length=100)


class UpdateWorkspaceRequest(BaseModel):
    """Request body for updating an existing workspace."""

    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(None, min_length=1, max_length=WORKSPACE_NAME_MAX)
    slug: str | None = Field(None, max_length=100)
    icon: str | None = Field(None, max_length=100)


class WorkspaceResponse(BaseModel):
    """Response body representing a workspace with membership info."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    slug: str
    icon: str | None = None
    owner_id: UUID
    role: str
    member_count: int = 0
    created_at: datetime
    updated_at: datetime


class WorkspaceListResponse(BaseModel):
    """Response body for listing workspaces."""

    workspaces: list[WorkspaceResponse]
