from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID

from uuid_utils.compat import uuid7

from storico.domain.entities.user_story import UserStoryStatus


class ExtractionStatus(StrEnum):
    """Internal extraction job status (for polling compatibility)."""

    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class Extraction:
    user_story_id: UUID
    model_used: str
    raw_response: str
    # Required from 0028 on: a row cannot be born with a provider nobody configured, and
    # NOT NULL cannot tell an empty string apart from a real value — an empty string is a
    # lie the database would accept. Required puts the failure at the type, at the
    # earliest possible moment.
    provider: str
    temperature: float
    status: ExtractionStatus = field(default=ExtractionStatus.PENDING)
    user_story_status: UserStoryStatus = field(default=UserStoryStatus.PENDING_EXTRACTION)
    error_info: str | None = field(default=None)
    prompt_config: dict | None = None
    confidence_score: float | None = None
    id: UUID = field(default_factory=uuid7)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    # Non-null exactly when the status is terminal. Stamped by the terminal-path call sites rather
    # than derived here, and the reason is the read path: the repository rebuilds an entity from
    # every row it loads, so deriving it would hand a freshly generated timestamp to a historical
    # extraction that finished before this column existed. The response would then report a
    # completion time that changed on each read, and the deliberate decision not to backfill would
    # be silently undone.
    completed_at: datetime | None = None
    # Optional because ``None`` means "not yet minted" and "never rendered" — both honest
    # answers: the number is minted inside the row's own INSERT (only
    # ``create_next_version`` may set it), and the rendered prompt is written between
    # render and generate, before any provider is contacted.
    version_number: int | None = None
    prompt_rendered: str | None = None
