"""UserModel — ORM model for the users table."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from storico.infrastructure.database.models.base import Base


class UserModel(Base):
    """ORM model representing a registered user."""

    __tablename__ = "users"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    auth_provider: Mapped[str] = mapped_column(String(50), nullable=False)
    auth_id: Mapped[str] = mapped_column(String(255), nullable=False)
    avatar_url: Mapped[str | None] = mapped_column(String(500), nullable=True, default=None)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    __table_args__ = (
        UniqueConstraint("email", name="uq_users_email"),
        UniqueConstraint(
            "auth_provider", "auth_id", name="uq_users_auth_provider_auth_id"
        ),
    )

    projects: Mapped[list["ProjectModel"]] = relationship(  # noqa: F821, UP037
        back_populates="owner", lazy="selectin"
    )
