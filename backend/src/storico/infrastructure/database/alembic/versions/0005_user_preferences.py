"""create user_preferences table

Revision ID: 0005
Revises: 0004
Create Date: 2026-07-11 22:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "user_preferences",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column(
            "preferences",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
    )
    op.create_foreign_key(
        op.f("fk_user_preferences_user_id_users"),
        "user_preferences",
        "users",
        ["user_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_primary_key(
        op.f("pk_user_preferences"),
        "user_preferences",
        ["user_id"],
    )


def downgrade() -> None:
    op.drop_table("user_preferences")
