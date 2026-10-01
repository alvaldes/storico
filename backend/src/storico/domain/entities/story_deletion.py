"""StoryDeletion — the audit record that survives the deletion it records.

The record carries the story's identity as values (the ``(actor, feature, benefit)`` trio the
app already treats as a story's identity, the workspace/project ids, and the version numbers
that were destroyed) because a record that referenced the story by foreign key would be
destroyed by the very delete it records. Domain layer: no SQLAlchemy, no infrastructure.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID

from uuid_utils.compat import uuid7


@dataclass(frozen=True, slots=True)
class StoryDeletion:
    """One row of the deletion audit trail: who deleted what, when, and which versions died."""

    story_id: UUID
    project_id: UUID
    workspace_id: UUID
    actor: str
    feature: str
    benefit: str
    # The version numbers destroyed with the story, snapshot from the live rows before the
    # delete — the only durable answer to "what did this deletion take".
    version_numbers: list[int]
    # Nullable by design (the ``projects.created_by`` convention): an account deletion nulls
    # the actor reference; the audit trail itself stays.
    deleted_by: UUID | None = None
    id: UUID = field(default_factory=uuid7)
    deleted_at: datetime = field(default_factory=lambda: datetime.now(UTC))
