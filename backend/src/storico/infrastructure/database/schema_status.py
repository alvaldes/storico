"""Compare the code's Alembic head with the database's revision.

On 2026-09-20 production ran code at head ``0024`` against a schema at ``0021`` for a day: the ORM
selected ``extractions.completed_at``, the column did not exist, and 56 extractions failed. Nothing
in the system could have said so. ``/api/v1/health`` probes ``SELECT 1``, which passes against any
schema, and no code under ``backend/src/`` read ``alembic_version`` at all.

This module answers the question that was missing — do the code and the schema agree? — with three
values rather than two:

``ok``
    The database's revision equals the head the packaged migration scripts declare.
``drift``
    They differ. The direction is deliberately not reported: readiness fails closed either way, and
    telling "the schema is behind" from "the code is behind" needs a declared order per revision,
    which this repository does not have yet.
``unknown``
    The question could not be answered — the scripts could not be read, the table is absent, the
    query failed. ``unknown`` must never collapse into ``ok``: a database nobody has migrated is
    exactly what a readiness gate exists to catch.

The revisions themselves travel in the returned value object for the log. They never reach a
response body: the health routes are unauthenticated and publish a status, not a diagnosis (see
``api/routes/health.py``).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import sqlalchemy as sa
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine

from storico.infrastructure.database.base import get_engine

logger = logging.getLogger(__name__)

SchemaStatusValue = Literal["ok", "drift", "unknown"]

# The migration scripts sit next to this module, and the location is resolved from ``__file__`` so
# it never depends on the working directory. Not from ``alembic.ini`` either: the production image
# installs the package and copies ``src/`` (``backend/Dockerfile``), and contains no
# ``alembic.ini`` at all.
_ALEMBIC_SCRIPT_LOCATION = Path(__file__).resolve().parent / "alembic"

# Alembic owns this table and creates it when the first revision runs; the one column it stores is
# the whole of the contract read here. Declared rather than hand-written as SQL, because a table
# declaration cannot smuggle a caller's input into a statement the way a composed string can.
_ALEMBIC_VERSION = sa.Table(
    "alembic_version",
    sa.MetaData(),
    sa.Column("version_num", sa.String(32), nullable=False),
)

# ``None`` is a real cached value — "the scripts could not be read" — so the cache needs its own
# empty flag rather than reusing ``None``.
_expected_head: str | None = None
_expected_head_cached = False


@dataclass(frozen=True, slots=True)
class SchemaStatus:
    """The comparison's three-way result.

    ``expected_revision`` and ``actual_revision`` exist for the log. HTTP publishes only ``status``,
    so a caller that needs the revisions must not be one of the unauthenticated routes.
    """

    status: SchemaStatusValue
    expected_revision: str | None
    actual_revision: str | None


def clear_expected_head_cache() -> None:
    """Forget the cached expected head, so the next read parses the scripts again.

    The cache is the point — reading and parsing two dozen migration scripts is disk I/O that does
    not belong on a health request. Production never needs to clear it; tests need the way back to a
    cold state.
    """
    global _expected_head, _expected_head_cached
    _expected_head = None
    _expected_head_cached = False


def _read_expected_head() -> str | None:
    """Read the head from the packaged migration scripts. ``None`` when they cannot be read."""
    try:
        config = Config()
        config.set_main_option("script_location", str(_ALEMBIC_SCRIPT_LOCATION))
        return ScriptDirectory.from_config(config).get_current_head()
    except Exception:
        logger.warning(
            "Could not read the Alembic head from %s", _ALEMBIC_SCRIPT_LOCATION, exc_info=True
        )
        return None


def get_expected_head() -> str | None:
    """The head revision the packaged migration scripts declare, read once.

    ``None`` means "could not tell", and every caller must treat it as ``unknown`` rather than
    ``ok``. A failed read is cached too, so an unreadable script directory does not re-parse on
    every request.
    """
    global _expected_head, _expected_head_cached
    if not _expected_head_cached:
        _expected_head = _read_expected_head()
        _expected_head_cached = True
    return _expected_head


async def read_actual_revision(engine: AsyncEngine | None = None) -> str | None:
    """Read ``alembic_version.version_num``. ``None`` when it cannot be read.

    A missing table, a missing row and a failed statement all mean the same thing to the caller —
    the revision is not known — and all three are ``unknown``, never ``ok``.
    """
    try:
        target = engine or get_engine()
        async with target.connect() as conn:
            try:
                result = await conn.execute(select(_ALEMBIC_VERSION.c.version_num))
            except Exception:
                # On Postgres a failed statement aborts the surrounding transaction, and every
                # later statement on that connection fails with "current transaction is aborted"
                # until someone rolls it back. The connection returns to the pool when this block
                # exits, so without this rollback the next caller would inherit the aborted
                # transaction and fail for a reason that has nothing to do with it.
                await conn.rollback()
                raise
            row = result.first()
    except Exception:
        logger.warning("Could not read the schema revision from alembic_version", exc_info=True)
        return None

    if row is None:
        logger.warning("alembic_version holds no row: the database carries no revision")
        return None
    return str(row[0])


async def probe_schema_status(engine: AsyncEngine | None = None) -> SchemaStatus:
    """Compare the code's head with the database's revision.

    ``engine`` is injectable so a caller that already holds one — or a test — does not have to reach
    for the module-level singleton. Absent, ``get_engine()`` supplies it, as everywhere else.
    """
    expected = get_expected_head()
    actual = await read_actual_revision(engine)

    if expected is None or actual is None:
        return SchemaStatus("unknown", expected, actual)
    if expected == actual:
        return SchemaStatus("ok", expected, actual)
    return SchemaStatus("drift", expected, actual)
