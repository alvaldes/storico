"""add workspace_llm_configs.judge_model — which model judges (D7)

One nullable column on ``workspace_llm_configs``: the model name the workspace's
LLM-as-a-Judge validation runs with. It rides the same provider, credential,
temperature, budget and endpoint as the extraction config — only the model name is
swapped at the judge call — so no second credential, no provider probe and no
cross-provider path exist for it. ``NULL`` (and a stored blank, which the readers
normalize to ``NULL``) means the judge runs with the extraction model, which is the
behavior every run had before this revision. ``judge_result.model`` and
``judge_result.model_source`` (``0033``) record which model actually judged.

This migration is additive, so like ``0029``, ``0030``, ``0031``, ``0032`` and
``0033`` it needs no empty-database guard: adding a nullable column is safe on a
table of any population, and there is nothing to backfill — a workspace that never
chose a judge model legitimately has none. The whole revision runs in one
transaction, so a failure rolls back to a schema that is exactly what ``0033``
left, and ``downgrade`` drops exactly the column ``upgrade`` adds, nothing else.

Revision ID: 0034
Revises: 0033
Create Date: 2026-11-03
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0034"
down_revision: str | None = "0033"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "workspace_llm_configs",
        sa.Column("judge_model", sa.String(length=100), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("workspace_llm_configs", "judge_model")
