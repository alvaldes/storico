"""pytest fixtures for Storico backend tests."""

from collections.abc import AsyncGenerator

import jwt as pyjwt
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
from storico.domain.entities.user import User
from storico.infrastructure.cache.user_cache import _reset_user_cache
from storico.infrastructure.database.models import Base
from storico.infrastructure.database.repositories import SQLAlchemyUserRepository
from storico.infrastructure.database.session import get_session

TEST_DATABASE_URL = "sqlite+aiosqlite://"


@pytest.fixture(autouse=True)
def _reset_cached_user() -> None:
    """Wipe the in-process authenticated-user cache before each test.

    The ``get_current_user`` dependency caches the authenticated user for
    30s to skip the ``find_by_id`` round-trip on repeated requests. Many
    tests authenticate as the same ``authed_user`` via the JWT fixture; a
    cached entry from test N must not satisfy test N+1 (which may have
    mutated or deleted the user). Per-test reset keeps suites isolated.
    """
    _reset_user_cache()


def make_jwt_headers(user_id: str) -> dict:
    """Generate JWT Authorization headers for a given user ID.

    Mirrors the proven pattern from ``test_export.py``.
    """
    from storico.config.settings import Settings

    secret = Settings.load().auth_jwt_secret
    token = pyjwt.encode({"sub": user_id}, secret, algorithm="HS256")
    return {"Authorization": f"Bearer {token}"}


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


@pytest_asyncio.fixture
async def authed_user(db_session: AsyncSession) -> User:
    """Create and return a user authenticated via JWT for testing."""
    repo = SQLAlchemyUserRepository(db_session)
    user = User(email="authed@test.com", name="Authed Test")
    saved = await repo.save(user)
    await repo.link_account(saved.id, "google", "g-authed-test")
    return saved


@pytest_asyncio.fixture
async def authed_client(
    authed_user: User, async_client: AsyncClient
) -> AsyncClient:
    """Return an async client pre-authenticated as ``authed_user`` via JWT."""
    token = make_jwt_headers(str(authed_user.id))["Authorization"]
    async_client.headers.update({"Authorization": token})
    return async_client
