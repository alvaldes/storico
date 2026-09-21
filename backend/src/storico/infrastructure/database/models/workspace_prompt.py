"""WorkspacePromptModel — ORM model for the workspace_prompts table."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, Text, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from uuid_utils.compat import uuid7

from storico.infrastructure.database.models.base import Base


class WorkspacePromptModel(Base):
    """ORM model representing prompt configuration for a workspace."""

    __tablename__ = "workspace_prompts"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid7)
    workspace_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    system_prompt: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    instruction_template: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    # JSONB on Postgres, plain JSON elsewhere: revision 0009 converted this column to JSONB
    # explicitly, naming richer Postgres indexing as the reason, and nothing here queries inside
    # the document. Same dialect variant as ``user_preferences.preferences``, and load-bearing for
    # the same reason — see that model's comment.
    few_shot_examples: Mapped[dict | None] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"), nullable=True, default=None
    )
    few_shot_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    few_shot_limit: Mapped[int] = mapped_column(
        Integer, nullable=False, default=3, server_default="3"
    )
    few_shot_threshold: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.85, server_default="0.85"
    )
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
