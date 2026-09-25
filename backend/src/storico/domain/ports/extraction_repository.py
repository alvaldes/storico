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
    async def list_by_story(self, user_story_id: UUID) -> list[Extraction]:
        """Return all extractions for a given user story."""
        ...

    @abstractmethod
    async def list_by_workspace(self, workspace_id: UUID) -> list[Extraction]:
        """Return all extractions belonging to a workspace."""
        ...

    @abstractmethod
    async def list_by_workspaces(self, workspace_ids: list[UUID]) -> list[Extraction]:
        """Return every extraction belonging to any of the workspaces, in one query.

        The fold for callers that used to await ``list_by_workspace`` once per workspace, which
        cost one statement per workspace. Against the dev pooler a statement measures ~2s — a bare
        ``SELECT 1`` already costs 800ms there (``/api/v1/health``) — so 12 of them is how a list
        request reached 25-32s. An empty ``workspace_ids`` returns ``[]`` without querying: no
        memberships is no rows, not a statement.
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
