"""add trello_exports.extraction_id — the version the job exported

One nullable column on ``trello_exports``: the extraction id of the version the
job was told to export, ``NULL`` when the trigger asked for current versions
(the behaviour every row before this revision has). Recorded as a value with no
foreign key, the same posture as ``project_id``/``user_story_id`` — the job row
must outlive its target so a member polling it can still say which version the
board came from.

This migration is additive, so like ``0029``, ``0030`` and ``0031`` it needs no
empty-database guard: adding a nullable column is safe on a table of any
population. The whole revision runs in one transaction, so a failure rolls back
to a schema that is exactly what ``0031`` left — no half-applied state — and
``downgrade`` drops exactly the column ``upgrade`` adds, nothing else.

Revision ID: 0032
Revises: 0031
Create Date: 2026-10-10
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0032"
down_revision: str | None = "0031"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "trello_exports",
        sa.Column("extraction_id", sa.Uuid(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("trello_exports", "extraction_id")
