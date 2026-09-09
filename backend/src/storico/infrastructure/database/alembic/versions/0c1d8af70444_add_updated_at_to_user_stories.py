"""add updated_at to user_stories

Revision ID: 0c1d8af70444
Revises: 0018
Create Date: 2026-09-09 11:47:11.715043
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '0c1d8af70444'
down_revision: Union[str, None] = '0018'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add updated_at column to user_stories
    op.add_column('user_stories', sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()))


def downgrade() -> None:
    # Remove updated_at column from user_stories
    op.drop_column('user_stories', 'updated_at')
