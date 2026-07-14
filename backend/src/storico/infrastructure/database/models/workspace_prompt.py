"""WorkspacePromptModel — ORM model for the workspace_prompts table."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, String, Text, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from storico.infrastructure.database.models.base import Base


class WorkspacePromptModel(Base):
    """ORM model representing prompt configuration for a workspace."""

    __tablename__ = "workspace_prompts"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    workspace_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    system_prompt: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    instruction_template: Mapped[str | None] = mapped_column(
        Text, nullable=True, default=None
    )
    few_shot_examples: Mapped[dict | None] = mapped_column(
        JSONB, nullable=True, default=None
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
