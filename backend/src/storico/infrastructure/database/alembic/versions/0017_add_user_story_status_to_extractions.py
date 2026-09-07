"""Add user_story_status column to extractions

Revision ID: 0017
Revises: 0016
Create Date: 2026-09-07
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ENUM

# revision identifiers, used by Alembic.
revision: str = "0017"
down_revision: Union[str, None] = "0016"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Enum definition matching the model
USER_STORY_STATUS_ENUM = ENUM(
    "pending_extraction",
    "extracting",
    "extracted",
    "failed_extraction",
    name="user_story_status_new",
    create_type=False,  # Already created in migration 0016
)


def upgrade() -> None:
    # Add user_story_status column to extractions table
    op.add_column(
        "extractions",
        sa.Column(
            "user_story_status",
            USER_STORY_STATUS_ENUM,
            nullable=False,
            server_default="pending_extraction",
        ),
    )


def downgrade() -> None:
    op.drop_column("extractions", "user_story_status")