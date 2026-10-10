from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from uuid import UUID

from storico.domain.entities.task import Task, TaskStatus


@dataclass(frozen=True, slots=True)
class TaskContextRow:
    """One row of the prompt-context read — a read model, not an entity.

    The rows belong to the *existing tasks* block of a prompt: the title, the
    kanban status and the owning story's id (so the template can name which
    story each task came from), nothing else. Returning a ``Task`` would drag
    the description, labels and dependencies through a read that never reads
    them.
    """

    title: str
    status: TaskStatus
    user_story_id: UUID


class TaskRepository(ABC):
    """Repository port for Task entities."""

    @abstractmethod
    async def save(self, task: Task) -> Task:
        """Persist a task. Creates or updates as needed."""
        ...

    @abstractmethod
    async def find_by_id(self, task_id: UUID) -> Task | None:
        """Find a task by its unique identifier."""
        ...

    @abstractmethod
    async def list_by_story(self, user_story_id: UUID) -> list[Task]:
        """Return all tasks belonging to a user story."""
        ...

    @abstractmethod
    async def list_page(
        self,
        *,
        workspace_id: UUID | None = None,
        user_story_id: UUID | None = None,
        workspace_ids: list[UUID] | None = None,
        extraction_id: UUID | None = None,
        project_id: UUID | None = None,
        limit: int,
        offset: int,
    ) -> tuple[list[Task], int]:
        """Return one page of tasks matching exactly one scope, plus the total.

        Exactly one of ``workspace_id``, ``user_story_id``, ``workspace_ids``
        or ``project_id`` must be given; calling with none raises
        ``ValueError``. An empty ``workspace_ids`` returns an empty page
        without issuing any statement: no memberships means no rows, not
        ``IN ()`` — and against the dev pooler, where one statement costs ~2s
        (a bare ``SELECT 1`` already measures 800ms in ``/api/v1/health``), an
        unasked statement is pure latency.

        The total rides on the rows' own statement as ``count(*) OVER ()``,
        so no separate ``SELECT COUNT(*)`` is issued on the normal path, and
        results are ordered by ``created_at DESC, id DESC`` in SQL.

        Current-version predicate (derived, never stored): the story scope
        filters to the highest-numbered ``completed`` version of the story, so
        both the page and the ``total`` count current tasks only. The
        workspace, ``workspace_ids`` and ``project_id`` scopes keep a task
        only while no higher-numbered ``completed`` version of its story
        exists. Passing ``extraction_id`` alongside ``user_story_id`` bypasses
        the predicate and reads exactly that version — the version selector's
        per-version read; ``extraction_id`` without ``user_story_id`` raises
        ``ValueError``.
        """
        ...

    @abstractmethod
    async def list_by_workspace(self, workspace_id: UUID) -> list[Task]:
        """Return all tasks belonging to a workspace."""
        ...

    @abstractmethod
    async def list_current_by_workspace(self, workspace_id: UUID) -> list[Task]:
        """Return the workspace's current-version tasks, unpaginated.

        The export's read: a task is returned only while no higher-numbered
        ``completed`` version of its story exists — the same current-version
        predicate the workspace scope of ``list_page`` carries, without the
        page window.
        """
        ...

    @abstractmethod
    async def list_current_by_project(self, project_id: UUID) -> list[Task]:
        """Return the project's current-version tasks, unpaginated.

        The Trello export's project-scope read: the same current-version
        predicate joined to the project scope, without the page window.
        """
        ...

    @abstractmethod
    async def list_current_by_story(self, user_story_id: UUID) -> list[Task]:
        """Return the story's current-version tasks, unpaginated.

        The Trello export's story-scope read: only the tasks of the
        highest-numbered ``completed`` version of the story — a superseded
        version's tasks stay out of the board exactly as they stay out of the
        file export.
        """
        ...

    @abstractmethod
    async def list_by_story_version(self, user_story_id: UUID, extraction_id: UUID) -> list[Task]:
        """Return exactly one story version's tasks, named by its extraction id.

        The version read the file export's selector needs: a superseded
        version's tasks come back too — currency is not the question being
        asked here. Both filters ride in the ``WHERE``, so an extraction id
        belonging to another story matches no row: a version can only be read
        through its own story, and a valid id aimed at the wrong story cannot
        leak across.
        """
        ...

    @abstractmethod
    async def list(self) -> list[Task]:
        """Return all tasks."""
        ...

    @abstractmethod
    async def delete(self, task_id: UUID) -> None:
        """Delete a task by its unique identifier."""
        ...

    @abstractmethod
    async def list_for_context(
        self, project_id: UUID, *, exclude_story_id: UUID
    ) -> list[TaskContextRow]:
        """The project's current-version, valid tasks except ``exclude_story_id``'s.

        Deliberately unbounded: the context block is not a paginated resource —
        the paginator's window would drop tasks while the composed prompt
        claimed to carry the project's whole task set, a silent truncation.
        Both exclusions ride in the ``WHERE`` clause, never in a Python filter:
        the story being decomposed (``user_story_id != exclude_story_id``), and
        any task carrying an active mark (``NOT EXISTS`` a ``task_invalidations``
        row with ``revoked_at IS NULL``).
        """
        ...
