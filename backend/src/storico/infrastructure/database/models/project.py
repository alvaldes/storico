"""ProjectModel — ORM model for the projects table."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from storico.infrastructure.database.models.base import Base


class ProjectModel(Base):
    """ORM model representing a project owned by a user."""

    __tablename__ = "projects"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    owner_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    owner: Mapped["UserModel"] = relationship(back_populates="projects", lazy="selectin")  # noqa: F821, UP037
    user_stories: Mapped[list["UserStoryModel"]] = relationship(  # noqa: F821, UP037
        back_populates="project", lazy="selectin"
    )
