"""story_deletions — the deletion audit record that survives the story it records

Creates ``story_deletions``: one row per sanctioned story deletion, carrying the story's
identity as values (``story_id``, ``project_id``, ``workspace_id``, the
``(actor, feature, benefit)`` trio) and the destroyed ``version_numbers`` as JSON, with
deliberately no foreign key to ``stories``, ``projects`` or ``extractions`` — a record
referencing the story it records would be destroyed by the very delete it records. The only
FK is ``deleted_by -> users.id ON DELETE SET NULL`` (the ``projects.created_by`` convention
from ``0014``), so an account deletion nulls the actor reference instead of erasing the
audit trail. One composite index, ``(workspace_id, deleted_at)``, serves the only plausible
query against an audit record: what was deleted in this workspace, newest first.

This migration is additive, so unlike ``0028`` it needs no empty-database guard: ``0028``
reshaped ``extractions``/``tasks`` in ways no backfill could reconstruct (D11) and had to
refuse populated tables, while creating a brand-new empty table is safe on a database of any
population — there is no existing row to migrate and nothing to backfill. Do not "fix" the
absence of the guard: copying it here would refuse the deploy for no reason.

Revision ID: 0029
Revises: 0028
Create Date: 2026-09-30
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0029"
down_revision: str | None = "0028"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "story_deletions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("story_id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("actor", sa.Text(), nullable=False),
        sa.Column("feature", sa.Text(), nullable=False),
        sa.Column("benefit", sa.Text(), nullable=False),
        # JSON, not a Postgres ARRAY: the unit suite builds its schema on SQLite, where
        # ARRAY does not exist (same portability choice as slice (a)'s prompt_config).
        sa.Column("version_numbers", sa.JSON(), nullable=False),
        sa.Column("deleted_by", sa.Uuid(), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["deleted_by"],
            ["users.id"],
            name=op.f("fk_story_deletions_deleted_by_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_story_deletions")),
    )
    op.create_index(
        op.f("ix_story_deletions_workspace_deleted_at"),
        "story_deletions",
        ["workspace_id", "deleted_at"],
        unique=False,
    )


def downgrade() -> None:
    # Losing this table loses the audit trail of deletes performed while the release was
    # live — the price of the rollback the design records, not a guard decision.
    op.drop_index(
        op.f("ix_story_deletions_workspace_deleted_at"),
        table_name="story_deletions",
    )
    op.drop_table("story_deletions")
