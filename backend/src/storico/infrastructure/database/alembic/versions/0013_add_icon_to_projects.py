"""add icon column to projects

Allows projects to have an optional Lucide icon name for display
in the sidebar and project cards.

Revision ID: 0013
Revises: 0012
Create Date: 2026-07-16
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0013"
down_revision: Union[str, None] = "0012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "projects",
        sa.Column("icon", sa.String(100), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("projects", "icon")
