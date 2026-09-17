"""reduce workspaces.name from String(255) to String(100)

Consistent with the slug limit (100) and project name limit (120).
Unaltered rows that exceed 100 chars are truncated.

Revision ID: 0010
Revises: 0009
Create Date: 2026-07-15
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Truncate any existing names that exceed 100 characters before altering.
    op.execute("UPDATE workspaces SET name = LEFT(name, 100) WHERE LENGTH(name) > 100")
    op.alter_column(
        "workspaces",
        "name",
        type_=sa.String(100),
        existing_type=sa.String(255),
        nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "workspaces",
        "name",
        type_=sa.String(255),
        existing_type=sa.String(100),
        nullable=False,
    )
