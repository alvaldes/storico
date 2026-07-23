"""Shared test helpers for Storico integration tests.

Canonical workspace-project seeding pattern: build Workspaces via the
repository so tests round-trip through the same entity↔ORM mapping the
production code path uses. Mirrors backend/tests/test_api/test_export.py:52-75.

Slug inline because ``python-slugify`` is not a project dependency
(see backend/pyproject.toml); tests need no real slugification semantics.
"""

from __future__ import annotations

from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from storico.domain.entities.workspace import Workspace
from storico.infrastructure.database.repositories.workspace_repository import (
    SQLAlchemyWorkspaceRepository as WorkspaceRepository,
)


def _slugify(name: str) -> str:
    """Minimal slugifier — only used for test fixture display names.

    Keeps the same ``name.lower().replace(" ", "-")`` shape as the
    pre-existing helper in backend/tests/test_api/test_export.py:56.
    """
    return name.lower().replace(" ", "-")


async def create_workspace(
    session: AsyncSession,
    *,
    name: str = "Test Workspace",
    slug: str | None = None,
    owner_id: UUID | None = None,
) -> Workspace:
    """Create and persist a Workspace, returning the saved entity.

    Helper for tests that need a valid ``workspace_id`` when constructing
    ``Project`` entities or POSTing to the (workspace-scoped) projects API.

    Auto-generates ``slug`` from ``name`` and ``owner_id`` (``uuid4``) if
    not provided, matching the Workspace entity contract used in
    ``_create_workspace`` in ``tests/test_api/test_export.py``.
    """
    slug_value = slug or _slugify(name)
    owner_value = owner_id or uuid4()
    workspace = Workspace(name=name, slug=slug_value, owner_id=owner_value)
    repo = WorkspaceRepository(session)
    return await repo.save(workspace)
