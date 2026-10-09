"""add workspace_trello_configs — the encrypted Trello credentials of a workspace

Creates ``workspace_trello_configs``: one row per workspace (``workspace_id`` unique
FK with ``ON DELETE CASCADE``, the same convention as ``workspace_llm_configs``),
holding the ``api_key`` and ``token`` an admin pastes in the workspace settings. Both
columns are ``String(1000)`` because the repository stores ciphertext, and Fernet's
base64 output is about 1.4x the plaintext the request schema caps at 500 characters —
the same sizing rule revision 0024 documented for the LLM key. The encryption itself
has no schema: ``FernetCipher`` marks its values with the ``v1:`` prefix inside the
column, so this migration only provides the storage.

This migration is additive, so like ``0029`` it needs no empty-database guard: creating
a brand-new empty table is safe on a database of any population.

Revision ID: 0030
Revises: 0029
Create Date: 2026-10-08
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0030"
down_revision: str | None = "0029"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "workspace_trello_configs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("api_key", sa.String(1000), nullable=True),
        sa.Column("token", sa.String(1000), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_workspace_trello_configs")),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name=op.f("fk_workspace_trello_configs_workspace_id_workspaces"),
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "workspace_id",
            name=op.f("uq_workspace_trello_configs_workspace_id"),
        ),
    )


def downgrade() -> None:
    # Dropping the table drops the stored credentials; the admin re-pastes them.
    op.drop_table("workspace_trello_configs")
