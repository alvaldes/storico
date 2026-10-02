"""TaskInvalidation — one invalidation mark on a task, as a domain entity.

The mark is a row, not a column pair on ``tasks``: only a row per mark event can
hold who revoked it and when (spec R9/R10). Revoking is an update on the same
row, never a delete — the revoke history is the record. Domain layer: no
SQLAlchemy, no infrastructure.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID

from uuid_utils.compat import uuid7


@dataclass(frozen=True, slots=True)
class TaskInvalidation:
    """One mark event with its optional revoke attribution on the same row."""

    task_id: UUID
    reason: str
    # Nullable by design (the ``projects.created_by`` convention): the column is
    # ON DELETE SET NULL, so an account deletion nulls the actor and the mark stays.
    marked_by: UUID | None = None
    marked_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    id: UUID = field(default_factory=uuid7)
    revoked_by: UUID | None = None
    revoked_at: datetime | None = None
