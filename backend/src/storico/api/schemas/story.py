"""UserStory Pydantic schemas for Storico API."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class CreateUserStoryRequest(BaseModel):
    """Request body for creating a new user story."""

    model_config = ConfigDict(extra="forbid")

    project_id: UUID
    actor: str
    feature: str
    benefit: str
    raw_text: str


class UpdateUserStoryRequest(BaseModel):
    """Request body for updating an existing user story."""

    model_config = ConfigDict(extra="forbid")

    actor: str | None = None
    feature: str | None = None
    benefit: str | None = None
    raw_text: str | None = None


class UserStoryResponse(BaseModel):
    """Response body representing a user story."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    actor: str
    feature: str
    benefit: str
    raw_text: str
    created_at: datetime
