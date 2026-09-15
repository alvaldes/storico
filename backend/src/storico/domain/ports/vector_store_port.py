"""VectorStorePort — abstract interface for vector similarity search and storage."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True, slots=True)
class ExtractionExample:
    """A past extraction result returned as a RAG example for the LLM prompt."""

    user_story_text: str
    tasks_summary: str
    model_used: str
    confidence_score: float | None = None
    similarity_score: float = 0.0


class VectorStorePort(ABC):
    """Port for vector similarity search and storage of extractions."""

    @abstractmethod
    async def search_similar(
        self,
        text: str,
        limit: int = 3,
        threshold: float = 0.85,
        workspace_id: UUID | None = None,
    ) -> list[ExtractionExample]:
        """Search for similar extractions by embedding the input text.

        Args:
            text: User story text to search by.
            limit: Maximum number of results to return.
            threshold: Minimum similarity score (0.0 to 1.0).
            workspace_id: Optional workspace to scope the search to. When
                provided, only examples stored for that workspace are returned;
                points without a matching ``workspace_id`` payload are excluded.

        Returns:
            List of similar ExtractionExample results.
            Empty list on any failure (graceful degradation).
        """
        ...

    @abstractmethod
    async def store_extraction(
        self,
        *,
        extraction_id: str,
        user_story_text: str,
        tasks_summary: str,
        model_used: str,
        workspace_id: UUID,
        confidence_score: float | None = None,
        user_story_id: str = "",
    ) -> None:
        """Store an extraction with its embedding for future RAG searches.

        ``workspace_id`` is persisted into the point payload so every search can
        be workspace-scoped. Silently skips on any failure (graceful
        degradation).
        """
        ...
