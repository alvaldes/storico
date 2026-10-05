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


@dataclass(frozen=True, slots=True)
class StandingRevocation:
    """One standing revocation attributed to a user — the account-delete read.

    The account-delete pre-check must name what blocks the deletion to the
    account's owner: the story the revoked mark sits in, the version number
    the mark's task was built from, and the task's title. A read model like
    ``TaskInvalidationCandidate`` — the rows are named through their join, not
    returned as entities.
    """

    user_story_id: UUID
    version_number: int
    title: str


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
    async def list_active_for_story(self, user_story_id: UUID) -> list[TaskInvalidation]:
        """The story's active marks, newest first — the card flag's read.

        The story-detail page renders one flag per task, so it needs to know
        which of the story's tasks carry an active mark without asking per
        task. The join is ``task_invalidations JOIN tasks``, filtered by
        ``tasks.user_story_id = :user_story_id`` and
        ``task_invalidations.revoked_at IS NULL``, ordered ``marked_at DESC``
        so the read is deterministic. All versions of the story are included on
        purpose: the caller intersects the result with the tasks it is
        displaying, so selecting a frozen version keeps working without a
        second query shape.

        The rows are marks of the story's own tasks, so returning the entity —
        with its ``task_id`` — is honest here, unlike the D16 candidate read,
        whose rows belong to other tasks.
        """
        ...

    @abstractmethod
    async def count_active_for_extraction(
        self, *, extraction_id: UUID, exclude_mark_id: UUID | None = None
    ) -> int:
        """How many active marks the extraction still carries — a computed value.

        The mark handlers' vector refresh needs exactly this number: the flag is
        ``True`` iff the extraction still has at least one active mark after the
        removal, so the revoke path counts with ``exclude_mark_id`` set to the
        mark it is about to revoke, **before** revoking it. Because the value is
        computed here, at call time, the refresh can run first without any
        surgery on ``revoke`` — which commits internally and cannot be asked a
        question first.

        The statement is one read: ``task_invalidations JOIN tasks ON
        tasks.id = task_invalidations.task_id``, filtered by
        ``tasks.extraction_id = :extraction_id`` and
        ``task_invalidations.revoked_at IS NULL``, minus the excluded mark
        (``task_invalidations.id != :exclude_mark_id``) when one is given.

        Args:
            extraction_id: The run whose marks are counted.
            exclude_mark_id: The mark being revoked, whose row must not count
                toward the remaining value. ``None`` excludes nothing.

        Returns:
            The number of active marks on the extraction's tasks.
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

    @abstractmethod
    async def list_standing_revocations_by_user(self, revoked_by: UUID) -> list[StandingRevocation]:
        """The user's revocations that still stand, each with its naming context.

        The join is ``task_invalidations JOIN tasks JOIN extractions``,
        filtered by ``task_invalidations.revoked_by = :user_id`` and
        ``task_invalidations.revoked_at IS NOT NULL``, ordered
        ``version_number ASC, title ASC`` — oldest version first, alphabetical
        within a version — so a refusal's entry list reads as a stable
        checklist the user can act on top-down, independent of mark
        timestamps. A ``revoked_by IS NULL`` row is an active mark (the
        revoke-pair CHECK ties the two nulls together) and is attributed to
        no one.
        """
        ...
