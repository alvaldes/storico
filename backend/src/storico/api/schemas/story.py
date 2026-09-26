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
    status: UserStoryStatus = UserStoryStatus.PENDING_EXTRACTION


class StoryImportErrorItem(BaseModel):
    """One blocking problem on one row of an imported CSV."""

    line: int
    reason: str
    field: str | None = None
    length: int | None = None
    # Serialises as "max" in JSON; that is the published contract.
    max: int | None = None
    # Populated only for ``field_count_mismatch``: the row's field count vs
    # the header's column count.
    observed: int | None = None
    expected: int | None = None


class StoryImportDuplicateItem(BaseModel):
    """One row of an imported CSV skipped because it duplicates a story."""

    line: int
    reason: str
    existing_story_id: str | None = None
    first_line: int | None = None


class StoryImportResponse(BaseModel):
    """Response body for a CSV story import."""

    created: int
    skipped: int
    total_rows: int
    duplicates: list[StoryImportDuplicateItem] = []
    story_ids: list[UUID] = []
