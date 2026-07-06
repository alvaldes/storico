"""Unit tests for QdrantAdapter — VEC-T11.

Uses unittest.mock to mock QdrantClient and EmbeddingService
so no real network calls or databases are needed.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from storico.domain.ports import ExtractionExample
from storico.infrastructure.vector.qdrant_adapter import QdrantAdapter


class TestQdrantAdapter:
    """QdrantAdapter implements VectorStorePort backed by Qdrant.

    Tests mock both EmbeddingService and QdrantClient.
    """

    def setup_method(self) -> None:
        self.mock_embedding = AsyncMock()
        self.collection = "test_storico_extractions"
        self.qdrant_url = "http://localhost:6333"

    # ── search_similar — success ────────────────────────────────────

    @pytest.mark.asyncio
    async def test_search_similar_success(self) -> None:
        """Successful search returns ExtractionExample list."""
        self.mock_embedding.embed.return_value = [0.1, 0.2, 0.3]

        mock_point = MagicMock()
        mock_point.score = 0.92
        mock_point.payload = {
            "user_story_text": "As a user, I want login",
            "tasks_summary": "1. Implement auth\n2. Create login form",
            "model_used": "llama3.2",
            "confidence_score": 0.85,
        }

        adapter = QdrantAdapter(
            embedding_service=self.mock_embedding,
            qdrant_url=self.qdrant_url,
            collection_name=self.collection,
            vector_size=3,
        )

        # Mock the internal QdrantClient
        mock_client = MagicMock()
        mock_client.search.return_value = [mock_point]
        mock_client.get_collections.return_value = MagicMock(
            collections=[]
        )
        adapter._client = mock_client

        results = await adapter.search_similar(
            text="As a user, I want login",
            limit=3,
            threshold=0.85,
        )

        assert len(results) == 1
        assert results[0].user_story_text == "As a user, I want login"
        assert results[0].similarity_score == 0.92
        assert results[0].confidence_score == 0.85

    @pytest.mark.asyncio
    async def test_search_similar_empty(self) -> None:
        """Empty search results return empty list."""
        self.mock_embedding.embed.return_value = [0.1, 0.2, 0.3]

        adapter = QdrantAdapter(
            embedding_service=self.mock_embedding,
            qdrant_url=self.qdrant_url,
            collection_name=self.collection,
            vector_size=3,
        )

        mock_client = MagicMock()
        mock_client.search.return_value = []
        mock_client.get_collections.return_value = MagicMock(
            collections=[]
        )
        adapter._client = mock_client

        results = await adapter.search_similar(text="test")
        assert results == []

    # ── search_similar — graceful degradation ────────────────────────

    @pytest.mark.asyncio
    async def test_search_similar_embedding_fails(self) -> None:
        """Embedding failure returns empty list gracefully."""
        self.mock_embedding.embed.return_value = []

        adapter = QdrantAdapter(
            embedding_service=self.mock_embedding,
            qdrant_url=self.qdrant_url,
            collection_name=self.collection,
        )

        results = await adapter.search_similar(text="test")
        assert results == []

    @pytest.mark.asyncio
    async def test_search_similar_qdrant_error(self) -> None:
        """Qdrant search error returns empty list gracefully."""
        self.mock_embedding.embed.return_value = [0.1, 0.2, 0.3]

        adapter = QdrantAdapter(
            embedding_service=self.mock_embedding,
            qdrant_url=self.qdrant_url,
            collection_name=self.collection,
            vector_size=3,
        )

        mock_client = MagicMock()
        mock_client.search.side_effect = RuntimeError("Qdrant down")
        mock_client.get_collections.return_value = MagicMock(
            collections=[]
        )
        adapter._client = mock_client

        results = await adapter.search_similar(text="test")
        assert results == []

    # ── store_extraction — success ───────────────────────────────────

    @pytest.mark.asyncio
    async def test_store_extraction_success(self) -> None:
        """Successful store calls upsert with correct payload."""
        self.mock_embedding.embed.return_value = [0.1, 0.2, 0.3]

        adapter = QdrantAdapter(
            embedding_service=self.mock_embedding,
            qdrant_url=self.qdrant_url,
            collection_name=self.collection,
            vector_size=3,
        )

        mock_client = MagicMock()
        mock_client.get_collections.return_value = MagicMock(
            collections=[]
        )
        adapter._client = mock_client

        await adapter.store_extraction(
            extraction_id="ext-123",
            user_story_text="As a user, I want login",
            tasks_summary="1. Implement auth",
            model_used="llama3.2",
            confidence_score=0.85,
            user_story_id="story-456",
        )

        # Verify upsert was called
        mock_client.upsert.assert_called_once()
        call_args = mock_client.upsert.call_args[1]
        assert call_args["collection_name"] == self.collection
        points = call_args["points"]
        assert len(points) == 1
        assert points[0].id == "ext-123"
        assert points[0].vector == [0.1, 0.2, 0.3]
        assert points[0].payload["model_used"] == "llama3.2"

    # ── store_extraction — graceful degradation ──────────────────────

    @pytest.mark.asyncio
    async def test_store_extraction_embedding_fails(self) -> None:
        """Embedding failure silently skips store (no qdrant call)."""
        self.mock_embedding.embed.return_value = []

        adapter = QdrantAdapter(
            embedding_service=self.mock_embedding,
            qdrant_url=self.qdrant_url,
            collection_name=self.collection,
        )

        mock_client = MagicMock()
        adapter._client = mock_client

        await adapter.store_extraction(
            extraction_id="ext-123",
            user_story_text="test",
            tasks_summary="tasks",
            model_used="test",
        )

        # Qdrant upsert should NOT be called
        mock_client.upsert.assert_not_called()

    @pytest.mark.asyncio
    async def test_store_extraction_qdrant_error(self) -> None:
        """Qdrant error silently skips store (graceful degradation)."""
        self.mock_embedding.embed.return_value = [0.1, 0.2, 0.3]

        adapter = QdrantAdapter(
            embedding_service=self.mock_embedding,
            qdrant_url=self.qdrant_url,
            collection_name=self.collection,
            vector_size=3,
        )

        mock_client = MagicMock()
        mock_client.upsert.side_effect = RuntimeError("Qdrant down")
        mock_client.get_collections.return_value = MagicMock(
            collections=[]
        )
        adapter._client = mock_client

        # Should not raise
        await adapter.store_extraction(
            extraction_id="ext-123",
            user_story_text="test",
            tasks_summary="tasks",
            model_used="test",
        )

    # ── Lazy init ────────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_lazy_init_creates_collection(self) -> None:
        """Collection created on first use if it doesn't exist."""
        self.mock_embedding.embed.return_value = [0.1, 0.2, 0.3]

        adapter = QdrantAdapter(
            embedding_service=self.mock_embedding,
            qdrant_url=self.qdrant_url,
            collection_name=self.collection,
            vector_size=3,
        )

        # First call should trigger lazy init
        mock_client = MagicMock()
        mock_get_collections = MagicMock()
        mock_get_collections.collections = []
        mock_client.get_collections.return_value = mock_get_collections

        with patch.object(adapter, "_get_client", return_value=mock_client):
            await adapter.store_extraction(
                extraction_id="ext-1",
                user_story_text="test",
                tasks_summary="tasks",
                model_used="test",
            )

        # Verify search went through mock client
        mock_client.upsert.assert_called_once()

    @pytest.mark.asyncio
    async def test_lazy_init_connection_error(self) -> None:
        """Connection error during lazy init returns None, methods return empty."""
        adapter = QdrantAdapter(
            embedding_service=self.mock_embedding,
            qdrant_url="http://invalid:6333",
            collection_name=self.collection,
        )

        # Force _client to None and _get_client to fail
        adapter._client = None

        # Since we can't actually connect, _get_client will raise
        # But search_similar and store_extraction should handle it
        results = await adapter.search_similar(text="test")
        assert results == []

        # store should also handle it silently
        await adapter.store_extraction(
            extraction_id="ext-1",
            user_story_text="test",
            tasks_summary="tasks",
            model_used="test",
        )

    # ── Payload structure ────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_store_extraction_payload_has_all_fields(self) -> None:
        """Stored point payload contains all expected fields."""
        self.mock_embedding.embed.return_value = [0.1, 0.2, 0.3]

        adapter = QdrantAdapter(
            embedding_service=self.mock_embedding,
            qdrant_url=self.qdrant_url,
            collection_name=self.collection,
            vector_size=3,
        )

        mock_client = MagicMock()
        mock_client.get_collections.return_value = MagicMock(
            collections=[]
        )
        adapter._client = mock_client

        await adapter.store_extraction(
            extraction_id="ext-1",
            user_story_text="story text",
            tasks_summary="task list",
            model_used="llama3.2",
            confidence_score=0.9,
            user_story_id="story-1",
        )

        call_args = mock_client.upsert.call_args[1]
        point = call_args["points"][0]
        payload = point.payload
        assert payload["user_story_text"] == "story text"
        assert payload["tasks_summary"] == "task list"
        assert payload["model_used"] == "llama3.2"
        assert payload["confidence_score"] == 0.9
        assert payload["user_story_id"] == "story-1"
        assert "created_at" in payload

    @pytest.mark.asyncio
    async def test_search_similar_maps_null_score(self) -> None:
        """Null score in qdrant result maps to 0.0 similarity."""
        self.mock_embedding.embed.return_value = [0.1, 0.2, 0.3]

        adapter = QdrantAdapter(
            embedding_service=self.mock_embedding,
            qdrant_url=self.qdrant_url,
            collection_name=self.collection,
            vector_size=3,
        )

        mock_point = MagicMock()
        mock_point.score = None  # null score
        mock_point.payload = {
            "user_story_text": "test",
            "tasks_summary": "tasks",
            "model_used": "test",
        }

        mock_client = MagicMock()
        mock_client.search.return_value = [mock_point]
        mock_client.get_collections.return_value = MagicMock(
            collections=[]
        )
        adapter._client = mock_client

        results = await adapter.search_similar(text="test")
        assert len(results) == 1
        assert results[0].similarity_score == 0.0
