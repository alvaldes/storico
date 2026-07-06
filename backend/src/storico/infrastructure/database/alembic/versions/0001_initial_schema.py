"""initial_schema

Revision ID: 0001
Revises:
Create Date: 2026-07-05 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # --- users ---
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("auth_provider", sa.String(50), nullable=False),
        sa.Column("auth_id", sa.String(255), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name="pk_users"),
        sa.UniqueConstraint("email", name="uq_users_email"),
        sa.UniqueConstraint(
            "auth_provider", "auth_id", name="uq_users_auth_provider_auth_id"
        ),
    )

    # --- projects ---
    op.create_table(
        "projects",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name="pk_projects"),
        sa.ForeignKeyConstraint(
            ["owner_id"],
            ["users.id"],
            name="fk_projects_owner_id_users",
        ),
    )

    # --- user_stories ---
    op.create_table(
        "user_stories",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("actor", sa.Text(), nullable=False),
        sa.Column("feature", sa.Text(), nullable=False),
        sa.Column("benefit", sa.Text(), nullable=False),
        sa.Column("raw_text", sa.Text(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name="pk_user_stories"),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name="fk_user_stories_project_id_projects",
        ),
    )
    op.create_index(
        "ix_user_stories_project_id", "user_stories", ["project_id"]
    )

    # --- tasks ---
    op.create_table(
        "tasks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_story_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column(
            "description", sa.Text(), nullable=False, server_default=""
        ),
        sa.Column(
            "status",
            sa.String(50),
            nullable=False,
            server_default="backlog",
        ),
        sa.Column(
            "priority",
            sa.String(20),
            nullable=False,
            server_default="medium",
        ),
        sa.Column("labels", sa.JSON(), nullable=True),
        sa.Column("dependencies", sa.JSON(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name="pk_tasks"),
        sa.ForeignKeyConstraint(
            ["user_story_id"],
            ["user_stories.id"],
            name="fk_tasks_user_story_id_user_stories",
        ),
    )
    op.create_index(
        "ix_tasks_user_story_id", "tasks", ["user_story_id"]
    )

    # --- extractions ---
    op.create_table(
        "extractions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_story_id", sa.Uuid(), nullable=False),
        sa.Column("model_used", sa.String(100), nullable=False),
        sa.Column("prompt_config", sa.JSON(), nullable=True),
        sa.Column("raw_response", sa.Text(), nullable=False),
        sa.Column("confidence_score", sa.Float(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name="pk_extractions"),
        sa.ForeignKeyConstraint(
            ["user_story_id"],
            ["user_stories.id"],
            name="fk_extractions_user_story_id_user_stories",
        ),
    )
    op.create_index(
        "ix_extractions_user_story_id", "extractions", ["user_story_id"]
    )


def downgrade() -> None:
    op.drop_table("extractions")
    op.drop_table("tasks")
    op.drop_table("user_stories")
    op.drop_table("projects")
    op.drop_table("users")
