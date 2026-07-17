"""ExtractionModel — ORM model for the extractions table."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Index, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from storico.infrastructure.database.models.base import Base


class ExtractionModel(Base):
    """ORM model representing an LLM extraction result for a user story."""

    __tablename__ = "extractions"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    user_story_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("user_stories.id", ondelete="CASCADE"), nullable=False
    )
    model_used: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pending"
    )
    error_info: Mapped[str | None] = mapped_column(
        Text, nullable=True, default=None
    )
    prompt_config: Mapped[dict | None] = mapped_column(JSON, nullable=True, default=None)
    raw_response: Mapped[str] = mapped_column(Text, nullable=False)
    confidence_score: Mapped[float | None] = mapped_column(
        Float, nullable=True, default=None
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    __table_args__ = (
        Index("ix_extractions_user_story_id", "user_story_id"),
    )

    user_story: Mapped["UserStoryModel"] = relationship(  # noqa: F821, UP037
        back_populates="extractions", lazy="selectin"
    )
