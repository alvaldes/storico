"""add few-shot retrieval config to workspace_prompts

Revision ID: 0020
Revises: 0019
Create Date: 2026-09-14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0020"
down_revision: str | None = "0019"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add the automatic few-shot retrieval configuration columns.

    ``few_shot_examples`` is retained (read-only) so the one-time seed job can
    migrate legacy manual examples into Qdrant; it is dropped in a follow-up.
    """
    op.add_column(
        "workspace_prompts",
        sa.Column("few_shot_enabled", sa.Boolean(), nullable=False, server_default="true"),
    )
    op.add_column(
        "workspace_prompts",
        sa.Column("few_shot_limit", sa.Integer(), nullable=False, server_default="3"),
    )
    op.add_column(
        "workspace_prompts",
        sa.Column("few_shot_threshold", sa.Float(), nullable=False, server_default="0.85"),
    )


def downgrade() -> None:
    """Remove the few-shot retrieval configuration columns."""
    op.drop_column("workspace_prompts", "few_shot_threshold")
    op.drop_column("workspace_prompts", "few_shot_limit")
    op.drop_column("workspace_prompts", "few_shot_enabled")
