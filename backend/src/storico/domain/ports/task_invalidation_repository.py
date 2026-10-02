"""TaskInvalidationRepository — the port for the invalidation mark's storage.

Slice (a) shipped the table with no door; this port is the door. The port is
deliberately small: one write (``create``), two reads over one task's rows, one
targeted revoke, and one story-scoped candidate read for the D16 repetition
warning. There is deliberately no ``delete``: revoking is an UPDATE of the row
``find_active_by_task`` resolves, never a DELETE (D12) — the revoke history is
the record.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from storico.domain.entities.task_invalidation import TaskInvalidation


@dataclass(frozen=True, slots=True)
class TaskInvalidationCandidate:
    """One row of the D16 repetition read — a read model, not an entity.

    The join's rows belong to *other* tasks (the marked task of another version),
    so returning a ``TaskInvalidation`` would put a wrong ``task_id`` in an
    entity. What the D16 match needs is the marked version's number, the marked
    task's title, and the mark's reason and timestamp.
    """

    version_number: int
    title: str
    reason: str
    marked_at: datetime


class TaskInvalidationRepository(ABC):
    """Repository port for TaskInvalidation entities."""

    @abstractmethod
    async def create(self, mark: TaskInvalidation) -> TaskInvalidation:
        """Persist the mark and return the entity as the table now holds it.

        The caller owns the active-mark rule (at most one per task): a second
        active mark on one task is refused by the table's partial unique index.
        """
        ...

    @abstractmethod
    async def find_active_by_task(self, task_id: UUID) -> TaskInvalidation | None:
        """Return the task's active mark, or ``None`` when it has none.

        At most one row can match: the table's partial unique index allows one
        ``revoked_at IS NULL`` row per task. A revoked mark is history, not an
        active mark, and never answers here.
        """
        ...

    @abstractmethod
    async def list_by_task(self, task_id: UUID) -> list[TaskInvalidation]:
        """The task's full mark history, active mark first, then ``marked_at DESC``.

        Revoked rows are part of the history and are returned with their
        ``revoked_by``/``revoked_at`` attribution intact.
        """
        ...

    @abstractmethod
    async def revoke(self, mark_id: UUID, *, revoked_by: UUID, revoked_at: datetime) -> None:
        """Set ``revoked_by``/``revoked_at`` on the mark's row — an UPDATE, never a DELETE.

        Only the two revoke fields move; the row's reason, ``marked_by`` and
        ``marked_at`` stay untouched. The statement matches only a still-active
        row and raises ``EntityNotFound`` when none does.
        """
        ...

    @abstractmethod
    async def list_active_on_other_versions(
        self, *, user_story_id: UUID, exclude_extraction_id: UUID | None
    ) -> list[TaskInvalidationCandidate]:
        """The D16 candidate read: active marks on the story's *other* versions.

        The join is ``task_invalidations JOIN tasks JOIN extractions``, filtered
        by ``tasks.user_story_id``, ``task_invalidations.revoked_at IS NULL`` and
        ``tasks.extraction_id IS DISTINCT FROM :exclude_extraction_id``, ordered
        ``version_number DESC, marked_at DESC``. ``exclude_extraction_id=None``
        means the distinct-from predicate filters out nothing — it does *not*
        mean "exclude null extraction ids" (the column is ``NOT NULL`` anyway);
        the ``None`` shape exists for callers that have no version to exclude.
        """
        ...
