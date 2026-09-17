"""add custom_providers table for workspace-registered provider names

A custom provider used to exist only as the current value of
``workspace_llm_configs.provider``. This revision gives it a row of its own,
scoped by workspace, and backfills one row per existing config whose provider is
not one of the four first-class providers.

Revision ID: 0021
Revises: 0020
Create Date: 2026-09-18
"""

from collections.abc import Sequence
from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op
from sqlalchemy.orm import Session
from uuid_utils.compat import uuid7

# revision identifiers, used by Alembic.
revision: str = "0021"
down_revision: str | None = "0020"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Mirrors ``KNOWN_PROVIDERS`` in the frontend and the guard in the providers API:
# these four names are first-class, so they must never be registered as custom.
_KNOWN_PROVIDERS = ("ollama", "openai", "anthropic", "gemini")

# Matches the ``String(50)`` bound on ``workspace_llm_configs.provider``.
_NAME_MAX_LENGTH = 50


def upgrade() -> None:
    """Create ``custom_providers`` and backfill the names already in use."""
    op.create_table(
        "custom_providers",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(50), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_custom_providers")),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name=op.f("fk_custom_providers_workspace_id_workspaces"),
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "workspace_id",
            "name",
            name=op.f("uq_custom_providers_workspace_id_name"),
        ),
    )
    op.create_index("ix_custom_providers_workspace_id", "custom_providers", ["workspace_id"])

    _backfill_existing_custom_providers()


def _backfill_existing_custom_providers() -> None:
    """Give every already-configured custom provider a row of its own.

    The name is copied verbatim rather than normalized: it is the value
    ``workspace_llm_configs.provider`` already holds and the value extraction
    matches on, so rewriting the case here would leave the registry and the
    config disagreeing. A legacy name that the API's pattern would now reject is
    still worth a row — it makes the name visible in the select, where the
    rename action can fix it.
    """
    configs = sa.table(
        "workspace_llm_configs",
        sa.column("workspace_id", sa.Uuid()),
        sa.column("provider", sa.String(_NAME_MAX_LENGTH)),
    )
    # Read through a Session rather than the raw migration connection: the id column
    # has no server default, so the uuid7 values have to come from Python, and a
    # session is the API that reads them back into rows.
    with Session(op.get_bind()) as session:
        rows = session.execute(
            sa.select(configs.c.workspace_id, configs.c.provider).where(
                configs.c.provider.notin_(_KNOWN_PROVIDERS)
            )
        ).fetchall()

    now = datetime.now(UTC)
    seen: set[tuple[object, str]] = set()
    new_rows: list[dict[str, object]] = []
    for workspace_id, provider in rows:
        name = (provider or "").strip()
        # A name the column cannot hold, or one that is effectively absent, has no
        # valid registry row to write.
        if not name or len(name) > _NAME_MAX_LENGTH or name in _KNOWN_PROVIDERS:
            continue
        # One config row per workspace already rules this out; the guard keeps a
        # duplicate from aborting the whole migration if that ever changes.
        if (workspace_id, name) in seen:
            continue
        seen.add((workspace_id, name))
        new_rows.append(
            {
                "id": uuid7(),
                "workspace_id": workspace_id,
                "name": name,
                "created_at": now,
                "updated_at": now,
            }
        )

    if new_rows:
        op.bulk_insert(
            sa.table(
                "custom_providers",
                sa.column("id", sa.Uuid()),
                sa.column("workspace_id", sa.Uuid()),
                sa.column("name", sa.String(_NAME_MAX_LENGTH)),
                sa.column("created_at", sa.DateTime(timezone=True)),
                sa.column("updated_at", sa.DateTime(timezone=True)),
            ),
            new_rows,
        )


def downgrade() -> None:
    """Drop the registry. Configured provider names themselves are untouched."""
    op.drop_index("ix_custom_providers_workspace_id", table_name="custom_providers")
    op.drop_table("custom_providers")
