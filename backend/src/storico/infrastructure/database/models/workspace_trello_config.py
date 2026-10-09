"""WorkspaceTrelloConfigModel — ORM model for the workspace_trello_configs table."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column
from uuid_utils.compat import uuid7

from storico.infrastructure.database.models.base import Base


class WorkspaceTrelloConfigModel(Base):
    """ORM model representing the Trello credentials of a workspace."""

    __tablename__ = "workspace_trello_configs"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid7)
    workspace_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    # Wide enough for the ciphertext of the longest credential the API accepts, which is not the
    # same as being wide enough for the credential. The request schema caps the plaintext at 500
    # characters, and Fernet's base64 output is about 1.4x with its padding, so 500 characters
    # measure 763 stored — a plaintext that fit the request would have overflowed the moment it
    # was encrypted. SQLite does not enforce a VARCHAR length and would not have said so;
    # Postgres would have raised on the write. A test asserts the two numbers against each
    # other so they cannot drift apart.
    api_key: Mapped[str | None] = mapped_column(String(1000), nullable=True, default=None)
    token: Mapped[str | None] = mapped_column(String(1000), nullable=True, default=None)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
