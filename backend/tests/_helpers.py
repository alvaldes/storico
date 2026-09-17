"""Shared test helpers for Storico integration tests.

Low-level builders only. Constructing a Workspace through the repository keeps
tests on the same entity↔ORM mapping the production code path uses.

Seeding a whole ``workspace → project → stories`` chain plus the caller's
membership has exactly one entry point — the ``seed_workspace`` fixture in
``tests/conftest.py`` — and this module deliberately stays below it.

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

    Not real slugification: ``python-slugify`` is not a project dependency, and
    no test asserts on slug semantics beyond uniqueness.
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

    For tests that need a valid ``workspace_id`` when constructing ``Project``
    entities or POSTing to the (workspace-scoped) projects API, and for the
    ``seed_workspace`` factory itself.

    Auto-generates ``slug`` from ``name`` and ``owner_id`` (``uuid4``) when they
    are not provided.
    """
    slug_value = slug or _slugify(name)
    owner_value = owner_id or uuid4()
    workspace = Workspace(name=name, slug=slug_value, owner_id=owner_value)
    repo = WorkspaceRepository(session)
    return await repo.save(workspace)
