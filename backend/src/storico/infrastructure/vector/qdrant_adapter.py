"""QdrantAdapter — VectorStorePort implementation using Qdrant vector database."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from uuid import UUID

from qdrant_client import AsyncQdrantClient
from qdrant_client.http import models as qdrant_models

from storico.domain.ports import EmbeddingPort, ExtractionExample, VectorStorePort

logger = logging.getLogger(__name__)


class QdrantAdapter(VectorStorePort):
    """VectorStorePort implementation backed by Qdrant.

    Features:
    - Lazy async client initialization (first use, not constructor)
    - Auto-creates collection on first use if missing, and ensures a keyword
      payload index on ``workspace_id`` so filtered searches stay fast.
    - Workspace isolation: every search sends a ``workspace_id`` filter and
      every stored point carries ``workspace_id`` in its payload.
    - Graceful degradation: empty results on failure.

    Collection schema (storico_extractions):
        - vector: ``vector_size``d float array
        - payload: user_story_text, tasks_summary, model_used,
                   confidence_score, created_at, user_story_id, workspace_id
    """

    def __init__(
        self,
        embedding_port: EmbeddingPort,
        qdrant_url: str = "http://localhost:6333",
        qdrant_api_key: str | None = None,
        collection_name: str = "storico_extractions",
        vector_size: int = 768,
        distance: qdrant_models.Distance = qdrant_models.Distance.COSINE,
    ) -> None:
        self._embedding_port = embedding_port
        self._qdrant_url = qdrant_url
        self._qdrant_api_key = qdrant_api_key
        self._collection_name = collection_name
        self._vector_size = vector_size
        self._distance = distance
        self._client: AsyncQdrantClient | None = None
        self._index_ensured = False

    def _check_dimensions(self) -> None:
        """Fail fast when the embedding dimensions do not match the collection.

        Prevents silently storing vectors that cannot be searched against the
        configured collection vector size.
        """
        provider_dimensions = self._embedding_port.dimensions
        if provider_dimensions != self._vector_size:
            raise ValueError(
                "Embedding provider dimensions "
                f"({provider_dimensions}) do not match the Qdrant collection "
                f"vector size ({self._vector_size}). "
                "Configure STORICO_EMBEDDING_PROVIDER/DIMENSIONS consistently."
            )

    async def _get_client(self) -> AsyncQdrantClient | None:
        """Lazy init — creates client + ensures collection on first call.

        Returns None if connection fails (graceful degradation).
        """
        if self._client is not None:
            return self._client

        self._check_dimensions()

        try:
            self._client = AsyncQdrantClient(
                url=self._qdrant_url,
                api_key=self._qdrant_api_key,
                timeout=10,
            )
            # Check if collection exists, create if not
            collections = await self._client.get_collections()
            existing = {c.name for c in collections.collections}

            if self._collection_name not in existing:
                await self._client.create_collection(
                    collection_name=self._collection_name,
                    vectors_config=qdrant_models.VectorParams(
                        size=self._vector_size,
                        distance=self._distance,
                    ),
                )
                logger.info("Created Qdrant collection '%s'", self._collection_name)

            await self._ensure_workspace_payload_index(self._client)
            return self._client
        except Exception as e:
            logger.warning("Failed to initialize Qdrant client: %s", e)
            self._client = None
            return None

    async def _ensure_workspace_payload_index(self, client: AsyncQdrantClient) -> None:
        """Create the keyword payload index on ``workspace_id`` once.

        Idempotent: after the first success the flag is set so repeated lazy
        inits do not re-issue the index request. A failure is logged but is not
        fatal — searches still work, just without the index acceleration.
        """
        if self._index_ensured:
            return
        try:
            await client.create_payload_index(
                collection_name=self._collection_name,
                field_name="workspace_id",
                field_schema=qdrant_models.PayloadSchemaType.KEYWORD,
                wait=True,
            )
            self._index_ensured = True
            logger.info("Ensured payload index on 'workspace_id' for '%s'", self._collection_name)
        except Exception as e:
            logger.warning("Failed to ensure workspace_id payload index: %s", e)

    def _build_workspace_filter(self, workspace_id: UUID) -> qdrant_models.Filter:
        """Build a Qdrant filter that restricts results to a workspace.

        Legacy points without a ``workspace_id`` payload are excluded because
        the filter matches on the field value.
        """
        return qdrant_models.Filter(
            must=[
                qdrant_models.FieldCondition(
                    key="workspace_id",
                    match=qdrant_models.MatchValue(value=str(workspace_id)),
                )
            ]
        )

    async def search_similar(
        self,
        text: str,
        limit: int = 3,
        threshold: float = 0.85,
        workspace_id: UUID | None = None,
    ) -> list[ExtractionExample]:
        """Search for similar extractions by embedding the input text.

        When ``workspace_id`` is provided, only points stored for that workspace
        are returned. Graceful degradation: returns empty list on any failure.
        """
        # Generate embedding
        embedding = await self._embedding_port.embed(text)
        if not embedding:
            return []

        # Get Qdrant client (lazy init)
        client = await self._get_client()
        if client is None:
            return []

        # Search
        try:
            query_filter = (
                self._build_workspace_filter(workspace_id) if workspace_id is not None else None
            )
            search_result = await client.query_points(
                collection_name=self._collection_name,
                query=embedding,
                limit=limit,
                score_threshold=threshold,
                query_filter=query_filter,
                with_payload=True,
            )
        except Exception as e:
            logger.warning("Qdrant search failed: %s", e)
            return []

        # Map results
        examples: list[ExtractionExample] = []
        for point in search_result.points:
            payload = point.payload or {}
            examples.append(
                ExtractionExample(
                    user_story_text=payload.get("user_story_text", ""),
                    tasks_summary=payload.get("tasks_summary", ""),
                    model_used=payload.get("model_used", ""),
                    confidence_score=payload.get("confidence_score"),
                    similarity_score=point.score if point.score is not None else 0.0,
                )
            )

        return examples

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

        ``workspace_id`` is written into the point payload so the point is
        discoverable by workspace-scoped searches. Silently skips on any
        failure (graceful degradation).
        """
        # Generate embedding
        embedding = await self._embedding_port.embed(user_story_text)
        if not embedding:
            return

        # Get Qdrant client (lazy init)
        client = await self._get_client()
        if client is None:
            return

        # Upsert point
        try:
            await client.upsert(
                collection_name=self._collection_name,
                points=[
                    qdrant_models.PointStruct(
                        id=extraction_id,
                        vector=embedding,
                        payload={
                            "user_story_text": user_story_text,
                            "tasks_summary": tasks_summary,
                            "model_used": model_used,
                            "workspace_id": str(workspace_id),
                            "confidence_score": confidence_score,
                            "user_story_id": user_story_id,
                            "created_at": datetime.now(UTC).isoformat(),
                        },
                    )
                ],
            )
        except Exception as e:
            logger.warning("Qdrant store failed: %s", e)
