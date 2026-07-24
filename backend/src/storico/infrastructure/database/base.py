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
_factory: "async_sessionmaker[AsyncSession] | None" = None


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
            pool_size=10,
            max_overflow=20,
            pool_timeout=10,
            pool_pre_ping=False,  # disabled — see commit note: trade-off pre_ping vs pool_recycle
            pool_recycle=1800,  # 30 min — recycle connections before Supabase/Neon idle drops them
            connect_args={"timeout": 10},
        )
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Return the module-level session factory, creating it lazily if needed.

    Caching the factory at module level avoids building a new
    ``async_sessionmaker`` on every request — that allocation has small
    but measurable cost per request in higher-concurrency deployments.
    Binding to the singleton engine via ``get_engine`` keeps the same
    pool semantics callers already had.
    """
    global _factory
    if _factory is None:
        _factory = async_sessionmaker(
            bind=get_engine(),
            class_=AsyncSession,
            expire_on_commit=False,
        )
    return _factory


def create_session_factory(
    engine: AsyncEngine | None = None,
) -> async_sessionmaker[AsyncSession]:
    """Create a NEW session factory bound to the given or default engine.

    Note: callers that want the cached singleton should prefer
    ``get_session_factory``. This function is kept for callers that need
    a factory bound to a different engine (e.g. tests with a dedicated
    in-memory engine, or background tasks that explicitly pass ``engine``).
    The singleton ``get_session_factory`` returns is independent from any
    factory returned here.
    """
    return async_sessionmaker(
        bind=engine or get_engine(),
        class_=AsyncSession,
        expire_on_commit=False,
    )


def dispose_engine() -> None:
    """Dispose the module-level engine and factory and reset both to None.

    Resets the session-factory singleton too so the next request does
    not bind to a disposed engine. Idempotent — safe to call when the
    engine is already None (e.g. during teardown of a process that never
    opened a DB connection).
    """
    global _engine, _factory
    if _engine is not None:
        _engine.sync_engine.dispose()
        _engine = None
    _factory = None
