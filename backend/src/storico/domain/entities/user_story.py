from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID

from uuid_utils.compat import uuid7


class UserStoryStatus(StrEnum):
    """Tracks the extraction lifecycle of a user story."""

    PENDING_EXTRACTION = "pending_extraction"
    EXTRACTING = "extracting"
    EXTRACTED = "extracted"
    FAILED_EXTRACTION = "failed_extraction"


@dataclass(frozen=True, slots=True)
class UserStory:
    project_id: UUID
    actor: str
    feature: str
    benefit: str
    raw_text: str
    id: UUID = field(default_factory=uuid7)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    status: UserStoryStatus = field(default=UserStoryStatus.PENDING_EXTRACTION)
