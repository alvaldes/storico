"""UserStoryStatus and TaskStatus enums with data migration

Revision ID: 0016
Revises: 0015
Create Date: 2026-09-03
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ENUM

# revision identifiers, used by Alembic.
revision: str = "0016"
down_revision: str | None = "0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Enum definitions matching spec
USER_STORY_STATUS_ENUM = ENUM(
    "pending_extraction",
    "extracting",
    "extracted",
    "failed_extraction",
    name="user_story_status_new",
    create_type=True,
)

TASK_STATUS_ENUM = ENUM(
    "backlog",
    "todo",
    "in_progress",
    "review",
    "done",
    name="task_status_new",
    create_type=True,
)


def upgrade() -> None:
    # Step 1: Create new enum types
    USER_STORY_STATUS_ENUM.create(op.get_bind(), checkfirst=True)
    TASK_STATUS_ENUM.create(op.get_bind(), checkfirst=True)

    # Step 2: Add temporary columns
    op.add_column("user_stories", sa.Column("status_new", USER_STORY_STATUS_ENUM, nullable=True))
    op.add_column("tasks", sa.Column("status_new", TASK_STATUS_ENUM, nullable=True))

    # Step 3: Data migration - User Stories
    op.execute(
        """
        UPDATE user_stories
        SET status_new = CASE
            WHEN status = 'pending' THEN 'pending_extraction'::user_story_status_new
            WHEN status = 'processing' THEN 'extracting'::user_story_status_new
            WHEN status = 'completed' THEN 'extracted'::user_story_status_new
            WHEN status = 'error' THEN 'failed_extraction'::user_story_status_new
            ELSE 'pending_extraction'::user_story_status_new
        END;
    """
    )

    # Step 4: Data migration - Tasks
    op.execute(
        """
        UPDATE tasks
        SET status_new = CASE
            WHEN status IS NULL THEN 'backlog'::task_status_new
            WHEN status = 'backlog' THEN 'backlog'::task_status_new
            WHEN status = 'todo' THEN 'todo'::task_status_new
            WHEN status = 'in_progress' THEN 'in_progress'::task_status_new
            WHEN status = 'in progress' THEN 'in_progress'::task_status_new
            WHEN status = 'review' THEN 'review'::task_status_new
            WHEN status = 'done' THEN 'done'::task_status_new
            ELSE 'backlog'::task_status_new
        END;
    """
    )

    # Step 5: Verify (optional - separate verification query)
    # SELECT status, status_new, COUNT(*) FROM user_stories GROUP BY status, status_new;
    # SELECT status, status_new, COUNT(*) FROM tasks GROUP BY status, status_new;

    # Step 6: Drop old columns, rename new
    op.drop_column("user_stories", "status")
    op.alter_column("user_stories", "status_new", new_column_name="status", nullable=False)

    op.drop_column("tasks", "status")
    op.alter_column("tasks", "status_new", new_column_name="status", nullable=False)

    # Step 7: Add defaults for future inserts
    op.alter_column("user_stories", "status", server_default="pending_extraction")
    op.alter_column("tasks", "status", server_default="backlog")

    # Step 8: Indexes for query performance
    op.create_index("idx_user_stories_status", "user_stories", ["status"])
    op.create_index("idx_tasks_status", "tasks", ["status"])
    op.create_index("idx_tasks_user_story_id", "tasks", ["user_story_id"])


def downgrade() -> None:
    # Rollback strategy: recreate old VARCHAR columns, map back, drop enums
    op.add_column("user_stories", sa.Column("status_old", sa.String(), nullable=True))
    op.add_column("tasks", sa.Column("status_old", sa.String(), nullable=True))

    op.execute(
        """
        UPDATE user_stories
        SET status_old = CASE
            WHEN status = 'pending_extraction' THEN 'pending'
            WHEN status = 'extracting' THEN 'processing'
            WHEN status = 'extracted' THEN 'completed'
            WHEN status = 'failed_extraction' THEN 'error'
        END;
    """
    )

    op.execute(
        """
        UPDATE tasks
        SET status_old = CASE
            WHEN status = 'backlog' THEN 'backlog'
            WHEN status = 'todo' THEN 'todo'
            WHEN status = 'in_progress' THEN 'in_progress'
            WHEN status = 'review' THEN 'review'
            WHEN status = 'done' THEN 'done'
        END;
    """
    )

    op.drop_column("user_stories", "status")
    op.alter_column("user_stories", "status_old", new_column_name="status")

    op.drop_column("tasks", "status")
    op.alter_column("tasks", "status_old", new_column_name="status")

    # Drop enum types
    USER_STORY_STATUS_ENUM.drop(op.get_bind(), checkfirst=True)
    TASK_STATUS_ENUM.drop(op.get_bind(), checkfirst=True)

    # Drop indexes
    op.drop_index("idx_user_stories_status", "user_stories")
    op.drop_index("idx_tasks_status", "tasks")
    op.drop_index("idx_tasks_user_story_id", "tasks")
