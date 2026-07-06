"""pytest fixtures for Storico backend tests."""

from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from storico.api.app import create_app
from storico.infrastructure.database.models import Base
from storico.infrastructure.database.session import get_session

TEST_DATABASE_URL = "sqlite+aiosqlite://"

# Shared secret used by auth tests — matches the default in Settings.
AUTH_INTERNAL_TOKEN = "dev-insecure-token-change-in-production"


@pytest.fixture
def app():
    """Return a FastAPI application instance."""
    return create_app()


@pytest_asyncio.fixture
async def test_engine() -> AsyncGenerator[AsyncEngine, None]:
    """Create an in-memory SQLite engine with all tables created.

    Shared by ``async_client`` (for route tests) and ``db_session``
    (for repository tests) so that both layers see the same database.
    """
    engine = create_async_engine(TEST_DATABASE_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def async_client(app, test_engine: AsyncEngine):
    """Return an async HTTP client with ``get_session`` overridden to use
    the same in-memory SQLite database as ``test_engine``.

    Each test gets a fresh database — tables are created before the client
    is yielded and disposed after the test completes.
    """
    factory = async_sessionmaker(
        bind=test_engine, class_=AsyncSession, expire_on_commit=False
    )

    # Override the ``get_session`` dependency so routes use the test database.
    async def override_get_session():
        async with factory() as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    # Cleanup
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def db_session(test_engine: AsyncEngine) -> AsyncGenerator[AsyncSession, None]:
    """Return a fresh async session per test, backed by the shared in-memory
    SQLite engine.

    Uses the same engine as ``async_client`` so direct repository calls and
    API-driven operations see the same data.
    """
    factory = async_sessionmaker(
        bind=test_engine, class_=AsyncSession, expire_on_commit=False
    )
    async with factory() as session:
        yield session
