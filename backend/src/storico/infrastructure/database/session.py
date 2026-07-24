"""FastAPI dependency that provides an async database session."""

from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession

from storico.infrastructure.database.base import get_session_factory


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency — yields an async session and closes it on teardown.

    Uses the module-level session-factory singleton (``get_session_factory``)
    so the factory itself is allocated once per process instead of once per
    request. Each call still yields its own short-lived ``AsyncSession`` from
    the shared factory — connection pool semantics are unchanged.

    Usage::

        from fastapi import Depends
        from sqlalchemy.ext.asyncio import AsyncSession
        from storico.infrastructure.database.session import get_session

        @router.get("/items")
        async def list_items(session: AsyncSession = Depends(get_session)):
            ...
    """
    factory = get_session_factory()
    async with factory() as session:
        yield session
