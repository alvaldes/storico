"""WorkspaceMemberModel — ORM model for the workspace_members table."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from storico.infrastructure.database.models.base import Base


class WorkspaceMemberModel(Base):
    """ORM model representing a member of a workspace."""

    __tablename__ = "workspace_members"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    workspace_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    __table_args__ = (
        UniqueConstraint(
            "workspace_id", "user_id",
            name="uq_workspace_members_workspace_id_user_id",
        ),
    )

    workspace: Mapped["WorkspaceModel"] = relationship(  # noqa: F821, UP037
        back_populates="members", lazy="selectin"
    )
    user: Mapped["UserModel"] = relationship(  # noqa: F821, UP037
        lazy="selectin"
    )
