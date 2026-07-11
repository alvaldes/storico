"""create user_accounts table and migrate auth data

Revision ID: 0004
Revises: 3fefad99b84d
Create Date: 2026-07-11 10:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0004'
down_revision: Union[str, None] = '3fefad99b84d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Create user_accounts table
    op.create_table('user_accounts',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('user_id', sa.Uuid(), nullable=False),
        sa.Column('provider', sa.String(50), nullable=False),
        sa.Column('provider_id', sa.String(255), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    )

    # 2. Migrate existing data from users table
    op.execute("""
        INSERT INTO user_accounts (id, user_id, provider, provider_id, created_at)
        SELECT gen_random_uuid(), id, auth_provider, auth_id, created_at
        FROM users
        WHERE auth_provider IS NOT NULL AND auth_id IS NOT NULL
    """)

    # 3. Add FK and UNIQUE after data is in place
    op.create_foreign_key(
        op.f('fk_user_accounts_user_id_users'),
        'user_accounts', 'users',
        ['user_id'], ['id'],
        ondelete='CASCADE',
    )
    op.create_unique_constraint(
        op.f('uq_user_accounts_provider_provider_id'),
        'user_accounts', ['provider', 'provider_id'],
    )

    # 4. Drop old columns and constraint from users
    op.drop_constraint(
        op.f('uq_users_auth_provider_auth_id'), 'users', type_='unique',
    )
    op.drop_column('users', 'auth_provider')
    op.drop_column('users', 'auth_id')


def downgrade() -> None:
    # 1. Restore columns
    op.add_column('users', sa.Column('auth_provider', sa.String(50), nullable=True))
    op.add_column('users', sa.Column('auth_id', sa.String(255), nullable=True))
    op.create_unique_constraint(
        op.f('uq_users_auth_provider_auth_id'),
        'users', ['auth_provider', 'auth_id'],
    )

    # 2. Restore data from user_accounts
    op.execute("""
        UPDATE users SET
            auth_provider = ua.provider,
            auth_id = ua.provider_id
        FROM user_accounts ua
        WHERE ua.user_id = users.id
    """)

    # 3. Make columns NOT NULL after data restored
    op.execute("ALTER TABLE users ALTER COLUMN auth_provider SET NOT NULL")
    op.execute("ALTER TABLE users ALTER COLUMN auth_id SET NOT NULL")

    # 4. Drop user_accounts constraints and table
    op.drop_constraint(
        op.f('uq_user_accounts_provider_provider_id'),
        'user_accounts', type_='unique',
    )
    op.drop_constraint(
        op.f('fk_user_accounts_user_id_users'),
        'user_accounts', type_='foreignkey',
    )
    op.drop_table('user_accounts')
