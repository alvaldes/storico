"""Integration test against a real Postgres via testcontainers.

This test is NOT executed by default — it is marked
``@pytest.mark.integration`` and additionally disabled unless the Docker
daemon is reachable. ``docker is not running`` is exactly the scenario
the plan flagged as the honest-skip case: rather than forcing a docker
pull in CI/local runs that are not prepared for it, we fail-open with a
skip.

To run manually (docker daemon up):

    pytest tests/test_integration/test_projects_integration.py -m integration

What this measures: the latency of ``list_projects`` against a real
Postgres 16 with enough rows (50 projects×5 user stories = 250 stories).
The perf sears of commits P0.1 / P0.3 / P2.1 should keep this under
500ms wall-clock in CI-like hardware even though it's the small
asyncpg + 1 round-trip query.
"""

from __future__ import annotations

import socket
import time
import uuid

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

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


@pytest_asyncio.fixture(scope="module")
async def pg_engine() -> AsyncEngine:
    """Startup Postgres 16 in a testcontainer and wire an async engine."""
    # Import lazily so the module import itself never blocks on testcontainers —
    # testcontainers imports docker, which is heavy and may pull images.
    from testcontainers.postgres import PostgresContainer

    with PostgresContainer("postgres:16-alpine", driver="asyncpg") as pg:
        url = pg.get_connection_url()
        engine = create_async_engine(url, pool_size=5, max_overflow=10, pool_pre_ping=True)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        yield engine
        await engine.dispose()


@pytest_asyncio.fixture
async def pg_session(pg_engine: AsyncEngine) -> AsyncSession:
    factory = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with factory() as session:
        yield session


@pytest.mark.asyncio
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
    ws = Workspace(name=f"Perf-{uuid.uuid4().hex[:8]}", slug=f"perf-{uuid.uuid4().hex[:8]}", owner_id=owner_id)
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
    assert elapsed_ms < 500, f"list_by_workspace_with_counts took {elapsed_ms:.1f}ms (threshold 500ms)"
