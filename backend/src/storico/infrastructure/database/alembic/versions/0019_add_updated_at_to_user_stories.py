"""add updated_at to user_stories

Revision ID: 0019
Revises: 0018
Create Date: 2026-09-09 11:47:11.715043
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0019"
down_revision: str | None = "0018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Add updated_at column to user_stories
    op.add_column(
        "user_stories",
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )


def downgrade() -> None:
    # Remove updated_at column from user_stories
    op.drop_column("user_stories", "updated_at")
