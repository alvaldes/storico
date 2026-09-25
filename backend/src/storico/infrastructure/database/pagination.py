"""Shared paging helper: one statement that carries both a page and its total.

The dev database is a pooler where one statement costs ~2s, so a paginated
list may not issue a separate ``SELECT COUNT(*)`` next to its page query.
The total rides on the rows' own statement as ``count(*) OVER ()``: the
window function is evaluated over the whole filtered set before
``LIMIT``/``OFFSET``, which is exactly the ``len()`` the caller used to
compute in Python over a full fetch.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import Select, func
from sqlalchemy.engine import Row
from sqlalchemy.ext.asyncio import AsyncSession

__all__ = ["fetch_page", "with_total"]


def with_total(stmt: Select[Any]) -> Select[Any]:
    """Append ``count(*) OVER () AS total`` so a page carries its own total.

    The window function is evaluated after ``WHERE``/``GROUP BY`` but before
    ``LIMIT``/``OFFSET``, so every row of the page reports how many rows the
    statement would return without paging.
    """
    return stmt.add_columns(func.count().over().label("total"))


async def fetch_page(
    session: AsyncSession,
    stmt: Select[Any],
    count_stmt: Select[Any],
    *,
    limit: int,
    offset: int,
) -> tuple[list[Row[Any]], int]:
    """Return ``(rows, total)``. ``rows`` keep the total as their last column.

    Applies ``limit``/``offset`` to ``stmt`` and executes it once. When the page
    is non-empty, the total is the window count carried on the first row
    (``rows[0][-1]``) — no second statement is issued.

    A page past the end returns zero rows, so there is no row for the total to
    travel on. That is the one case where ``count_stmt`` runs, and it exists so
    callers still learn the real total instead of misreading a page-count of
    zero. At ``offset == 0`` an empty result already means zero matching rows,
    so the fallback is skipped and not even asked.
    """
    result = await session.execute(stmt.limit(limit).offset(offset))
    rows: list[Row[Any]] = list(result.all())
    if rows:
        return rows, rows[0][-1]
    if offset == 0:
        return [], 0
    count_result = await session.execute(count_stmt)
    return [], int(count_result.scalar_one())
