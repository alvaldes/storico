"""UserStoryModel — ORM model for the user_stories table."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, Index, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from storico.infrastructure.database.models.base import Base


class UserStoryModel(Base):
    """ORM model representing a user story within a project."""

    __tablename__ = "user_stories"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    project_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("projects.id"), nullable=False
    )
    actor: Mapped[str] = mapped_column(Text, nullable=False)
    feature: Mapped[str] = mapped_column(Text, nullable=False)
    benefit: Mapped[str] = mapped_column(Text, nullable=False)
    raw_text: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    __table_args__ = (
        Index("ix_user_stories_project_id", "project_id"),
    )

    project: Mapped["ProjectModel"] = relationship(  # noqa: F821, UP037
        back_populates="user_stories", lazy="selectin"
    )
    tasks: Mapped[list["TaskModel"]] = relationship(  # noqa: F821, UP037
        back_populates="user_story", lazy="selectin"
    )
    extractions: Mapped[list["ExtractionModel"]] = relationship(  # noqa: F821, UP037
        back_populates="user_story", lazy="selectin"
    )
