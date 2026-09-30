"""extraction versioning — version identity for extraction runs

Adds to ``extractions``: ``version_number`` (per-story, minted inside the row's
own INSERT), ``provider``, ``temperature`` (the run snapshot) and
``prompt_rendered`` (written at render time, before any provider is contacted),
plus the per-story unique pair and its positive-version CHECK. Adds
``tasks.extraction_id`` (every extracted task belongs to its run) and creates
``task_invalidations`` (the invalidation mark is a row, not a column pair).

This migration only ever runs on an empty ``extractions``/``tasks`` pair: it
refuses to run on a populated database instead of backfilling (D11). The data
wipe that precedes it is a separate destructive operation with its own
confirmation — it is not an Alembic step.

Revision ID: 0028
Revises: 0027
Create Date: 2026-09-28
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0028"
down_revision: str | None = "0027"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # The guard runs before any DDL, on the migration's own connection, with raw SQL over
    # table names only — no ORM model, no metadata, so it can never depend on what the
    # models look like today. Meeting a Postgres NOT NULL error halfway through a
    # half-migrated schema is the failure this prevents: the operator gets the sentence
    # naming D11 instead.
    bind = op.get_bind()
    extractions_count = bind.execute(sa.text("SELECT count(*) FROM extractions")).scalar_one()
    tasks_count = bind.execute(sa.text("SELECT count(*) FROM tasks")).scalar_one()
    if extractions_count or tasks_count:
        raise RuntimeError(
            "0028 refuses to run: this migration does not backfill (D11). "
            f"extractions holds {extractions_count} row(s) and tasks holds "
            f"{tasks_count} row(s). Wipe the relational data with its own confirmed "
            "operation before running 0028."
        )

    # --- extractions: version identity and the run snapshot ---
    op.add_column("extractions", sa.Column("version_number", sa.Integer(), nullable=False))
    op.create_check_constraint(
        op.f("ck_extractions_version_number_positive"),
        "extractions",
        "version_number > 0",
    )
    op.add_column("extractions", sa.Column("provider", sa.String(length=50), nullable=False))
    op.add_column("extractions", sa.Column("temperature", sa.Double(), nullable=False))
    op.add_column("extractions", sa.Column("prompt_rendered", sa.Text(), nullable=True))
    op.create_unique_constraint(
        op.f("uq_extractions_story_version"),
        "extractions",
        ["user_story_id", "version_number"],
    )

    # --- tasks: every extracted task belongs to its extraction ---
    op.add_column("tasks", sa.Column("extraction_id", sa.Uuid(), nullable=False))
    op.create_foreign_key(
        op.f("fk_tasks_extraction_id_extractions"),
        "tasks",
        "extractions",
        ["extraction_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index(
        op.f("ix_tasks_extraction_id"),
        "tasks",
        ["extraction_id"],
        unique=False,
    )

    # --- task_invalidations: the mark is a row ---
    op.create_table(
        "task_invalidations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("task_id", sa.Uuid(), nullable=False),
        sa.Column("reason", sa.String(length=500), nullable=False),
        sa.Column("marked_by", sa.Uuid(), nullable=True),
        sa.Column("revoked_by", sa.Uuid(), nullable=True),
        sa.Column("marked_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["task_id"],
            ["tasks.id"],
            name=op.f("fk_task_invalidations_task_id_tasks"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["marked_by"],
            ["users.id"],
            name=op.f("fk_task_invalidations_marked_by_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["revoked_by"],
            ["users.id"],
            name=op.f("fk_task_invalidations_revoked_by_users"),
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "length(trim(reason)) > 0",
            name=op.f("ck_task_invalidations_reason_not_blank"),
        ),
        sa.CheckConstraint(
            "(revoked_by IS NULL) = (revoked_at IS NULL)",
            name=op.f("ck_task_invalidations_revoke_pair"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_task_invalidations")),
    )
    # One partial index, not two columns: the revoke history is the record. Only one
    # non-revoked mark per task may exist.
    op.create_index(
        op.f("uq_task_invalidations_active_task"),
        "task_invalidations",
        ["task_id"],
        unique=True,
        postgresql_where=sa.text("revoked_at IS NULL"),
    )
    op.create_index(
        op.f("ix_task_invalidations_task_id"),
        "task_invalidations",
        ["task_id"],
        unique=False,
    )


def downgrade() -> None:
    # Reverses exactly the list upgrade() built, in reverse. It does NOT re-run the guard:
    # a drop is safe on a populated database, and 0028 can only ever have run on an empty
    # pair of tables, so losing the version identity here is lossless in every reachable
    # state.
    op.drop_index(
        op.f("ix_task_invalidations_task_id"),
        table_name="task_invalidations",
    )
    op.drop_index(
        op.f("uq_task_invalidations_active_task"),
        table_name="task_invalidations",
    )
    op.drop_table("task_invalidations")
    op.drop_index(op.f("ix_tasks_extraction_id"), table_name="tasks")
    op.drop_constraint(
        op.f("fk_tasks_extraction_id_extractions"),
        "tasks",
        type_="foreignkey",
    )
    op.drop_column("tasks", "extraction_id")
    op.drop_constraint(
        op.f("uq_extractions_story_version"),
        "extractions",
        type_="unique",
    )
    op.drop_constraint(
        op.f("ck_extractions_version_number_positive"),
        "extractions",
        type_="check",
    )
    op.drop_column("extractions", "prompt_rendered")
    op.drop_column("extractions", "temperature")
    op.drop_column("extractions", "provider")
    op.drop_column("extractions", "version_number")
