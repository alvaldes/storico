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
        *,
        workspace_id: UUID,
    ) -> list[ExtractionExample]:
        """Search for similar extractions by embedding the input text.

        The search is always scoped to ``workspace_id``. A workspace-scoped RAG
        lookup that silently widens into a global search is a cross-workspace
        leak — other workspaces' user stories would end up in this workspace's
        prompt — so omitting the scope is deliberately not expressible. Callers
        that cannot supply one must fail closed and skip retrieval.

        Args:
            text: User story text to search by.
            limit: Maximum number of results to return.
            threshold: Minimum similarity score (0.0 to 1.0).
            workspace_id: Workspace to scope the search to. Required; only
                examples stored for that workspace are returned, and points
                without a matching ``workspace_id`` payload are excluded.

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
    ) -> bool:
        """Store an extraction with its embedding for future RAG searches.

        ``workspace_id`` is persisted into the point payload so every search can
        be workspace-scoped.

        Returns:
            ``True`` when the point was accepted by the vector store, ``False``
            when it was skipped or rejected (empty embedding, unavailable
            client, or a store error). Never raises — failures degrade
            gracefully.
        """
        ...
