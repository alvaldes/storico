"""QdrantAdapter — VectorStorePort implementation using Qdrant vector database."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from qdrant_client import QdrantClient
from qdrant_client.http import models as qdrant_models

from storico.domain.ports import ExtractionExample, VectorStorePort
from storico.infrastructure.vector.embedding_service import EmbeddingService

logger = logging.getLogger(__name__)


class QdrantAdapter(VectorStorePort):
    """VectorStorePort implementation backed by Qdrant.

    Features:
    - Lazy client initialization (first use, not constructor)
    - Auto-creates collection on first use if missing
    - Graceful degradation: empty results on failure

    Collection schema (storico_extractions):
        - vector: 768d float array (nomic-embed-text)
        - payload: user_story_text, tasks_summary, model_used,
                   confidence_score, created_at, user_story_id
    """

    def __init__(
        self,
        embedding_service: EmbeddingService,
        qdrant_url: str = "http://localhost:6333",
        collection_name: str = "storico_extractions",
        vector_size: int = 768,
        distance: qdrant_models.Distance = qdrant_models.Distance.COSINE,
    ) -> None:
        self._embedding_service = embedding_service
        self._qdrant_url = qdrant_url
        self._collection_name = collection_name
        self._vector_size = vector_size
        self._distance = distance
        self._client: QdrantClient | None = None

    def _get_client(self) -> QdrantClient | None:
        """Lazy init — creates client + ensures collection on first call.

        Returns None if connection fails (graceful degradation).
        """
        if self._client is not None:
            return self._client

        try:
            self._client = QdrantClient(url=self._qdrant_url, timeout=10.0)
            # Check if collection exists, create if not
            collections = self._client.get_collections()
            existing = {c.name for c in collections.collections}

            if self._collection_name not in existing:
                self._client.create_collection(
                    collection_name=self._collection_name,
                    vectors_config=qdrant_models.VectorParams(
                        size=self._vector_size,
                        distance=self._distance,
                    ),
                )
                logger.info("Created Qdrant collection '%s'", self._collection_name)

            return self._client
        except Exception as e:
            logger.warning("Failed to initialize Qdrant client: %s", e)
            self._client = None
            return None

    async def search_similar(
        self,
        text: str,
        limit: int = 3,
        threshold: float = 0.85,
    ) -> list[ExtractionExample]:
        """Search for similar extractions by embedding the input text.

        Graceful degradation: returns empty list on any failure.
        """
        # Generate embedding
        embedding = await self._embedding_service.embed(text)
        if not embedding:
            return []

        # Get Qdrant client (lazy init)
        client = self._get_client()
        if client is None:
            return []

        # Search
        try:
            search_result = client.search(
                collection_name=self._collection_name,
                query_vector=embedding,
                limit=limit,
                score_threshold=threshold,
            )
        except Exception as e:
            logger.warning("Qdrant search failed: %s", e)
            return []

        # Map results
        examples: list[ExtractionExample] = []
        for point in search_result:
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
        extraction_id: str,
        user_story_text: str,
        tasks_summary: str,
        model_used: str,
        confidence_score: float | None = None,
        user_story_id: str = "",
    ) -> None:
        """Store an extraction with its embedding for future RAG searches.

        Silently skips on any failure (graceful degradation).
        """
        # Generate embedding
        embedding = await self._embedding_service.embed(user_story_text)
        if not embedding:
            return

        # Get Qdrant client (lazy init)
        client = self._get_client()
        if client is None:
            return

        # Upsert point
        try:
            client.upsert(
                collection_name=self._collection_name,
                points=[
                    qdrant_models.PointStruct(
                        id=extraction_id,
                        vector=embedding,
                        payload={
                            "user_story_text": user_story_text,
                            "tasks_summary": tasks_summary,
                            "model_used": model_used,
                            "confidence_score": confidence_score,
                            "user_story_id": user_story_id,
                            "created_at": datetime.now(timezone.utc).isoformat(),
                        },
                    )
                ],
            )
        except Exception as e:
            logger.warning("Qdrant store failed: %s", e)
