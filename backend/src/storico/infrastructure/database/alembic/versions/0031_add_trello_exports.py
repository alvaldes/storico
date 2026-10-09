"""add trello_exports — the persisted export job a member polls

Creates ``trello_exports``: one row per Trello export request, the polling
answer for an asynchronous job (D5), mirroring how the extraction job records
state — a ``trello_export_status_new`` enum whose labels are the domain's
``TrelloExportStatus`` members, created here (the model declares
``create_type=False``) and dropped by this revision's ``downgrade``.

``project_id`` and ``user_story_id`` are deliberately plain columns with **no**
foreign keys. Everywhere else this schema FKs its targets, but a cascading
delete of the story or its project mid-run would destroy the job row the member
is polling for exactly when the answer is most needed; the job records its
target as a value so it can outlive it and still report what happened.

``error_code``, ``board_id``, ``board_url`` and ``cards_created`` are nullable
because a pending or running job has none of them, and a job that failed before
the board was created has no board identity — while a failure *after* creation
keeps ``board_id``/``board_url`` so the half-built board stays reachable.

This migration is additive, so like ``0029`` and ``0030`` it needs no
empty-database guard: creating a brand-new empty table is safe on a database of
any population.

Revision ID: 0031
Revises: 0030
Create Date: 2026-10-09
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ENUM

# revision identifiers, used by Alembic.
revision: str = "0031"
down_revision: str | None = "0030"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# The labels ``trello_export_status_new`` declares, matching
# ``TrelloExportStatus`` in the domain. Spelled here rather than imported from
# the domain enum for the reason every migration in this repository spells its
# own names: a revision has to keep working against the schema as it was when
# the revision was written, after the enum has moved on.
_STATUS_LABELS: tuple[str, ...] = ("pending", "running", "completed", "failed")

# ``create_type=False`` because ``upgrade`` creates the type explicitly, before the table:
# leaving it ``True`` makes ``create_table`` issue a second ``CREATE TYPE`` inside that same
# transaction, and PostgreSQL refuses it with a duplicate-object error. Measured on a real
# database on 2026-10-09 — this revision failed to apply there while every test that would
# have caught it skipped for lack of Docker. The rollback left the schema clean.
_STATUS_ENUM = ENUM(*_STATUS_LABELS, name="trello_export_status_new", create_type=False)


def upgrade() -> None:
    _STATUS_ENUM.create(op.get_bind(), checkfirst=True)
    op.create_table(
        "trello_exports",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("scope", sa.String(20), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=True),
        sa.Column("user_story_id", sa.Uuid(), nullable=True),
        sa.Column("status", _STATUS_ENUM, nullable=False, server_default="pending"),
        sa.Column("error_code", sa.String(64), nullable=True),
        sa.Column("board_id", sa.String(100), nullable=True),
        sa.Column("board_url", sa.Text(), nullable=True),
        sa.Column("cards_created", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_trello_exports")),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name=op.f("fk_trello_exports_workspace_id_workspaces"),
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "ix_trello_exports_workspace_id",
        "trello_exports",
        ["workspace_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_trello_exports_workspace_id", table_name="trello_exports")
    op.drop_table("trello_exports")
    # Dropping the table drops the polling answers; the enum type this revision
    # owns goes with it, the same way 0018's own downgrade drops its type.
    _STATUS_ENUM.drop(op.get_bind(), checkfirst=True)
