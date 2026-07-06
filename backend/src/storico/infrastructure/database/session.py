"""FastAPI dependency that provides an async database session."""

from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession

from storico.infrastructure.database.base import create_session_factory, get_engine


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency — yields an async session and closes it on teardown.

    Usage::

        from fastapi import Depends
        from sqlalchemy.ext.asyncio import AsyncSession
        from storico.infrastructure.database.session import get_session

        @router.get("/items")
        async def list_items(session: AsyncSession = Depends(get_session)):
            ...
    """
    engine = get_engine()
    factory = create_session_factory(engine)
    async with factory() as session:
        yield session
