from __future__ import annotations

from abc import ABC, abstractmethod
from uuid import UUID

from storico.domain.entities.extraction import Extraction


class ExtractionRepository(ABC):
    """Repository port for Extraction entities."""

    @abstractmethod
    async def save(self, extraction: Extraction) -> Extraction:
        """Persist an extraction. Creates or updates as needed."""
        ...

    @abstractmethod
    async def find_by_id(self, extraction_id: UUID) -> Extraction | None:
        """Find an extraction by its unique identifier."""
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

    @abstractmethod
    async def delete(self, extraction_id: UUID) -> None:
        """Delete an extraction by its unique identifier."""
        ...
