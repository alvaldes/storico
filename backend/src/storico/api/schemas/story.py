"""UserStory Pydantic schemas for Storico API."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from storico.domain.entities.extraction import ExtractionStatus
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


class StoryVersionSummaryResponse(BaseModel):
    """One story's version summary, as the story-card badge reads it.

    Projected by the story read paths (``list_stories``, ``get_story``,
    ``update_story``) from one batched statement over the page's story ids —
    never one request per card. ``current_number`` is the highest completed
    run's number (``None`` when there is no completed run); ``latest_number``
    and ``latest_status`` describe the newest run of any status, so a story
    whose only run failed renders ``v1 · failed`` instead of lying with
    "current". ``null`` on the response means the story has no runs at all —
    which is exactly what ``create_story`` answers for a story just created.
    """

    count: int
    current_number: int | None
    latest_number: int
    latest_status: ExtractionStatus


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
    version_summary: StoryVersionSummaryResponse | None = None


class StoryVersionResponse(BaseModel):
    """One version of a user story, as the version selector reads it.

    A bare entry of the unpaginated ``GET /stories/{story_id}/versions`` array:
    every run of the story — ``pending`` and ``failed`` ones included — ordered
    ``version_number DESC`` by the route. The two booleans are derived there,
    never stored: ``is_current`` marks the first ``completed`` entry of the
    ordered list (a story with no completed run has no current entry), and
    ``has_output`` is ``status == completed``.
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    version_number: int | None
    status: ExtractionStatus
    model_used: str
    provider: str
    temperature: float
    created_at: datetime
    completed_at: datetime | None
    error_info: str | None = None
    is_current: bool
    has_output: bool


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
