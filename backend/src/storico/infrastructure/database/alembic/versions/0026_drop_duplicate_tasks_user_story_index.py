"""drop the duplicate index on tasks.user_story_id

Revision 0001 created ``ix_tasks_user_story_id`` for ``tasks.user_story_id``, and revision
0016 created ``idx_tasks_user_story_id`` for the same column: same table, same column,
same non-unique btree, two names. One of the two is redundant, and the ORM model declares
``ix_tasks_user_story_id`` — 0001's — so this revision drops 0016's copy.

**Deploy order: this revision is order-agnostic**, and saying so is the point — 0022,
0023 and 0024 each carry an ordering instruction, and those docstrings are this
repository's only written record of ordering. Dropping a duplicate index changes no query
result, no constraint and no row: ``ix_tasks_user_story_id`` keeps the column indexed for
the repository's reads and for the ``ON DELETE CASCADE`` path on both sides of the change.
Nothing needs to be deployed before or after it, and no query anywhere names the dropped
index. ``odd/tasks/schema-drift-reconciliation.md`` records why 0016's copy is the one
that goes.

Revision ID: 0026
Revises: 0025
Create Date: 2026-09-21
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0026"
down_revision: str | None = "0025"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE_NAME = "tasks"
_REDUNDANT_INDEX_NAME = "idx_tasks_user_story_id"
_INDEXED_COLUMN = "user_story_id"


def upgrade() -> None:
    """Drop the 0016 copy of the index on ``tasks.user_story_id``.

    0001's ``ix_tasks_user_story_id`` is left untouched: it is the one the model declares, and
    it is the reason this drop costs no query performance.
    """
    op.drop_index(_REDUNDANT_INDEX_NAME, table_name=_TABLE_NAME)


def downgrade() -> None:
    """Recreate the index 0016 created, with 0016's name and definition.

    Recreates a duplicate on purpose: this restores the schema as 0025 left it, which is what a
    downgrade is for. The column is already indexed by 0001's ``ix_tasks_user_story_id``, so the
    recreated copy is redundant immediately — recreating it anyway is what keeps the revision
    sequence reversible, and the redundancy is undone by running this revision's ``upgrade``.
    """
    op.create_index(_REDUNDANT_INDEX_NAME, _TABLE_NAME, [_INDEXED_COLUMN])
