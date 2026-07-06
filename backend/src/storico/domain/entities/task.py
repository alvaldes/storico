from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID, uuid4


@dataclass(frozen=True, slots=True)
class Task:
    user_story_id: UUID
    title: str
    description: str = ""
    status: str = "backlog"
    priority: str = "medium"
    labels: list[str] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)
    id: UUID = field(default_factory=uuid4)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
