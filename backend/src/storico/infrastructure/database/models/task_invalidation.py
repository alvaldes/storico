"""TaskInvalidationModel — ORM model for the task_invalidations table.

The invalidation mark is a row, not a column pair on ``tasks``: only a row per
mark event can hold who revoked it and when. Revoking is an update on the same
row, never a delete — the revoke history is the record.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, Uuid, text
from sqlalchemy.orm import Mapped, mapped_column
from uuid_utils.compat import uuid7

from storico.infrastructure.database.models.base import Base


class TaskInvalidationModel(Base):
    """One row per invalidation mark on a task."""

    __tablename__ = "task_invalidations"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid7)
    task_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False
    )
    reason: Mapped[str] = mapped_column(String(500), nullable=False)
    # Actor references survive account deletion (the ``projects.created_by`` convention):
    # the mark and its reason stay; only the actor id is nulled.
    marked_by: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    revoked_by: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    marked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        # The naming convention prefixes ``ck_task_invalidations_`` — the short names here
        # land as ``ck_task_invalidations_reason_not_blank`` and
        # ``ck_task_invalidations_revoke_pair``, matching revision 0028.
        CheckConstraint("length(trim(reason)) > 0", name="reason_not_blank"),
        CheckConstraint("(revoked_by IS NULL) = (revoked_at IS NULL)", name="revoke_pair"),
        Index("ix_task_invalidations_task_id", "task_id"),
        # One active mark per task. Partial in both dialects: a full unique index on
        # ``task_id`` would forbid the revoke-then-re-mark history the table exists for.
        # ``sqlite_where`` mirrors the Postgres shape so the unit schema enforces it too.
        Index(
            "uq_task_invalidations_active_task",
            "task_id",
            unique=True,
            postgresql_where=text("revoked_at IS NULL"),
            sqlite_where=text("revoked_at IS NULL"),
        ),
    )
