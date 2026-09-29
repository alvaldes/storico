"""ExtractionModel — ORM model for the extractions table."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    Double,
    Float,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.dialects.postgresql import ENUM as PGEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from uuid_utils.compat import uuid7

from storico.domain.entities.extraction import ExtractionStatus
from storico.domain.entities.user_story import UserStoryStatus
from storico.infrastructure.database.models.base import Base


class ExtractionModel(Base):
    """ORM model representing an LLM extraction result for a user story."""

    __tablename__ = "extractions"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid7)
    user_story_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("user_stories.id", ondelete="CASCADE"), nullable=False
    )
    model_used: Mapped[str] = mapped_column(String(100), nullable=False)
    # Per-story run identity and run snapshot (revision 0028). ``version_number`` has no
    # default on purpose: it is minted inside the row's own INSERT by
    # ``create_next_version`` — no other writer may ever set it.
    version_number: Mapped[int] = mapped_column(nullable=False)
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    temperature: Mapped[float] = mapped_column(Double, nullable=False)
    # Written once, between render and generate, before the provider is contacted.
    prompt_rendered: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    status: Mapped[ExtractionStatus] = mapped_column(
        PGEnum(
            ExtractionStatus,
            name="extraction_status_new",
            create_type=False,
            values_callable=lambda x: [e.value for e in x],
        ),
        nullable=False,
        default=ExtractionStatus.PENDING,
    )
    user_story_status: Mapped[UserStoryStatus] = mapped_column(
        PGEnum(
            UserStoryStatus,
            name="user_story_status_new",
            create_type=False,
            values_callable=lambda x: [e.value for e in x],
        ),
        nullable=False,
        default=UserStoryStatus.PENDING_EXTRACTION,
    )
    error_info: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    prompt_config: Mapped[dict | None] = mapped_column(JSON, nullable=True, default=None)
    raw_response: Mapped[str] = mapped_column(Text, nullable=False)
    confidence_score: Mapped[float | None] = mapped_column(Float, nullable=True, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # Nullable because a ``pending`` extraction has not finished. The invariant — non-null exactly
    # when ``status`` is terminal — is enforced by the call sites that reach a terminal state, and
    # rows that predate this column keep ``NULL`` rather than a backfilled guess.
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )

    __table_args__ = (
        Index("ix_extractions_user_story_id", "user_story_id"),
        UniqueConstraint("user_story_id", "version_number", name="uq_extractions_story_version"),
        # The naming convention prefixes ``ck_extractions_`` — the short name here lands as
        # ``ck_extractions_version_number_positive``, matching revision 0028.
        CheckConstraint("version_number > 0", name="version_number_positive"),
    )

    user_story: Mapped["UserStoryModel"] = relationship(  # noqa: F821, UP037
        back_populates="extractions", lazy="selectin"
    )
