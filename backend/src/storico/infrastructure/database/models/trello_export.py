"""TrelloExportModel — ORM model for the trello_exports table."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, Uuid
from sqlalchemy.dialects.postgresql import ENUM as PGEnum
from sqlalchemy.orm import Mapped, mapped_column
from uuid_utils.compat import uuid7

from storico.domain.entities.trello_export import TrelloExportStatus
from storico.infrastructure.database.models.base import Base

# Created by migration 0031; the model never creates it (the extraction enum's
# own convention — 0018 owns ``extraction_status_new`` the same way).
_TRELLO_EXPORT_STATUS_ENUM_NAME = "trello_export_status_new"


class TrelloExportModel(Base):
    """ORM model representing one Trello export job."""

    __tablename__ = "trello_exports"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid7)
    workspace_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    scope: Mapped[str] = mapped_column(String(20), nullable=False)
    # Recorded as values, not foreign keys — by design: a cascading delete of
    # the story or its project mid-run would otherwise destroy the job row the
    # member is polling for. See ``TrelloExport``.
    project_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True, default=None)
    user_story_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True, default=None)
    status: Mapped[TrelloExportStatus] = mapped_column(
        PGEnum(
            TrelloExportStatus,
            name=_TRELLO_EXPORT_STATUS_ENUM_NAME,
            create_type=False,
            values_callable=lambda x: [e.value for e in x],
        ),
        nullable=False,
        default=TrelloExportStatus.PENDING,
    )
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True, default=None)
    # Trello's own identity for the board: string ids and a URL, both absent
    # until the board exists — a failed board creation has neither, and a
    # partial failure keeps both so the half-built board stays reachable.
    board_id: Mapped[str | None] = mapped_column(String(100), nullable=True, default=None)
    board_url: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    cards_created: Mapped[int | None] = mapped_column(Integer, nullable=True, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # Nullable because a ``pending`` job has not finished. Non-null exactly when
    # the status is terminal, enforced by the call sites that reach one.
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )

    __table_args__ = (Index("ix_trello_exports_workspace_id", "workspace_id"),)
