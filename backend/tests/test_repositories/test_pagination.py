"""Tests for the pagination helper (``with_total`` / ``fetch_page``).

The dev database is a pooler where one statement costs ~2s, so a page's total
must ride on the rows' own statement (``count(*) OVER ()``) instead of a
separate ``SELECT COUNT(*)``. ``fetch_page`` falls back to a real ``COUNT``
only when a past-the-end page returns no row for the total to travel on, and
never falls back at ``offset == 0`` — an empty first page already means zero
matching rows.

Statement counts are taken from the engine with the ``before_cursor_execute``
listener pattern (``ReadsOf``) rather than by mocking the session, because the
property under test is how many statements the database actually receives.
"""

from __future__ import annotations

from typing import Any

import pytest
import pytest_asyncio
from sqlalchemy import Column, Integer, MetaData, Select, String, Table, func, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from storico.infrastructure.database.pagination import fetch_page, with_total
from tests.test_api.test_unfiltered_list_queries import ReadsOf

metadata = MetaData()
items = Table(
    "pagination_helper_items",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("name", String(32)),
    Column("position", Integer),
)


@pytest_asyncio.fixture
async def items_table(test_engine: AsyncEngine) -> None:
    """Create the throwaway table on this test's fresh in-memory engine."""
    async with test_engine.begin() as conn:
        await conn.run_sync(metadata.create_all)


async def _seed(session: AsyncSession, count: int) -> None:
    """Insert ``count`` rows whose ``position`` matches their insertion order."""
    await session.execute(
        items.insert(),
        [{"id": i, "name": f"item-{i}", "position": i} for i in range(1, count + 1)],
    )
    await session.commit()


def _page_stmt() -> Select[Any]:
    """The page statement every test uses: deterministic order, total attached."""
    return with_total(select(items).order_by(items.c.position))


def _count_stmt() -> Select[Any]:
    """The fallback COUNT for the same rows."""
    return select(func.count()).select_from(items)


async def test_with_total_appends_a_labelled_window_count() -> None:
    """with_total appends a ``total`` column rendered as ``count(*) OVER ()``."""
    stmt: Select[Any] = select(items).order_by(items.c.position)
    total_stmt = with_total(stmt)

    assert "total" in total_stmt.selected_columns
    rendered = str(total_stmt.compile())
    assert "count(*) OVER ()" in rendered


@pytest.mark.asyncio
async def test_fetch_page_returns_full_total_on_a_mid_page(
    db_session: AsyncSession, items_table: None
) -> None:
    """A mid page reports the full total, not the page size."""
    await _seed(db_session, 5)

    rows, total = await fetch_page(db_session, _page_stmt(), _count_stmt(), limit=2, offset=2)

    assert total == 5
    assert len(rows) == 2
    assert [row.position for row in rows] == [3, 4]


@pytest.mark.asyncio
async def test_fetch_page_past_the_end_falls_back_to_a_real_count(
    test_engine: AsyncEngine, db_session: AsyncSession, items_table: None
) -> None:
    """A page past the end returns no rows but the real total, via count_stmt."""
    await _seed(db_session, 5)

    with ReadsOf(test_engine, "pagination_helper_items") as reads:
        rows, total = await fetch_page(db_session, _page_stmt(), _count_stmt(), limit=2, offset=10)

    assert rows == []
    assert total == 5
    # The fallback actually asked the database: exactly one COUNT (no LIMIT) ran.
    assert len(reads.statements) == 2, reads.statements
    assert all("LIMIT" not in statement for statement in reads.statements[1:])


@pytest.mark.asyncio
async def test_fetch_page_empty_at_offset_zero_skips_the_count(
    test_engine: AsyncEngine, db_session: AsyncSession, items_table: None
) -> None:
    """An empty first page means zero matching rows, so count_stmt is not run."""
    await _seed(db_session, 5)
    empty_stmt = with_total(select(items).where(items.c.position > 100).order_by(items.c.position))
    empty_count = select(func.count()).select_from(items).where(items.c.position > 100)

    with ReadsOf(test_engine, "pagination_helper_items") as reads:
        rows, total = await fetch_page(db_session, empty_stmt, empty_count, limit=2, offset=0)

    assert rows == []
    assert total == 0
    # Only the page statement ran — no COUNT, not even for zero rows.
    assert len(reads.statements) == 1, reads.statements
    assert "LIMIT" in reads.statements[0]


@pytest.mark.asyncio
async def test_fetch_pages_are_disjoint_and_cover_every_row_once(
    db_session: AsyncSession, items_table: None
) -> None:
    """Consecutive pages never overlap and together hold every row exactly once."""
    await _seed(db_session, 4)

    page1, total1 = await fetch_page(db_session, _page_stmt(), _count_stmt(), limit=2, offset=0)
    page2, total2 = await fetch_page(db_session, _page_stmt(), _count_stmt(), limit=2, offset=2)

    ids1 = [row.id for row in page1]
    ids2 = [row.id for row in page2]
    assert ids1 == [1, 2]
    assert ids2 == [3, 4]
    assert sorted([*ids1, *ids2]) == [1, 2, 3, 4]
    assert total1 == total2 == 4
