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


@dataclass(frozen=True, slots=True)
class StoryCardContext:
    """One row of the card-context read — a read model, not an entity.

    What a board card needs to name its story and where it came from: the
    project label (decision D14 of feature ``kanban-card-project-story``)
    plus the story's own sentence (decision D19 of feature
    ``kanban-context-tooltips``), whose purpose is the story chip's tooltip,
    plus the project's own icon name (decision D24 of feature
    ``kanban-project-icons``) — the same kebab-case name the project pages
    render through ``IconDisplay``. Like ``StoryContextRow`` above, the
    projection selects the columns the caller reads instead of hydrating
    whole ``UserStory`` rows.
    """

    project_id: UUID
    project_name: str
    # ``icon`` is nullable on the model while ``name`` is not, so an icon-less
    # project is an ordinary project (decision D22): the three values are
    # independent facts about one story's project, and only the icon may be
    # absent — a ``None`` icon never takes the label's place.
    project_icon: str | None
    # ``str | None`` because the repository answers ``None`` for a story whose
    # sentence is empty: the column is NOT NULL but carries no ``min_length``,
    # so an empty string is reachable and must read as "no sentence" rather
    # than as an empty tooltip. The annotation said ``str`` while the mapping
    # already produced ``None`` — a type that lied about its own values until a
    # reviewer compared the two.
    story_raw_text: str | None


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
    async def list_by_project(self, project_id: UUID) -> list[UserStory]:
        """Return all user stories belonging to a project, unpaginated.

        The Trello export's project-scope read: the plan builder attributes each
        card to its story, so the export needs every story the exported tasks
        may reference, not a page of them.
        """
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
    async def story_context_for(self, story_ids: list[UUID]) -> dict[UUID, StoryCardContext]:
        """Batch story → its card context — project label, icon and story text, one statement.

        The card's context-chip data: the project label is decision D14 of
        feature ``kanban-card-project-story``; the story's ``raw_text`` joined
        into the same statement is decision D19 of feature
        ``kanban-context-tooltips`` — the story chip's tooltip needs the full
        sentence the story list already shows; and the project's ``icon`` in
        the same statement is decision D24 of feature
        ``kanban-project-icons`` — the card draws the project's own icon, not
        a hardcoded one. The read that was already walking
        ``task → story → project`` simply answers one more column. Never a
        second query and never a per-task lookup.

        This is a repository-level read by design, not a lazy ORM traversal:
        the route sees domain entities, which carry no relationships to lean
        on, and building the mapping in the repository from the models'
        declared ``lazy="selectin"`` relationships would quietly issue a
        statement per row instead of the one deliberate join this read pays
        for.

        The join is a single hop on both legs: ``user_stories.project_id`` is
        an indexed FK (``ix_user_stories_project_id``) and ``projects.id`` is
        the primary key, so the batch is the IN list itself — the same shape
        ``ExtractionRepository.version_numbers`` takes.

        An empty ``story_ids`` is answered here rather than sent as ``IN ()``:
        an empty page of tasks means no rows, not a statement. Ids with no row
        are absent from the dict, never ``None`` entries, and a row whose
        ``raw_text`` is absent is unresolved too — an empty tooltip would be a
        fabricated answer, and the column is ``NOT NULL``, so such a row can
        only mean data the read refuses to name. An unresolvable story is the
        caller's decision to render as absence, not a fabricated context.
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
