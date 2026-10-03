from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass
from uuid import UUID

from storico.domain.entities.story_deletion import StoryDeletion
from storico.domain.entities.user_story import UserStory


@dataclass(frozen=True, slots=True)
class StoryContextRow:
    """One row of the prompt-context read — a read model, not an entity.

    The prompt needs the story's identity and its text, nothing else, so the
    projection selects two columns instead of hydrating whole ``UserStory``
    rows (the same shape ``(b)'s`` ``TaskInvalidationCandidate`` takes).
    """

    id: UUID
    raw_text: str


class UserStoryRepository(ABC):
    """Repository port for UserStory entities."""

    @abstractmethod
    async def save(self, user_story: UserStory) -> UserStory:
        """Persist a user story. Creates or updates as needed."""
        ...

    @abstractmethod
    async def find_by_id(self, user_story_id: UUID) -> UserStory | None:
        """Find a user story by its unique identifier."""
        ...

    @abstractmethod
    async def list_page(
        self,
        *,
        workspace_id: UUID | None = None,
        project_id: UUID | None = None,
        workspace_ids: list[UUID] | None = None,
        limit: int,
        offset: int,
    ) -> tuple[list[UserStory], int]:
        """Return one page of stories matching exactly one scope, plus the total.

        Exactly one of ``workspace_id``, ``project_id`` or ``workspace_ids``
        must be given; calling with none raises ``ValueError``. An empty
        ``workspace_ids`` returns an empty page without issuing any statement:
        no memberships means no rows, not ``IN ()`` — and against the dev
        pooler, where one statement costs ~2s (a bare ``SELECT 1`` already
        measures 800ms in ``/api/v1/health``), an unasked statement is pure
        latency.

        The total rides on the rows' own statement as ``count(*) OVER ()``,
        so no separate ``SELECT COUNT(*)`` is issued on the normal path, and
        results are ordered by ``created_at DESC, id DESC`` in SQL.
        """
        ...

    @abstractmethod
    async def list_by_workspace(self, workspace_id: UUID) -> list[UserStory]:
        """Return all user stories belonging to a workspace."""
        ...

    @abstractmethod
    async def list(self) -> list[UserStory]:
        """Return all user stories."""
        ...

    @abstractmethod
    async def delete(self, user_story_id: UUID) -> None:
        """Delete a user story by its unique identifier."""
        ...

    @abstractmethod
    async def delete_with_record(self, user_story_id: UUID, record: StoryDeletion) -> None:
        """Delete the story and write its deletion record in one transaction.

        The atomic sibling of ``delete``: the story row is removed and the
        audit record of what was destroyed is inserted inside a single
        transaction, so there is never a deletion without its record and
        never a record without its deletion. Two separate commits could
        produce either orphan — and a record for a story that still exists is
        a lie a human would later read as history.

        If the delete matches no row, nothing is inserted, no commit is made
        and ``EntityNotFound`` is raised. If the record insert fails, the
        delete rolls back and ``RepositoryError`` is raised.
        """
        ...

    @abstractmethod
    async def find_by_parts(
        self, project_id: UUID, actor: str, feature: str, benefit: str
    ) -> UserStory | None:
        """Find a user story by project_id and its parts (actor, feature, benefit).

        Returns the existing story if found, None otherwise.
        This is used for duplicate detection based on the semantic content
        rather than the raw text format.
        """
        ...

    @abstractmethod
    async def list_parts_by_project(self, project_id: UUID) -> list[tuple[str, str, str, UUID]]:
        """Return ``(actor, feature, benefit, story_id)`` for every story in a project.

        One statement covers the whole project: a CSV import checks duplicates
        for many rows at once, and calling ``find_by_parts`` per row would cost
        one round-trip per row before anything was written.

        The strings come back exactly as stored — no normalisation. The
        caller's duplicate rule is an exact match, so folding case here would
        hide differences the rule treats as distinct (``User`` vs ``user``).
        An empty project returns an empty list.
        """
        ...

    @abstractmethod
    async def save_many(self, user_stories: Sequence[UserStory]) -> list[UserStory]:
        """Insert every story in one transaction and return the saved entities.

        A bulk import must not pay one commit per row: ``save`` commits per
        call, so a thousand rows would be a thousand transactions with no
        atomicity at all. Here the whole batch commits once — either every row
        lands or none does.

        An empty input returns an empty list without issuing any statement.
        No rows means no work, not a round-trip — the same rule
        ``list_page`` follows for an empty ``workspace_ids``, and against a
        pooler where one statement costs seconds, an unasked statement is pure
        latency.

        Returns the saved entities with their ids and timestamps populated.
        """
        ...

    @abstractmethod
    async def list_for_context(
        self, project_id: UUID, *, exclude_story_id: UUID
    ) -> list[StoryContextRow]:
        """Every story of one project except ``exclude_story_id``, oldest first.

        Deliberately unbounded: the context block is not a paginated resource —
        the paginator's window would drop rows while the composed prompt
        claimed to carry the whole project, a silent truncation. The exclusion
        rides in the ``WHERE`` clause, never in a Python filter, so the
        statement itself can never answer with the story being decomposed.
        """
        ...
