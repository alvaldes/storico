"""TaskModel — ORM model for the tasks table."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import JSON, DateTime, ForeignKey, Index, String, Text, Uuid
from sqlalchemy.dialects.postgresql import ENUM as PGEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from uuid_utils.compat import uuid7

from storico.domain.entities.task import TaskStatus
from storico.infrastructure.database.models.base import Base


class TaskModel(Base):
    """ORM model representing a task derived from a user story."""

    __tablename__ = "tasks"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid7)
    user_story_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("user_stories.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[TaskStatus] = mapped_column(
        PGEnum(
            TaskStatus,
            name="task_status_new",
            create_type=False,
            values_callable=lambda x: [e.value for e in x],
        ),
        nullable=False,
        default=TaskStatus.BACKLOG,
    )
    priority: Mapped[str] = mapped_column(String(20), nullable=False, default="medium")
    labels: Mapped[dict | None] = mapped_column(JSON, nullable=True, default=None)
    dependencies: Mapped[dict | None] = mapped_column(JSON, nullable=True, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    # ``ix_tasks_user_story_id`` comes from revision 0001. ``idx_tasks_status`` comes from 0016:
    # no query in the repository filters ``tasks.status`` in SQL (the Kanban grouping is
    # client-side), but a deliberately created index is cheaper to document than to remove and
    # want back, and the migrations are the side that already has it.
    __table_args__ = (
        Index("ix_tasks_user_story_id", "user_story_id"),
        Index("idx_tasks_status", "status"),
    )

    user_story: Mapped["UserStoryModel"] = relationship(  # noqa: F821, UP037
        back_populates="tasks", lazy="selectin"
    )
