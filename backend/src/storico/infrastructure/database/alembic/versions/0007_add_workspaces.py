"""add workspaces, workspace_members, workspace_llm_configs, workspace_prompts tables
and migrate projects from owner_id to workspace_id

Revision ID: 0007
Revises: 0006
Create Date: 2026-07-13 18:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0007"
down_revision: Union[str, None] = "0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- workspaces ---
    op.create_table(
        "workspaces",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("slug", sa.String(100), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_workspaces")),
        sa.ForeignKeyConstraint(
            ["owner_id"], ["users.id"],
            name=op.f("fk_workspaces_owner_id_users"),
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("slug", name=op.f("uq_workspaces_slug")),
    )

    # --- workspace_members ---
    op.create_table(
        "workspace_members",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_workspace_members")),
        sa.ForeignKeyConstraint(
            ["workspace_id"], ["workspaces.id"],
            name=op.f("fk_workspace_members_workspace_id_workspaces"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"],
            name=op.f("fk_workspace_members_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "workspace_id", "user_id",
            name=op.f("uq_workspace_members_workspace_id_user_id"),
        ),
    )

    # --- workspace_llm_configs ---
    op.create_table(
        "workspace_llm_configs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.String(50), nullable=False),
        sa.Column("model", sa.String(100), nullable=True),
        sa.Column("temperature", sa.Float(), nullable=True),
        sa.Column("max_tokens", sa.Integer(), nullable=True),
        sa.Column("base_url", sa.String(500), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_workspace_llm_configs")),
        sa.ForeignKeyConstraint(
            ["workspace_id"], ["workspaces.id"],
            name=op.f("fk_workspace_llm_configs_workspace_id_workspaces"),
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "workspace_id",
            name=op.f("uq_workspace_llm_configs_workspace_id"),
        ),
    )

    # --- workspace_prompts ---
    op.create_table(
        "workspace_prompts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("system_prompt", sa.Text(), nullable=True),
        sa.Column("instruction_template", sa.Text(), nullable=True),
        sa.Column("few_shot_examples", sa.JSON(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_workspace_prompts")),
        sa.ForeignKeyConstraint(
            ["workspace_id"], ["workspaces.id"],
            name=op.f("fk_workspace_prompts_workspace_id_workspaces"),
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "workspace_id",
            name=op.f("uq_workspace_prompts_workspace_id"),
        ),
    )

    # --- migrate projects: drop owner_id, add workspace_id and created_by ---
    op.drop_constraint(
        op.f("fk_projects_owner_id_users"), "projects", type_="foreignkey",
    )
    op.drop_column("projects", "owner_id")
    op.add_column(
        "projects",
        sa.Column(
            "workspace_id", sa.Uuid(),
            nullable=True,  # nullable during migration — existing rows have no workspace
        ),
    )
    op.add_column(
        "projects",
        sa.Column(
            "created_by", sa.Uuid(),
            nullable=True,
        ),
    )
    # Add FK constraints — server_default is kept so that NOT NULL is accepted.
    op.create_foreign_key(
        op.f("fk_projects_workspace_id_workspaces"),
        "projects", "workspaces",
        ["workspace_id"], ["id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        op.f("fk_projects_created_by_users"),
        "projects", "users",
        ["created_by"], ["id"],
    )


def downgrade() -> None:
    # --- reverse projects migration ---
    op.drop_constraint(
        op.f("fk_projects_created_by_users"), "projects", type_="foreignkey",
    )
    op.drop_constraint(
        op.f("fk_projects_workspace_id_workspaces"), "projects", type_="foreignkey",
    )
    op.drop_column("projects", "created_by")
    op.drop_column("projects", "workspace_id")
    op.add_column(
        "projects",
        sa.Column(
            "owner_id", sa.Uuid(),
            nullable=True,  # Must be nullable — data was lost
        ),
    )
    op.create_foreign_key(
        op.f("fk_projects_owner_id_users"),
        "projects", "users",
        ["owner_id"], ["id"],
    )

    # --- drop new tables (reverse order for FK integrity) ---
    op.drop_table("workspace_prompts")
    op.drop_table("workspace_llm_configs")
    op.drop_table("workspace_members")
    op.drop_table("workspaces")
