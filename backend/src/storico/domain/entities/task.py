from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID

from uuid_utils.compat import uuid7


class TaskStatus(StrEnum):
    """Kanban column status for a task."""

    BACKLOG = "backlog"
    TODO = "todo"
    IN_PROGRESS = "in_progress"
    REVIEW = "review"
    DONE = "done"


@dataclass(frozen=True, slots=True)
class Task:
    user_story_id: UUID
    title: str
    description: str = ""
    status: TaskStatus = field(default=TaskStatus.BACKLOG)
    priority: str = "medium"
    labels: list[str] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)
    id: UUID = field(default_factory=uuid7)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
