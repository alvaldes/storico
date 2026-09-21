"""UserPreferencesModel — ORM model for the user_preferences table."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import JSON, DateTime, ForeignKey, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from storico.infrastructure.database.models.base import Base


class UserPreferencesModel(Base):
    """ORM model representing per-user application preferences."""

    __tablename__ = "user_preferences"

    user_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    # JSONB on Postgres, plain JSON on every other dialect. Revision 0005 created this column as
    # JSONB and nothing anywhere queries inside the document, so the migration is authoritative
    # and the model under-declared it. The variant is load-bearing rather than stylistic: a bare
    # ``postgresql.JSONB()`` does not compile on SQLite, and the unit suite builds its whole
    # schema from these models with ``Base.metadata.create_all``.
    preferences: Mapped[dict] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"), nullable=False, default=dict
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )
