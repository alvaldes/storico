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
    async def list(self) -> list[Extraction]:
        """Return all extractions."""
        ...

    @abstractmethod
    async def delete(self, extraction_id: UUID) -> None:
        """Delete an extraction by its unique identifier."""
        ...
