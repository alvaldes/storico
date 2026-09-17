"""uuid v7 switchover marker (no DDL)

Empty migration: NO column changes are required because none of the PK columns
across the schema carry a `server_default` — every primary key UUID is generated
Python-side in the ORM layer (SQLAlchemy `default=`) or the domain layer
(dataclass `default_factory=`). The v4 -> v7 switchover is therefore a pure
application-code change.

This migration exists ONLY as an audit-trail marker. Applying it advances the
alembic_version pointer from 0014 to 0015, recording in the deploy history the
date on which new rows started receiving UUIDv7 primary keys. Existing rows
retain their pre-existing UUIDv4 values; only NEW rows generated after this
revision's deployment receive v7 IDs.

For rationale (B-tree friendliness, sequenced inserts, RFC 9562), see the SDD
proposal at engram topic `sdd/uuid-v7-migration/proposal` and spec at
`sdd/uuid-v7-migration/spec`.

Revision ID: 0015
Revises: 0014
Create Date: 2026-07-23
"""

from collections.abc import Sequence

revision: str = "0015"
down_revision: str | None = "0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Intentionally empty. See module docstring for rationale.
    pass


def downgrade() -> None:
    # Intentionally empty. Downgrading the pointer does NOT regenerate v4 IDs
    # for rows already created with v7; this is a forward-only audit marker.
    pass
