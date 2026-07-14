"""WorkspaceLLMConfigModel — ORM model for the workspace_llm_configs table."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from storico.infrastructure.database.models.base import Base


class WorkspaceLLMConfigModel(Base):
    """ORM model representing LLM configuration for a workspace."""

    __tablename__ = "workspace_llm_configs"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    workspace_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    model: Mapped[str | None] = mapped_column(String(100), nullable=True, default=None)
    temperature: Mapped[float | None] = mapped_column(Float, nullable=True, default=None)
    max_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True, default=None)
    base_url: Mapped[str | None] = mapped_column(String(500), nullable=True, default=None)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
