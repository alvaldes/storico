from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from uuid import UUID

from storico.domain.entities.extraction import Extraction


class ExtractionRepository(ABC):
    """Repository port for Extraction entities.

    There is deliberately no whole-row writer and no ``delete``:
    a version's rows are never removed inside a version (the story cascade is the
    only deletion path), and the terminal writes are targeted marks that cannot
    name — and so cannot silently null — a snapshot column they do not own.
    """

    @abstractmethod
    async def create_next_version(self, extraction: Extraction) -> Extraction:
        """Insert the extraction with its per-story version number minted in the INSERT.

        The number is computed inside the row's own statement (``max(version_number)
        + 1`` for the story) and returned on the entity — the return value is the
        only source of the minted number, and any number the passed entity carries
        is ignored. A lost race against a concurrent run on the same story is
        retried a bounded number of times; a conflict on every attempt raises
        ``VersionAllocationConflictError``.
        """
        ...

    @abstractmethod
    async def record_rendered_prompt(
        self,
        extraction_id: UUID,
        *,
        prompt_rendered: str,
        prompt_config: dict | None,
    ) -> None:
        """Write the rendered prompt and its prompt config, once, before the provider runs.

        The write replaces ``prompt_config`` wholesale (Postgres ``json`` has no
        merge operator), so the caller restates every key it wants stored.
        """
        ...

    @abstractmethod
    async def record_usage(
        self,
        extraction_id: UUID,
        *,
        prompt_config: dict,
    ) -> None:
        """Record the provider's usage container on the snapshot, after it answers.

        One targeted UPDATE that names only ``prompt_config``: no rendered
        prompt, no provider/model/temperature column, no status. Like the
        render-time write, the caller restates the complete dictionary — the
        six render-time keys plus ``usage`` — because the JSON column has no
        merge. The runner calls this only when the provider reported usage;
        a provider without one leaves the six render-time keys untouched.

        Raises:
            EntityNotFound: If no extraction row matches ``extraction_id``.
        """
        ...

    @abstractmethod
    async def mark_completed(
        self,
        extraction_id: UUID,
        *,
        raw_response: str,
        confidence_score: float | None,
        completed_at: datetime,
    ) -> None:
        """Mark the extraction completed — one targeted UPDATE, no snapshot columns.

        Raises ``EntityNotFound`` when no row matches.
        """
        ...

    @abstractmethod
    async def mark_failed(
        self,
        extraction_id: UUID,
        *,
        error_info: str,
        completed_at: datetime,
    ) -> None:
        """Mark the extraction failed — one targeted UPDATE, no snapshot columns.

        Raises ``EntityNotFound`` when no row matches.
        """
        ...

    @abstractmethod
    async def find_by_id(self, extraction_id: UUID) -> Extraction | None:
        """Find an extraction by its unique identifier."""
        ...

    @abstractmethod
    async def find_current_version(self, user_story_id: UUID) -> Extraction | None:
        """Return the story's current version, derived — never stored.

        "Current" is the highest-numbered *completed* version of the story: a
        ``pending`` or ``failed`` run above it never steals the title. Returns
        ``None`` when the story has no completed version.
        """
        ...

    @abstractmethod
    async def list_versions(self, user_story_id: UUID) -> list[Extraction]:
        """Every version of one story, ordered ``version_number DESC`` — the newest first.

        Deliberately unbounded: the version list is the pagination *input* for the
        version selector, not a paginated resource, and the paginator's 20/100 window
        would truncate a long history silently — exactly the failure this read exists
        to avoid. A story's version count is bounded by hand-run extractions, so no
        window is applied here, and a ``pending`` or ``failed`` run is part of the
        history the user must see, never filtered out.

        Agreement with ``find_current_version``: "current" is derived in two places —
        the first ``completed`` entry of this ordered list, and that method's
        ``LIMIT 1`` query — and they agree by construction because both mean
        "highest-numbered completed version"; the repository test pinning one against
        the other for a three-version story is what keeps them in step. Do not unify
        them by making ``find_current_version`` load this list and filter in Python:
        it sits on the hot path of every task write (the frozen check) and must stay
        a ``LIMIT 1`` query.
        """
        ...

    @abstractmethod
    async def list_page(
        self,
        *,
        workspace_id: UUID | None = None,
        user_story_id: UUID | None = None,
        workspace_ids: list[UUID] | None = None,
        limit: int,
        offset: int,
    ) -> tuple[list[Extraction], int]:
        """Return one page of extractions matching exactly one scope, plus the total.

        Exactly one of ``workspace_id``, ``user_story_id`` or ``workspace_ids``
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
    async def list(self) -> list[Extraction]:
        """Return all extractions."""
        ...
