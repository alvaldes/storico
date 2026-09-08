"""Add extraction_status enum type

Revision ID: 0018
Revises: 0017
Create Date: 2026-09-07
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ENUM

# revision identifiers, used by Alembic.
revision: str = "0018"
down_revision: Union[str, None] = "0017"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

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