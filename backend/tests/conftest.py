"""pytest fixtures for Storico backend tests."""

from collections.abc import AsyncGenerator, Awaitable, Callable
from dataclasses import dataclass
from uuid import UUID, uuid4

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
from storico.domain.entities.project import Project
from storico.domain.entities.user import User
from storico.domain.entities.user_story import UserStory
from storico.domain.entities.workspace_member import WorkspaceMember, WorkspaceRole
from storico.infrastructure.cache.user_cache import _reset_user_cache
from storico.infrastructure.database.models import Base
from storico.infrastructure.database.repositories import (
    SQLAlchemyProjectRepository,
    SQLAlchemyUserRepository,
    SQLAlchemyUserStoryRepository,
)
from storico.infrastructure.database.repositories.workspace_member_repository import (
    SQLAlchemyWorkspaceMemberRepository,
)
from storico.infrastructure.database.session import get_session
from tests._helpers import create_workspace

TEST_DATABASE_URL = "sqlite+aiosqlite://"


@dataclass(frozen=True, slots=True)
class SeededWorkspace:
    """Ids of one seeded ``workspace → project → stories`` chain.

    ``story_ids`` keeps the order the stories were created in; ``story_id`` is
    the convenience accessor for the common single-story chain.
    """

    workspace_id: UUID
    project_id: UUID
    story_ids: tuple[UUID, ...]

    @property
    def story_id(self) -> UUID:
        """Id of the first seeded story."""
        return self.story_ids[0]


QDRANT_LEAK_MESSAGE = (
    "This test tried to build a REAL AsyncQdrantClient. The adapter's lazy client is what "
    "embeds the story against the configured Ollama and upserts a point into "
    "Settings.load().qdrant_collection — the developer's live cluster. Measured: the "
    "default suite grew that collection by exactly one point per full run, each a seeded "
    "'As a user, I want to use seeded feature 0...' story with model_used=''. Patch the "
    "vector store in this test instead: monkeypatch.setattr(extraction_task, "
    "'get_embedding_port', <raiser>) makes run_background_extraction take its existing "
    "'vector store unavailable' branch (vector_store=None), or monkeypatch.setattr("
    "extraction_task, 'QdrantAdapter', lambda **_: None) hands it a null store. When the "
    "live client IS the point of the test, opt out with @pytest.mark.integration."
)


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


@pytest.fixture(autouse=True)
def _forbid_real_qdrant_clients(
    request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Refuse to construct a real Qdrant client in a test that has not opted in.

    This guards the measured leak, not a hypothetical one: ``run_background_extraction``
    builds a real ``QdrantAdapter`` with the configured collection unless its embedding
    factory raises, and the adapter's lazy ``AsyncQdrantClient`` then talks to the live
    cluster. On a machine with no Docker daemon that cluster is the developer's own, so a
    default-suite run wrote real points — one per run, each a seeded
    ``"As a user, I want to use seeded feature 0..."`` story with ``model_used=""``.

    The patch targets the name the adapter actually constructs. It fails through
    ``pytest.fail`` rather than a bare ``AssertionError`` on purpose: the adapter wraps the
    construction in ``except Exception`` (graceful degradation) and
    ``run_background_extraction`` wraps the whole run the same way, so an
    ``AssertionError`` is swallowed and the leak would proceed anyway — a guard that never
    guards. ``pytest.fail`` raises ``Failed``, which is a ``BaseException``, so it reaches
    the test report instead.

    Live tests opt out with ``@pytest.mark.integration`` (the live suite builds its own
    real adapters). A test that mocks ``AsyncQdrantClient`` itself is unaffected: its own
    patch replaces this one, because a test-body ``monkeypatch.setattr`` runs after this
    fixture.
    """
    if request.node.get_closest_marker("integration") is not None:
        return

    def _refuse_real_qdrant_client(*args: object, **kwargs: object) -> None:
        pytest.fail(QDRANT_LEAK_MESSAGE, pytrace=False)

    monkeypatch.setattr(
        "storico.infrastructure.vector.qdrant_adapter.AsyncQdrantClient",
        _refuse_real_qdrant_client,
    )


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
    factory = async_sessionmaker(bind=test_engine, class_=AsyncSession, expire_on_commit=False)

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
    factory = async_sessionmaker(bind=test_engine, class_=AsyncSession, expire_on_commit=False)
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
async def authed_client(authed_user: User, async_client: AsyncClient) -> AsyncClient:
    """Return an async client pre-authenticated as ``authed_user`` via JWT."""
    token = make_jwt_headers(str(authed_user.id))["Authorization"]
    async_client.headers.update({"Authorization": token})
    return async_client


@pytest_asyncio.fixture
async def seed_workspace(
    db_session: AsyncSession, authed_user: User
) -> Callable[..., Awaitable[SeededWorkspace]]:
    """Return a factory that seeds a workspace chain its caller can access.

    Why this exists: the ``/api/v1/extractions`` and ``/api/v1/tasks`` routes
    resolve a row's workspace by walking ``task/extraction → story → project →
    workspace`` and only then require the caller to be a member of that
    workspace (``member_repo.find_by_workspace_and_user``). A bare ``uuid4()``
    used as a ``user_story_id`` therefore never reads back as a row: the walk
    raises a 404 before the membership check is even reached. Seeding the whole
    chain — membership included — is what makes such a row addressable.

    Defaults target the ``authed_client`` caller: the chain is seeded with
    ``authed_user`` as an ADMIN member, because that membership is exactly what
    the routes' workspace resolution requires. Knobs, so a test asks for
    exactly what it needs:

    - ``user``: seed the chain for a different authenticated user instead.
    - ``stories``: how many stories the project gets; ``0`` when a test only
      needs an accessible (empty) workspace.
    - ``member``: ``False`` when a test needs a chain the caller must NOT be
      able to reach.
    - ``role``: the role that membership is granted with; ``ADMIN`` by default,
      because that is what the routes' admin-only checks accept.

    Everything else a test needs on top of the chain — tasks, a second
    workspace, a user to hand to ``user`` — is composed by the test from this
    factory, not added here as another knob.
    """

    async def _seed(
        *,
        user: User | None = None,
        stories: int = 1,
        member: bool = True,
        role: WorkspaceRole = WorkspaceRole.ADMIN,
    ) -> SeededWorkspace:
        owner = user or authed_user
        # ``workspaces.slug`` is unique, so each seeded workspace needs its own.
        workspace = await create_workspace(
            db_session,
            name="Seeded Workspace",
            slug=f"seeded-workspace-{uuid4().hex[:8]}",
            owner_id=owner.id,
        )
        project = await SQLAlchemyProjectRepository(db_session).save(
            Project(name="Seeded Project", workspace_id=workspace.id)
        )

        story_repo = SQLAlchemyUserStoryRepository(db_session)
        story_ids: list[UUID] = []
        for index in range(stories):
            story = await story_repo.save(
                UserStory(
                    project_id=project.id,
                    actor="user",
                    feature=f"use seeded feature {index}",
                    benefit="the seeded chain is addressable",
                    raw_text=(
                        f"As a user, I want to use seeded feature {index} "
                        "so that the seeded chain is addressable"
                    ),
                )
            )
            story_ids.append(story.id)

        if member:
            await SQLAlchemyWorkspaceMemberRepository(db_session).add(
                WorkspaceMember(
                    workspace_id=workspace.id,
                    user_id=owner.id,
                    role=role,
                )
            )

        return SeededWorkspace(
            workspace_id=workspace.id,
            project_id=project.id,
            story_ids=tuple(story_ids),
        )

    return _seed
