from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID, uuid4


@dataclass(frozen=True, slots=True)
class Extraction:
    user_story_id: UUID
    model_used: str
    raw_response: str
    status: str = field(default="pending")
    error_info: str | None = field(default=None)
    prompt_config: dict | None = None
    confidence_score: float | None = None
    id: UUID = field(default_factory=uuid4)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
