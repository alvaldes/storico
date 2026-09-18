"""Integration test against a real Postgres via testcontainers.

This test is marked ``@pytest.mark.integration`` and disabled unless the
Docker daemon is reachable, so it skips on a laptop without a daemon and
runs for real on GitHub runners, which do have one. ``docker is not
running`` is exactly the scenario the plan flagged as the honest-skip
case: rather than forcing a docker pull in runs that are not prepared for
it, we fail-open with a skip.

To run manually (docker daemon up):

    pytest tests/test_integration/test_projects_integration.py -m integration

What this measures: the latency of ``list_projects`` against a real
Postgres 16 with enough rows (50 projects×5 user stories = 250 stories).
The perf sears of commits P0.1 / P0.3 / P2.1 should keep this under
500ms wall-clock in CI-like hardware even though it's the small
asyncpg + 1 round-trip query.
"""

from __future__ import annotations

import time
import uuid
from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from storico.domain.entities.project import Project
from storico.domain.entities.user_story import UserStory
from storico.domain.entities.workspace import Workspace
from storico.domain.entities.workspace_member import WorkspaceMember, WorkspaceRole
from storico.infrastructure.database.models import Base
from storico.infrastructure.database.repositories.project_repository import (
    SQLAlchemyProjectRepository,
)
from storico.infrastructure.database.repositories.user_story_repository import (
    SQLAlchemyUserStoryRepository,
)
from storico.infrastructure.database.repositories.workspace_member_repository import (
    SQLAlchemyWorkspaceMemberRepository,
)
from storico.infrastructure.database.repositories.workspace_repository import (
    SQLAlchemyWorkspaceRepository,
)


def _docker_reachable() -> bool:
    """Best-effort check — is the docker daemon pickable in $DOCKER_HOST?

    testcontainers spawns containers via docker; if the daemon is offline
    we get a noisy multi-second timeout trying to start a container. The
    socket probe fails fast and the test skips cleanly instead.
    """
    import os

    host = os.environ.get("DOCKER_HOST", "")
    # Docker Desktop default unix socket path:
    socket_path = host.removeprefix("unix://") if host.startswith("unix://") else ""
    if not socket_path:
        socket_path = os.path.expanduser("~/.docker/run/docker.sock")
        if not os.path.exists(socket_path):
            socket_path = "/var/run/docker.sock"
    return os.path.exists(socket_path) and os.access(socket_path, os.W_OK)


pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not _docker_reachable(),
        reason="Docker daemon unreachable — this integration test needs docker to spawn a Postgres container via testcontainers.",
    ),
]


# loop_scope="module" keeps the fixtures on the loop that owns the engine;
# pytest-asyncio otherwise gives every single test a fresh loop, and asyncpg
# connections created on one loop cannot be awaited from another.
@pytest_asyncio.fixture(scope="module", loop_scope="module")
async def pg_engine() -> AsyncGenerator[AsyncEngine, None]:
    """Startup Postgres 16 in a testcontainer and wire an async engine."""
    # Import lazily so the module import itself never blocks on testcontainers —
    # testcontainers imports docker, which is heavy and may pull images.
    # ``testcontainers.postgres`` is the one path that exists across the >=4.9
    # range; on 4.15+ it re-exports ``community.postgres`` with a
    # DeprecationWarning, which pytest.ini does not turn into a failure.
    from testcontainers.postgres import PostgresContainer

    # The container keeps its own *sync* driver, and only the app engine moves to
    # asyncpg. Older testcontainers releases probe readiness by running
    # ``create_engine(get_connection_url()).connect()``, which is a legacy sync
    # Engine over whatever driver the URL names -- hand it an async one and the
    # probe dies with MissingGreenlet before this fixture yields anything. Kept
    # version-independent rather than relying on newer releases probing with psql.
    with PostgresContainer("postgres:16-alpine") as pg:
        url = make_url(pg.get_connection_url()).set(drivername="postgresql+asyncpg")
        engine = create_async_engine(url, pool_size=5, max_overflow=10, pool_pre_ping=True)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        yield engine
        await engine.dispose()


@pytest_asyncio.fixture(loop_scope="module")
async def pg_session(pg_engine: AsyncEngine) -> AsyncGenerator[AsyncSession, None]:
    factory = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with factory() as session:
        yield session


@pytest.mark.asyncio(loop_scope="module")
async def test_list_projects_with_counts_latency_under_500ms(pg_session: AsyncSession) -> None:
    """Seed 50 projects×5 stories, measure list_by_workspace_with_counts wall time.

    Guards the perf fix from P0.1: with N=50 projects, the previous
    N+1 path (list + count_stories per project) would fire ~51 round-trips
    on a remote Supabase pool. With the JOIN+GROUP_BY fix, this should
    complete in well under 500ms even from inside the testcontainer bridge.
    """
    ws_repo = SQLAlchemyWorkspaceRepository(pg_session)
    member_repo = SQLAlchemyWorkspaceMemberRepository(pg_session)
    project_repo = SQLAlchemyProjectRepository(pg_session)
    story_repo = SQLAlchemyUserStoryRepository(pg_session)

    owner_id = uuid.uuid4()
    ws = Workspace(
        name=f"Perf-{uuid.uuid4().hex[:8]}", slug=f"perf-{uuid.uuid4().hex[:8]}", owner_id=owner_id
    )
    ws = await ws_repo.save(ws)
    await member_repo.add(
        WorkspaceMember(workspace_id=ws.id, user_id=owner_id, role=WorkspaceRole.ADMIN)
    )

    for _ in range(50):
        project = Project(name=f"P-{uuid.uuid4().hex[:6]}", workspace_id=ws.id)
        await project_repo.save(project)
        for _ in range(5):
            await story_repo.save(
                UserStory(
                    project_id=project.id,
                    actor="user",
                    feature="feature",
                    benefit="benefit",
                    raw_text="As a user, I want a feature so that benefit.",
                )
            )

    start = time.perf_counter()
    pairs = await project_repo.list_by_workspace_with_counts(ws.id)
    elapsed_ms = (time.perf_counter() - start) * 1000.0

    assert len(pairs) == 50, "all 50 projects present"
    assert all(pwc.story_count == 5 for pwc in pairs), "each project has 5 stories"
    assert elapsed_ms < 500, (
        f"list_by_workspace_with_counts took {elapsed_ms:.1f}ms (threshold 500ms)"
    )
