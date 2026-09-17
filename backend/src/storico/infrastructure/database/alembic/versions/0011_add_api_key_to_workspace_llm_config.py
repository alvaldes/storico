"""add api_key column to workspace_llm_configs

Revision ID: 0011
Revises: 0010
Create Date: 2026-07-15
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "workspace_llm_configs",
        sa.Column("api_key", sa.String(500), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("workspace_llm_configs", "api_key")
