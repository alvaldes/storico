"""convert extractions.status to the extraction_status_new enum

Revision 0018 created the ``extraction_status_new`` enum type and no revision ever
converted the column to it, so ``extractions.status`` has stayed ``VARCHAR(20)`` while
the ORM model has declared the enum since ``f13a587``. This revision closes that gap; it
is the last difference on this column, and ``odd/tasks/schema-drift-reconciliation.md``
records the decision and the evidence behind it.

**The pre-flight check runs before the cast.** The cast fails on any value outside the
enum's three labels (``pending``, ``completed``, ``failed``) with a Postgres cast error,
and — because a revision runs in one transaction — that failure takes the whole upgrade
with it. The check reads the distinct values the column actually holds and raises naming
each stray one, so an operator learns which value is in the way in one readable line
instead of decoding a truncated cast failure in an SSH session. The mitigation lives
here, in the revision, rather than in an operator's memory.

**The default moves in three steps, not one.** 0002 created the column with
``server_default='pending'``, and Postgres will not cast that existing default expression
to the new enum type as part of the type change. So the default is dropped before the
cast and re-set afterwards, this time as the enum's label. Dropping it leaves a window
inside the transaction with no default; nothing can observe that window, because the
whole revision commits or aborts as one.

**Deploy order: this revision is order-agnostic**, and saying so is the point — 0022,
0023 and 0024 each carry an ordering instruction, and those docstrings are this
repository's only written record of ordering. The application writes and compares only
``ExtractionStatus`` members, which are exactly the enum's three labels, and Postgres
accepts those labels as strings against a ``VARCHAR(20)`` column just as it accepts them
against the enum, so the current release and this code both run correctly on either side
of the conversion. The one behavioural difference is ordering: an enum sorts in
declaration order, a ``VARCHAR`` in collation order. Nothing in this repository orders or
range-compares ``extractions.status`` — the only predicate on it is an equality against
``ExtractionStatus.PENDING`` — so no observable behaviour depends on which side is live.

**The enum type is not created here.** 0018 owns it and created it already, which is why
this revision can name it in a cast. Symmetrically, the ``downgrade`` does not drop it:
a revision that dropped another's object would break that other revision's own
``downgrade``.

**The pre-flight check needs a live connection, so this revision cannot be rendered with
``alembic upgrade --sql``.** That is not a new limitation: offline rendering of this chain is
already unavailable, because 0022 and 0024 read and write rows through ``op.get_bind()`` too and
fail the same way (``base:head --sql`` stops at 0022 with an ``AttributeError`` on Alembic's
``MockConnection``). Apply this revision with a real connection, the way the rest of the chain
requires.

Revision ID: 0025
Revises: 0024
Create Date: 2026-09-21
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0025"
down_revision: str | None = "0024"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# The labels ``extraction_status_new`` declares, matching ``ExtractionStatus`` in the domain and
# 0018's own definition. Spelled here rather than imported from the domain enum for the reason
# every migration in this repository spells its own names: a revision has to keep working against
# the schema as it was when the revision was written, after the enum has moved on.
_ALLOWED_STATUSES: tuple[str, ...] = ("pending", "completed", "failed")

# The width 0002 created the column with, and the width the downgrade restores.
_STATUS_VARCHAR_LENGTH = 20

# Named for the cast below. 0018 created this type.
_ENUM_TYPE_NAME = "extraction_status_new"

# The column this revision rewrites, addressed without the ORM model: the model declares the enum
# this revision is producing, so it cannot be used to read the ``VARCHAR`` the revision starts
# from.
_STATUS_COLUMN = sa.table(
    "extractions",
    sa.column("status", sa.String(_STATUS_VARCHAR_LENGTH)),
)


def _stray_statuses() -> list[str]:
    """The distinct values in ``extractions.status`` the enum does not declare.

    A set of values rather than a count, because the error in ``upgrade`` has to *name* the
    offending value: "one row holds a value outside the enum" leaves an operator to find it,
    while naming the value answers the question the failure raises.
    """
    rows = op.get_bind().scalars(sa.select(_STATUS_COLUMN.c.status).distinct()).all()
    return sorted({value for value in rows if value is not None} - set(_ALLOWED_STATUSES))


def upgrade() -> None:
    """Check the stored values, drop the default, convert the column, restore the default.

    The check is first and unconditional, so a database holding a stray value fails before
    anything is altered and this revision can be re-run once the value is dealt with.
    """
    strays = _stray_statuses()
    if strays:
        offending = ", ".join(repr(value) for value in strays)
        allowed = ", ".join(repr(value) for value in _ALLOWED_STATUSES)
        raise RuntimeError(
            f"extractions.status holds value(s) the {_ENUM_TYPE_NAME} enum does not declare: "
            f"{offending}. The column accepts only {allowed}. Nothing has been changed: convert "
            "or delete those rows, then run this migration again."
        )

    # Postgres will not cast 0002's ``server_default='pending'`` expression to the new type as
    # part of the ALTER TYPE below, so the default has to leave and come back.
    op.execute("ALTER TABLE extractions ALTER COLUMN status DROP DEFAULT")
    op.execute(
        "ALTER TABLE extractions ALTER COLUMN status TYPE "
        f"{_ENUM_TYPE_NAME} USING status::{_ENUM_TYPE_NAME}"
    )
    op.execute("ALTER TABLE extractions ALTER COLUMN status SET DEFAULT 'pending'")


def downgrade() -> None:
    """Return the column to ``VARCHAR(20)`` with 0002's default restored.

    The same three steps in reverse, and the default needs the same treatment for the same
    reason: a ``'pending'`` default that Postgres treats as the enum cannot survive being cast
    back to ``VARCHAR`` automatically any more than the ``VARCHAR`` default could survive being
    cast forward.

    ``USING status::text`` cannot fail part-way: every enum label is already valid text, so no
    row can block the narrowing. Values are preserved as they are — a ``pending`` row stays
    ``pending``, and the three labels all fit in ``VARCHAR(20)``.

    The enum type is left in place; 0018 created it and 0018's own ``downgrade`` drops it.
    """
    op.execute("ALTER TABLE extractions ALTER COLUMN status DROP DEFAULT")
    op.execute(
        "ALTER TABLE extractions ALTER COLUMN status TYPE "
        f"VARCHAR({_STATUS_VARCHAR_LENGTH}) USING status::text"
    )
    op.execute("ALTER TABLE extractions ALTER COLUMN status SET DEFAULT 'pending'")
