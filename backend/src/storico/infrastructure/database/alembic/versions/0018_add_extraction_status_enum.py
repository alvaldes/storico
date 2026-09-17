"""Add extraction_status enum type

Revision ID: 0018
Revises: 0017
Create Date: 2026-09-07
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
from sqlalchemy.dialects.postgresql import ENUM

# revision identifiers, used by Alembic.
revision: str = "0018"
down_revision: str | None = "0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Enum definition matching the model
EXTRACTION_STATUS_ENUM = ENUM(
    "pending",
    "completed",
    "failed",
    name="extraction_status_new",
    create_type=True,
)


def upgrade() -> None:
    # Create the enum type
    EXTRACTION_STATUS_ENUM.create(op.get_bind(), checkfirst=True)


def downgrade() -> None:
    EXTRACTION_STATUS_ENUM.drop(op.get_bind(), checkfirst=True)
