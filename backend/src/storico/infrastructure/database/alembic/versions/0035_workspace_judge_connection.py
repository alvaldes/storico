"""add the judge connection to workspace_llm_configs — the judge's own provider, credential, endpoint (D9/S10)

Three nullable columns on ``workspace_llm_configs``, beside the ``judge_model`` that
``0034`` added: ``judge_provider``, ``judge_api_key`` and ``judge_base_url``. Together
the four let the workspace's LLM-as-a-Judge run on a second, independent LLM
configuration — another provider with another credential and another model — instead
of only swapping the model on the extraction's own configuration (S10). Each field
falls back independently to the extraction value, so any subset is legitimate: a
judge model on the extraction's provider, or a full judge block on another provider.

``judge_api_key`` is a credential and is therefore the same width as ``api_key``
(``String(1000)``): what the column stores is Fernet ciphertext of a plaintext the
request schema caps at 500 characters, and the same arithmetic that forced ``0024``
to widen ``api_key`` applies unchanged. The repository remains the only code that
encrypts on the way in and decrypts on the way out.

This migration is additive, so like ``0029``, ``0030``, ``0031``, ``0032``,
``0033`` and ``0034`` it needs no empty-database guard: adding nullable columns is
safe on a table of any population, and there is nothing to backfill — a workspace
that never configured a judge connection legitimately has none, and the fallback
rule gives every existing row today's behavior exactly. The whole revision runs in
one transaction, so a failure rolls back to a schema that is exactly what ``0034``
left, and ``downgrade`` drops exactly the three columns ``upgrade`` adds, nothing
else.

Revision ID: 0035
Revises: 0034
Create Date: 2026-11-03
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0035"
down_revision: str | None = "0034"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "workspace_llm_configs",
        sa.Column("judge_provider", sa.String(length=50), nullable=True),
    )
    op.add_column(
        "workspace_llm_configs",
        sa.Column("judge_api_key", sa.String(length=1000), nullable=True),
    )
    op.add_column(
        "workspace_llm_configs",
        sa.Column("judge_base_url", sa.String(length=500), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("workspace_llm_configs", "judge_base_url")
    op.drop_column("workspace_llm_configs", "judge_api_key")
    op.drop_column("workspace_llm_configs", "judge_provider")
