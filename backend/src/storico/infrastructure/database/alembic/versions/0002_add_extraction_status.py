"""add_extraction_status

Revision ID: 0002
Revises: 0001
Create Date: 2026-07-06 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "extractions",
        sa.Column(
            "status",
            sa.String(20),
            nullable=False,
            server_default="pending",
        ),
    )
    op.add_column(
        "extractions",
        sa.Column(
            "error_info",
            sa.Text(),
            nullable=True,
            default=None,
        ),
    )


def downgrade() -> None:
    op.drop_column("extractions", "error_info")
    op.drop_column("extractions", "status")
