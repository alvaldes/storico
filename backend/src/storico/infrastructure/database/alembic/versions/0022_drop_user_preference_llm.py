"""drop the per-user LLM settings from stored preferences

``AppSettings`` used to declare an ``llm`` block — a provider selection plus a
``model``/``api_key``/``base_url`` per provider — and the user-preferences endpoint
round-tripped it. Nothing ever read it: the live configuration is
``workspace_llm_configs``, a different row with a different owner. The field is gone
from the schema, and ``AppSettings`` sets ``extra="forbid"``, so a row that still
stores the key would fail validation on read.

This revision removes exactly that key from every stored document and leaves the rest
of it (today, ``export``) alone.

Revision ID: 0022
Revises: 0021
Create Date: 2026-06-30
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.orm import Session

# revision identifiers, used by Alembic.
revision: str = "0022"
down_revision: str | None = "0021"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# The key this revision deletes. It is a name, not a schema object: the point is that the
# document stops carrying it.
_REMOVED_KEY = "llm"


def upgrade() -> None:
    """Remove the ``llm`` key from every stored preferences document."""
    preferences = sa.table(
        "user_preferences",
        sa.column("user_id", sa.Uuid()),
        sa.column("preferences", sa.JSON()),
    )

    # Read through a Session rather than a raw result: the column is JSON, and going through
    # the session is what gives the driver's decoding a chance to produce a dict.
    with Session(op.get_bind()) as session:
        rows = session.execute(
            sa.select(preferences.c.user_id, preferences.c.preferences)
        ).fetchall()

        cleaned = [
            (user_id, {key: value for key, value in stored.items() if key != _REMOVED_KEY})
            for user_id, stored in rows
            # Defensive about the shape: a document that is not an object has nothing to
            # remove, and one without the key is already clean, so neither is written back.
            if isinstance(stored, dict) and _REMOVED_KEY in stored
        ]

        for user_id, document in cleaned:
            session.execute(
                sa.update(preferences)
                .where(preferences.c.user_id == user_id)
                .values(preferences=document)
            )

        # `updated_at` is deliberately left alone. It answers "when did the user last save
        # their preferences" — the settings response returns it — and this revision is not a
        # save by the user.
        session.commit()


def downgrade() -> None:
    """No-op: the removed keys cannot be recovered.

    Re-adding the ``llm`` field to the schema is not a data operation, and inventing an
    empty block here would write a configuration nobody asked for. A downgrade that
    silently loses the same data in the other direction is worth less than one that says
    so.
    """
