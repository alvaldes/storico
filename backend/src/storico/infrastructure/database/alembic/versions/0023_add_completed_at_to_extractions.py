"""add completed_at to extractions

An extraction records when it started (``created_at``) and never recorded when it
finished. The API advertised a ``completed_at`` while every construction site
hardcoded ``None``, so a finished extraction had no end time anywhere and the field
could not have been anything but null by construction.

This revision adds the column. It is **nullable** because a ``pending`` extraction
has not finished yet: the invariant is "non-null exactly when ``status`` is
terminal", not "not null".

**No backfill, deliberately.** An extraction that finished before this column
existed has no recoverable end time. Copying ``created_at`` would report an
instantaneous extraction, and using ``now()`` would report every historical row as
having completed at deploy time. Both invent data, and a null is the honest answer
for a row whose end time was never recorded. Rows that predate this revision keep
``NULL``, and the API returns it.

**Run this before deploying the release that reads the column.** The new ORM model
selects ``completed_at`` on every load, so the code needs the column to exist —
which is the opposite order from revision 0022, where the code had to be live first.
Adding a nullable column is otherwise additive: the previous release does not select
it and is unaffected while both are running.

Revision ID: 0023
Revises: 0022
Create Date: 2026-09-19
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0023"
down_revision: str | None = "0022"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add the nullable ``completed_at`` column."""
    op.add_column(
        "extractions",
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    """Drop the column.

    The end times are lost with it, but they are reproducible in the sense that
    matters here: the column can be re-added, and a row that has an end time is a row
    whose status is terminal and whose ``created_at`` bounds it. Nothing else in the
    schema depends on the value.
    """
    op.drop_column("extractions", "completed_at")
