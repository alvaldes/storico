"""UserStory Pydantic schemas for Storico API."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from storico.domain.entities.user_story import UserStoryStatus


class CreateUserStoryRequest(BaseModel):
    """Request body for creating a new user story."""

    model_config = ConfigDict(extra="forbid")

    project_id: UUID
    actor: str = Field(..., min_length=1, max_length=100)
    feature: str = Field(..., min_length=1, max_length=300)
    benefit: str = Field(..., min_length=1, max_length=300)
    raw_text: str = Field(..., max_length=2000)


class UpdateUserStoryRequest(BaseModel):
    """Request body for updating an existing user story."""

    model_config = ConfigDict(extra="forbid")

    actor: str | None = Field(None, min_length=1, max_length=100)
    feature: str | None = Field(None, min_length=1, max_length=300)
    benefit: str | None = Field(None, min_length=1, max_length=300)
    raw_text: str | None = Field(None, max_length=2000)


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
    status: UserStoryStatus = UserStoryStatus.PENDING
