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
        exclude_story_id: str,
    ) -> list[ExtractionExample]:
        """Search for similar extractions by embedding the input text.

        The search is always scoped to ``workspace_id``. A workspace-scoped RAG
        lookup that silently widens into a global search is a cross-workspace
        leak — other workspaces' user stories would end up in this workspace's
        prompt — so omitting the scope is deliberately not expressible. Callers
        that cannot supply one must fail closed and skip retrieval.

        The search is also always excluded from the story being extracted:
        ``exclude_story_id`` is the story whose previous versions must never be
        retrieved as their own few-shot examples. Both exclusions are
        unconditional rules of retrieval, and **no caller may opt out** — the
        parameter has no default, so a retrieval that cannot state which story
        it is must not run at all.

        Args:
            text: User story text to search by.
            limit: Maximum number of results to return.
            threshold: Minimum similarity score (0.0 to 1.0).
            workspace_id: Workspace to scope the search to. Required; only
                examples stored for that workspace are returned, and points
                without a matching ``workspace_id`` payload are excluded.
            exclude_story_id: Story the retrieval must exclude. Required; the
                caller forwards the id of the story being extracted (string
                form, as stored in the point payload).

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
        project_id: UUID,
        version_number: int,
        confidence_score: float | None = None,
        user_story_id: str = "",
    ) -> bool:
        """Store an extraction with its embedding for future RAG searches.

        ``workspace_id`` is persisted into the point payload so every search can
        be workspace-scoped. ``project_id`` and ``version_number`` are persisted
        alongside it: ``project_id`` scopes the point to its project and
        ``version_number`` ties the point to the run that produced it — the
        number the route minted and returned in its 202 body, so a retry reuses
        it instead of minting another (D22).

        Returns:
            ``True`` when the point was accepted by the vector store, ``False``
            when it was skipped or rejected (empty embedding, unavailable
            client, or a store error). Never raises — failures degrade
            gracefully.
        """
        ...

    @abstractmethod
    async def set_has_invalid_tasks(self, *, extraction_id: str, has_invalid_tasks: bool) -> None:
        """Set the validity flag on the point whose id IS ``extraction_id``.

        No search is involved: ``store_extraction`` upserts with
        ``id=extraction_id``, so the point is addressable by the extraction id
        directly. A point that does not exist is a no-op — nothing was ever
        stored, so nothing can be retrieved, so there is nothing to flag and
        not an error.

        Unlike ``search_similar``/``store_extraction``, which degrade gracefully
        and never raise, this method **raises** ``VectorStoreError`` on failure:
        its caller is a destructive-adjacent operation (the task-mark handlers'
        refresh, which runs before the relational write) that must not proceed
        — and must not persist the mark — on an unverified result.

        Args:
            extraction_id: Identifier of the extraction whose point is flagged;
                must equal the point id written by ``store_extraction``.
            has_invalid_tasks: The flag value — ``True`` when the run gains an
                active invalid-task mark, ``False`` when its last active mark is
                revoked.

        Raises:
            VectorStoreError: when the flag could not be written (client
                unavailable or driver failure).
        """
        ...

    @abstractmethod
    async def delete_by_story(self, *, workspace_id: UUID, user_story_id: str) -> None:
        """Delete every point of one story in one workspace.

        Unlike ``search_similar``/``store_extraction``, this method does **not**
        degrade silently: it raises ``VectorStoreError`` on failure. The caller
        is a destructive operation (story deletion) that must not proceed on an
        unverified cleanup — a lost upsert costs one future RAG example, but a
        cleanup that was believed to happen and wasn't leaves orphan points for a
        story that no longer exists, answering future similarity searches with
        content whose owner was deleted.

        The distinction the caller depends on: "no vector store configured" and
        "a vector store that cannot be reached" are different outcomes. The
        service skips this call entirely when there is no store at all — a
        legitimate completion, since no points exist to clean. But when a store
        is configured and its client is unavailable, or the delete itself fails,
        this raises.

        Args:
            workspace_id: Workspace whose points are eligible for deletion.
            user_story_id: Identifier of the deleted story; must match the
                string form written into point payloads by ``store_extraction``.

        Raises:
            VectorStoreError: when the cleanup could not be verified.
        """
        ...
