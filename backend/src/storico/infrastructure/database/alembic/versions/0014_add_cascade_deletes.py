"""add ondelete CASCADE/SET NULL to FK constraints for account deletion

Adds CASCADE to:
  - user_stories.project_id → projects.id
  - tasks.user_story_id → user_stories.id
  - extractions.user_story_id → user_stories.id

Adds SET NULL to:
  - projects.created_by → users.id

This enables DELETE /api/v1/users/me to cascade-delete all user data
(projects → user_stories → tasks & extractions) without FK violations.

Revision ID: 0014
Revises: 0013
Create Date: 2026-07-17
"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0014"
down_revision: Union[str, None] = "0013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- user_stories.project_id → projects.id (ondelete CASCADE) ---
    op.drop_constraint(
        op.f("fk_user_stories_project_id_projects"),
        "user_stories",
        type_="foreignkey",
    )
    op.create_foreign_key(
        op.f("fk_user_stories_project_id_projects"),
        "user_stories",
        "projects",
        ["project_id"],
        ["id"],
        ondelete="CASCADE",
    )

    # --- tasks.user_story_id → user_stories.id (ondelete CASCADE) ---
    op.drop_constraint(
        op.f("fk_tasks_user_story_id_user_stories"),
        "tasks",
        type_="foreignkey",
    )
    op.create_foreign_key(
        op.f("fk_tasks_user_story_id_user_stories"),
        "tasks",
        "user_stories",
        ["user_story_id"],
        ["id"],
        ondelete="CASCADE",
    )

    # --- extractions.user_story_id → user_stories.id (ondelete CASCADE) ---
    op.drop_constraint(
        op.f("fk_extractions_user_story_id_user_stories"),
        "extractions",
        type_="foreignkey",
    )
    op.create_foreign_key(
        op.f("fk_extractions_user_story_id_user_stories"),
        "extractions",
        "user_stories",
        ["user_story_id"],
        ["id"],
        ondelete="CASCADE",
    )

    # --- projects.created_by → users.id (ondelete SET NULL) ---
    op.drop_constraint(
        op.f("fk_projects_created_by_users"),
        "projects",
        type_="foreignkey",
    )
    op.create_foreign_key(
        op.f("fk_projects_created_by_users"),
        "projects",
        "users",
        ["created_by"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    # Reverse: recreate FKs without ondelete

    # --- projects.created_by → users.id (no ondelete) ---
    op.drop_constraint(
        op.f("fk_projects_created_by_users"),
        "projects",
        type_="foreignkey",
    )
    op.create_foreign_key(
        op.f("fk_projects_created_by_users"),
        "projects",
        "users",
        ["created_by"],
        ["id"],
    )

    # --- extractions.user_story_id → user_stories.id (no ondelete) ---
    op.drop_constraint(
        op.f("fk_extractions_user_story_id_user_stories"),
        "extractions",
        type_="foreignkey",
    )
    op.create_foreign_key(
        op.f("fk_extractions_user_story_id_user_stories"),
        "extractions",
        "user_stories",
        ["user_story_id"],
        ["id"],
    )

    # --- tasks.user_story_id → user_stories.id (no ondelete) ---
    op.drop_constraint(
        op.f("fk_tasks_user_story_id_user_stories"),
        "tasks",
        type_="foreignkey",
    )
    op.create_foreign_key(
        op.f("fk_tasks_user_story_id_user_stories"),
        "tasks",
        "user_stories",
        ["user_story_id"],
        ["id"],
    )

    # --- user_stories.project_id → projects.id (no ondelete) ---
    op.drop_constraint(
        op.f("fk_user_stories_project_id_projects"),
        "user_stories",
        type_="foreignkey",
    )
    op.create_foreign_key(
        op.f("fk_user_stories_project_id_projects"),
        "user_stories",
        "projects",
        ["project_id"],
        ["id"],
    )
