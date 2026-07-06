"""Engine and session factory for async SQLAlchemy."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from storico.config.settings import Settings

_engine: AsyncEngine | None = None


def get_engine(db_url: str | None = None) -> AsyncEngine:
    """Return the module-level async engine, creating it lazily if needed."""
    global _engine
    if _engine is None:
        url = db_url or Settings.load().database_url
        _engine = create_async_engine(
            url, echo=False, pool_size=5, max_overflow=10
        )
    return _engine


def create_session_factory(
    engine: AsyncEngine | None = None,
) -> async_sessionmaker[AsyncSession]:
    """Create a new session factory bound to the given or default engine."""
    return async_sessionmaker(
        bind=engine or get_engine(),
        class_=AsyncSession,
        expire_on_commit=False,
    )


def dispose_engine() -> None:
    """Dispose the module-level engine and reset it to None."""
    global _engine
    if _engine is not None:
        _engine.sync_engine.dispose()
        _engine = None
