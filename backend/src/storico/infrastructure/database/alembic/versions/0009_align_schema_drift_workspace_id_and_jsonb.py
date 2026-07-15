"""align schema drift: projects.workspace_id NOT NULL, workspace_prompts JSONB

Aligns two schema drifts detected by autogenerate but not included in 0008:
1. projects.workspace_id → NOT NULL (model requires it, 0007 created it nullable)
2. workspace_prompts.few_shot_examples → JSONB (model uses JSONB, 0007 created JSON)

Revision ID: 0009
Revises: 0008
Create Date: 2026-07-15
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0009"
down_revision: Union[str, None] = "0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # projects.workspace_id: created nullable in 0007, model expects NOT NULL
    op.alter_column(
        "projects",
        "workspace_id",
        existing_type=sa.Uuid(),
        nullable=False,
    )
    # workspace_prompts.few_shot_examples: created as sa.JSON() in 0007,
    # model uses JSONB for richer PostgreSQL indexing/operators
    op.alter_column(
        "workspace_prompts",
        "few_shot_examples",
        existing_type=sa.JSON(),
        type_=postgresql.JSONB(),
        postgresql_using="few_shot_examples::jsonb",
    )


def downgrade() -> None:
    # Reverse: projects.workspace_id → nullable again
    op.alter_column(
        "projects",
        "workspace_id",
        existing_type=sa.Uuid(),
        nullable=True,
    )
    # Reverse: workspace_prompts.few_shot_examples → back to JSON
    op.alter_column(
        "workspace_prompts",
        "few_shot_examples",
        existing_type=postgresql.JSONB(),
        type_=sa.JSON(),
    )
