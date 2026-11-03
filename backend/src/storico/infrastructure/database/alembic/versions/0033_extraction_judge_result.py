"""add extractions.judge_result — the judge's verdict, not just its confidence

One nullable JSON column on ``extractions``: the record of the run's
LLM-as-a-Judge validation — ``{state, criteria, total_score, max_total, approved,
model, model_source, error, error_type}`` — written once in the same terminal
UPDATE as ``confidence_score``. ``state`` distinguishes the three readings the
confidence column cannot make on its own (D5): ``NULL`` means the judge was
never requested, ``"ok"`` that it ran, ``"failed"`` that it was requested and
failed, carrying its ``error`` and ``error_type``. JSON, not JSONB: the unit
suite builds its schema on SQLite, the same portability choice as
``prompt_config``.

This migration is additive, so like ``0029``, ``0030``, ``0031`` and ``0032`` it
needs no empty-database guard: adding a nullable column is safe on a table of
any population, and there is nothing to backfill — rows written before this
revision legitimately have no judge record. The whole revision runs in one
transaction, so a failure rolls back to a schema that is exactly what ``0032``
left, and ``downgrade`` drops exactly the column ``upgrade`` adds, nothing else.

Revision ID: 0033
Revises: 0032
Create Date: 2026-11-03
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0033"
down_revision: str | None = "0032"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "extractions",
        sa.Column("judge_result", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("extractions", "judge_result")
