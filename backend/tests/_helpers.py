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

from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from storico.domain.entities.extraction import Extraction, ExtractionStatus
from storico.domain.entities.task import Task
from storico.domain.entities.workspace import Workspace
from storico.domain.services.extraction_service import ProjectContext
from storico.infrastructure.database.repositories import (
    SQLAlchemyExtractionRepository as ExtractionRepository,
)
from storico.infrastructure.database.repositories import (
    SQLAlchemyTaskRepository as TaskRepository,
)
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


async def seed_extraction(
    session: AsyncSession,
    story_id: UUID,
    *,
    model_used: str = "llama3.2",
    raw_response: str = "",
    provider: str = "ollama",
    temperature: float = 0.1,
    **kwargs: object,
) -> Extraction:
    """Create an extraction through the birth path and return the versioned entity.

    Revision ``0028`` declares ``version_number``, ``provider`` and ``temperature``
    ``NOT NULL`` and gives ``version_number`` no default, so a row can only be born
    through ``create_next_version`` — the same statement every production birth path
    uses. Seeding through ``save()`` would refuse the INSERT, and writing the number
    by hand would bypass the allocation the unique pair guards. The returned entity
    is the only source of the minted ``version_number``.

    ``provider``/``temperature`` default to the same values a birth path with no
    workspace configuration would record; ``kwargs`` (``status``, ``completed_at``,
    ``created_at``, ``confidence_score``, ...) pass through to the entity.
    """
    repo = ExtractionRepository(session)
    pending = Extraction(
        user_story_id=story_id,
        model_used=model_used,
        raw_response=raw_response,
        provider=provider,
        temperature=temperature,
        **kwargs,  # type: ignore[arg-type]
    )
    return await repo.create_next_version(pending)


async def seed_task(
    session: AsyncSession,
    story_id: UUID,
    title: str,
    *,
    extraction: Extraction | None = None,
    **kwargs: object,
) -> Task:
    """Create and persist a Task with the extraction its ``NOT NULL`` FK requires.

    ``tasks.extraction_id`` is ``NOT NULL`` from revision ``0028`` on, so every task
    seed needs an extraction row to belong to. When ``extraction`` is not supplied,
    one is allocated through ``seed_extraction`` — the mechanical case for tests that
    only need addressable task rows. Tests that count extraction rows must allocate
    the extraction themselves and pass it in, so the task reuses it instead of
    quietly minting an extra version.

    ``kwargs`` (``status``, ``created_at``, ``labels``, ...) pass through to the entity.
    """
    if extraction is None:
        # A task is the output of a run that completed, so a task seed with no
        # explicit extraction mints a COMPLETED one: reads answer the story's
        # current version only (D-a-5 item 2), and a task hanging off a pending
        # run would be invisible to every version-aware read. Tests that need a
        # pending or failed run mint it explicitly through ``seed_extraction``
        # and pass it in — the default of ``seed_extraction`` stays untouched.
        extraction = await seed_extraction(
            session,
            story_id,
            status=ExtractionStatus.COMPLETED,
            completed_at=datetime.now(UTC),
        )
    task = Task(user_story_id=story_id, extraction_id=extraction.id, title=title, **kwargs)  # type: ignore[arg-type]
    return await TaskRepository(session).save(task)


def simple_context(**overrides: object) -> ProjectContext:
    """A minimal ``ProjectContext`` for ``render()``/``extract()`` call sites.

    ``render()``'s ``context`` argument is required with no default — the type
    carries the requirement that every rendered prompt was composed from real
    project state — so every test call site must supply one. Call sites that
    assert nothing about the context use this builder; cases that assert on the
    composed block build their own ``ProjectContext`` with the rows they need.

    Keyword overrides pass straight through: ``other_stories``/``existing_tasks``
    take tuples of ``StoryContextRow``/``TaskContextRow``, ``negative_examples``
    stays empty (WU2 composes it).
    """
    defaults: dict[str, object] = {
        "name": "Test Project",
        "description": "A test project description",
        "other_stories": (),
        "existing_tasks": (),
    }
    defaults.update(overrides)
    return ProjectContext(**defaults)  # type: ignore[arg-type]
