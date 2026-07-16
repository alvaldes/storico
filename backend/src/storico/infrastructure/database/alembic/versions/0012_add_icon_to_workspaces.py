"""add icon column to workspaces

Allows workspaces to have an optional Lucide icon name for display
in the sidebar and project cards.

Revision ID: 0012
Revises: 0011
Create Date: 2026-07-16
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0012"
down_revision: Union[str, None] = "0011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "workspaces",
        sa.Column("icon", sa.String(100), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("workspaces", "icon")
