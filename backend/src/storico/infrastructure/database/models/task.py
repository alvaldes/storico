"""TaskModel — ORM model for the tasks table."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import JSON, DateTime, ForeignKey, Index, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from storico.infrastructure.database.models.base import Base


class TaskModel(Base):
    """ORM model representing a task derived from a user story."""

    __tablename__ = "tasks"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    user_story_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("user_stories.id"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="backlog")
    priority: Mapped[str] = mapped_column(String(20), nullable=False, default="medium")
    labels: Mapped[dict | None] = mapped_column(JSON, nullable=True, default=None)
    dependencies: Mapped[dict | None] = mapped_column(JSON, nullable=True, default=None)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    __table_args__ = (
        Index("ix_tasks_user_story_id", "user_story_id"),
    )

    user_story: Mapped["UserStoryModel"] = relationship(  # noqa: F821, UP037
        back_populates="tasks", lazy="selectin"
    )
