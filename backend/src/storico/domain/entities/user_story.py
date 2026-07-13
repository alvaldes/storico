from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum, auto
from uuid import UUID, uuid4


class UserStoryStatus(StrEnum):
    """Tracks the extraction lifecycle of a user story."""

    PENDING = auto()
    PROCESSING = auto()
    COMPLETED = auto()
    ERROR = auto()


@dataclass(frozen=True, slots=True)
class UserStory:
    project_id: UUID
    actor: str
    feature: str
    benefit: str
    raw_text: str
    id: UUID = field(default_factory=uuid4)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    status: UserStoryStatus = field(default=UserStoryStatus.PENDING)
