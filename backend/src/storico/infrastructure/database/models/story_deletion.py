"""StoryDeletionModel — ORM model for the story_deletions table.

An audit record that must survive the deletion it records: a record referencing the story it
records would be destroyed by the very delete it records. So the table carries the story's
identity as values — ``story_id``, ``project_id``, ``workspace_id`` and the
``(actor, feature, benefit)`` trio — with deliberately **no foreign key** to ``stories``,
``projects`` or ``extractions``. ``test_unit/test_story_deletions_migration.py`` pins that
absence, because a future "clean up" that adds the FK would silently turn every record into
nothing.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import JSON, DateTime, ForeignKey, Index, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column
from uuid_utils.compat import uuid7

from storico.infrastructure.database.models.base import Base


class StoryDeletionModel(Base):
    """One row per sanctioned story deletion; the only reader is an operator."""

    __tablename__ = "story_deletions"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid7)
    story_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    project_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    workspace_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    # The story's identity as the app treats it: the (actor, feature, benefit) trio (the
    # dedupe rule in story_import / find_by_parts), so the record stays readable by a human
    # who can no longer look the story up.
    actor: Mapped[str] = mapped_column(Text, nullable=False)
    feature: Mapped[str] = mapped_column(Text, nullable=False)
    benefit: Mapped[str] = mapped_column(Text, nullable=False)
    # sa.JSON, not a Postgres ARRAY: ARRAY would look more correct for a list of integers,
    # but the unit suite builds its schema with Base.metadata.create_all on SQLite, where
    # ARRAY does not exist — the table could not be constructed at all. Slice (a) made the
    # same portability choice for the same reason.
    version_numbers: Mapped[list[int]] = mapped_column(JSON, nullable=False)
    # The only FK in the table, following the repo's ``projects.created_by`` convention
    # (0014_add_cascade_deletes): an account deletion nulls the actor reference instead of
    # erasing the audit trail. ON DELETE SET NULL is not enforced by SQLite, so its
    # behaviour is proven by the integration suite (task 4.16), not the unit schema.
    deleted_by: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    deleted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        # Owner-resolved decision (tasks.md 4.10): the only plausible query against an audit
        # record is "what was deleted in this workspace, newest first"; story_id is not a
        # lookup the UI can perform because the story is gone.
        Index("ix_story_deletions_workspace_deleted_at", "workspace_id", "deleted_at"),
    )
