"""Engine and session factory for async SQLAlchemy."""

from __future__ import annotations

from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from storico.config.settings import Settings

_engine: AsyncEngine | None = None


def _normalize_db_url(url: str) -> str:
    """Convert psycopg2-style params to asyncpg-compatible format.

    asyncpg does not accept ``?sslmode=require`` (that is a psycopg2
    parameter).  Neon / cloud databases require TLS, which asyncpg expects
    as ``?ssl=require``.  Also strip other psycopg2-only parameters.
    """
    parsed = urlparse(url.replace("+asyncpg", "", 1))  # strip scheme suffix
    qs = parse_qs(parsed.query, keep_blank_values=True)

    # sslmode → ssl (asyncpg equivalent)
    if "sslmode" in qs:
        qs["ssl"] = qs.pop("sslmode")

    # Strip psycopg2-only params that asyncpg would choke on
    for key in ("gssencmode", "target_session_attrs"):
        qs.pop(key, None)

    new_query = urlencode(qs, doseq=True)
    new_netloc = parsed.hostname or ""
    if parsed.port:
        new_netloc = f"{new_netloc}:{parsed.port}"
    if parsed.username:
        auth = parsed.password or ""
        if auth:
            new_netloc = f"{parsed.username}:{auth}@{new_netloc}"
        else:
            new_netloc = f"{parsed.username}@{new_netloc}"
    new = urlunparse(("postgresql+asyncpg", new_netloc, parsed.path,
                       parsed.params, new_query, parsed.fragment))
    return new


def get_engine(db_url: str | None = None) -> AsyncEngine:
    """Return the module-level async engine, creating it lazily if needed."""
    global _engine
    if _engine is None:
        url = _normalize_db_url(db_url or Settings.load().database_url)
        _engine = create_async_engine(
            url,
            echo=False,
            pool_size=1,
            max_overflow=2,
            pool_timeout=10,
            pool_pre_ping=True,  # verify connections before use (Neon drops idle conns)
            connect_args={"timeout": 10},
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
