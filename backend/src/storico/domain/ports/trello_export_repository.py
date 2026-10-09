"""TrelloExportRepository — the port for the persisted export job."""

from __future__ import annotations

from abc import ABC, abstractmethod
from uuid import UUID

from storico.domain.entities.trello_export import TrelloExport, TrelloExportStatus


class TrelloExportRepository(ABC):
    """Repository port for TrelloExport entities.

    The job row is the polling contract: the route creates it pending, the
    background runner moves it through its lifecycle, and the GET route reads
    whatever state it has reached. ``save`` therefore upserts — the runner
    writes through the same port the route created the row with.
    """

    @abstractmethod
    async def save(self, export: TrelloExport) -> TrelloExport:
        """Persist a job. Creates or updates as needed."""
        ...

    @abstractmethod
    async def find_by_id(self, export_id: UUID) -> TrelloExport | None:
        """Find a job by its unique identifier."""
        ...

    @abstractmethod
    async def find_by_statuses(self, statuses: set[TrelloExportStatus]) -> list[TrelloExport]:
        """Find every job currently in one of *statuses*.

        The startup sweep uses this to bound the candidate set in the query;
        the age filter stays with the caller, next to the clock it owns.
        """
        ...
