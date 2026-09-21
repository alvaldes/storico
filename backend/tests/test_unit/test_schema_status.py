"""Tests for ``schema_status`` — the comparison between the code's Alembic head and the database's.

The health routes can only make a code/schema mismatch loud if this module can see one, so these
tests pin the three answers it may give and the one it must never give by accident: ``unknown`` is
not ``ok``.

Two of them carry more weight than the rest. ``test_expected_head_matches_the_chain`` recomputes the
head from the migration files with a second, independent reading — a value echoed back through
Alembic would prove nothing about a claim that rests on Alembic. And
``test_a_failed_probe_leaves_the_connection_usable`` covers the behaviour that makes a careless
probe worse than no probe: on Postgres a failed statement aborts the surrounding transaction, and a
connection returned to the pool in that state fails every later caller. SQLite cannot reproduce the
abort, so that test covers the half it can — the failure does not escape, and the same connection
still answers afterwards.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from pathlib import Path

import pytest
import sqlalchemy as sa
from sqlalchemy import insert, literal, select
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from storico.infrastructure.database import schema_status

# The migration files are the only source of truth for the chain, so the independent reading parses
# them directly instead of asking Alembic what it built out of them.
_REVISION = re.compile(r'^revision(?:\s*:\s*[^=]+)?\s*=\s*"([^"]+)"', re.MULTILINE)
_PARENT = re.compile(r'^down_revision(?:\s*:\s*[^=]+)?\s*=\s*"([^"]+)"', re.MULTILINE)


def _versions_dir() -> Path:
    return Path(schema_status.__file__).resolve().parent / "alembic" / "versions"


def _head_from_the_migration_files() -> str:
    """The chain's head, read from ``revision`` / ``down_revision`` without Alembic.

    The head is the revision no other script declares as its parent. Deliberately a second
    implementation: it can disagree with ``ScriptDirectory``, and that disagreement is the only
    thing that makes comparing the two meaningful.
    """
    declared: set[str] = set()
    parents: set[str] = set()
    for script in _versions_dir().glob("*.py"):
        source = script.read_text(encoding="utf-8")
        declared.update(_REVISION.findall(source))
        parents.update(_PARENT.findall(source))

    heads = declared - parents
    assert len(heads) == 1, f"the chain should have exactly one head, found {sorted(heads)}"
    return heads.pop()


@pytest.fixture(autouse=True)
def _cold_expected_head_cache() -> Iterator[None]:
    """Every test starts and ends with the expected head uncached.

    The cache is module state: one test caching ``None`` for a script location another test has
    monkeypatched away would make the order of this file matter.
    """
    schema_status.clear_expected_head_cache()
    yield
    schema_status.clear_expected_head_cache()


def _alembic_version_table() -> sa.Table:
    """The single-row bookkeeping table Alembic keeps, declared rather than hand-written in SQL."""
    return sa.Table(
        "alembic_version",
        sa.MetaData(),
        sa.Column("version_num", sa.String(32), nullable=False),
    )


async def _engine(revision: str | None) -> AsyncEngine:
    """A scratch database whose ``alembic_version`` holds ``revision``.

    ``None`` leaves the table out — a database nobody has migrated. ``""`` leaves it present and
    empty, which is the other way the revision is missing.
    """
    engine = create_async_engine("sqlite+aiosqlite://")
    if revision is not None:
        table = _alembic_version_table()
        async with engine.begin() as conn:
            await conn.run_sync(table.metadata.create_all)
            if revision:
                await conn.execute(insert(table).values(version_num=revision))
    return engine


@pytest.mark.asyncio
async def test_expected_head_matches_the_chain() -> None:
    """The cached head is the chain's head, checked against a reading Alembic did not produce."""
    assert schema_status.get_expected_head() == _head_from_the_migration_files()


@pytest.mark.asyncio
async def test_expected_head_is_read_once_and_can_be_forgotten(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Parsing every migration script belongs on a cold start, not on every health request."""
    reads = 0

    def counting_read() -> str:
        nonlocal reads
        reads += 1
        return "0024"

    monkeypatch.setattr(schema_status, "_read_expected_head", counting_read)

    assert schema_status.get_expected_head() == "0024"
    assert schema_status.get_expected_head() == "0024"
    assert reads == 1, "the scripts were parsed more than once for repeated calls"

    schema_status.clear_expected_head_cache()

    assert schema_status.get_expected_head() == "0024"
    assert reads == 2, "clearing the cache did not force a fresh read"


@pytest.mark.asyncio
async def test_an_unreadable_script_location_is_unknown_never_ok(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A probe that cannot compute the head has not found agreement; it has found nothing."""
    monkeypatch.setattr(
        schema_status, "_ALEMBIC_SCRIPT_LOCATION", Path("/nonexistent/alembic/scripts")
    )
    engine = await _engine("0024")
    try:
        result = await schema_status.probe_schema_status(engine)
    finally:
        await engine.dispose()

    assert schema_status.get_expected_head() is None
    assert result.status == "unknown"
    assert result.expected_revision is None
    assert result.actual_revision == "0024", "the database's own revision was still readable"


@pytest.mark.asyncio
async def test_a_database_at_the_code_head_is_ok() -> None:
    """The one answer that means the code and the schema agree."""
    head = schema_status.get_expected_head()
    assert head is not None

    engine = await _engine(head)
    try:
        result = await schema_status.probe_schema_status(engine)
    finally:
        await engine.dispose()

    assert result.status == "ok"
    assert result.expected_revision == head
    assert result.actual_revision == head


@pytest.mark.asyncio
@pytest.mark.parametrize("revision", ["0001", "9999"])
async def test_a_database_at_another_revision_is_drift(revision: str) -> None:
    """Behind and ahead are the same answer here: the code and the schema disagree."""
    engine = await _engine(revision)
    try:
        result = await schema_status.probe_schema_status(engine)
    finally:
        await engine.dispose()

    assert result.status == "drift"
    assert result.actual_revision == revision
    assert result.expected_revision is not None
    assert result.expected_revision != revision


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "revision",
    [pytest.param(None, id="table-absent"), pytest.param("", id="table-empty")],
)
async def test_a_missing_revision_is_unknown(revision: str | None) -> None:
    """Fail closed: a database nobody has migrated must not read as healthy."""
    engine = await _engine(revision)
    try:
        actual = await schema_status.read_actual_revision(engine)
        result = await schema_status.probe_schema_status(engine)
    finally:
        await engine.dispose()

    assert actual is None
    assert result.status == "unknown"
    assert result.actual_revision is None


@pytest.mark.asyncio
async def test_read_actual_revision_returns_the_stored_row() -> None:
    """The SQL itself, against a table that holds a value — not a mocked cursor."""
    engine = await _engine("0021")
    try:
        assert await schema_status.read_actual_revision(engine) == "0021"
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_a_probe_that_cannot_open_a_connection_is_unknown() -> None:
    """The third way to learn nothing, and still not ``ok``."""
    engine = create_async_engine("sqlite+aiosqlite:///nonexistent-directory/storico.db")
    try:
        result = await schema_status.probe_schema_status(engine)
    finally:
        await engine.dispose()

    assert result.status == "unknown"
    assert result.actual_revision is None


@pytest.mark.asyncio
async def test_a_failed_probe_leaves_the_connection_usable() -> None:
    """The query fails; the connection must not fail with it."""
    engine = await _engine(None)
    try:
        assert (await schema_status.probe_schema_status(engine)).status == "unknown"

        async with engine.connect() as conn:
            value = (await conn.execute(select(literal(1)))).scalar_one()
    finally:
        await engine.dispose()

    assert value == 1
