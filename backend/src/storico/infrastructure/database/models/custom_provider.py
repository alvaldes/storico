"""CustomProviderModel — ORM model for the custom_providers table."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column
from uuid_utils.compat import uuid7

from storico.infrastructure.database.models.base import Base


class CustomProviderModel(Base):
    """ORM model representing a workspace-registered LLM provider name.

    Unlike ``workspace_llm_configs`` and ``workspace_prompts`` this is a 1:N
    relation, so ``workspace_id`` is indexed but **not** unique. The composite
    unique constraint is what keeps one workspace from registering the same name
    twice while still letting two workspaces each register it once.
    """

    __tablename__ = "custom_providers"
    __table_args__ = (
        UniqueConstraint("workspace_id", "name", name="uq_custom_providers_workspace_id_name"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid7)
    workspace_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(50), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
