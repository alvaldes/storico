"""Unit tests for QdrantAdapter — VEC-T11.

Uses unittest.mock to mock AsyncQdrantClient and EmbeddingPort
so no real network calls or databases are needed.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from storico.infrastructure.vector.qdrant_adapter import QdrantAdapter


def _make_embedding_port(dimensions: int = 3):
    """Build a mock EmbeddingPort with the given dimensions."""
    port = MagicMock()
    port.dimensions = dimensions
    port.embed = AsyncMock()
    return port


def _make_query_response(points):
    """Build a QueryResponse-like object carrying the given scored points."""
    response = MagicMock()
    response.points = points
    return response


class TestQdrantAdapter:
    """QdrantAdapter implements VectorStorePort backed by Qdrant.

    Tests mock both EmbeddingPort and AsyncQdrantClient.
    """

    def setup_method(self) -> None:
        self.workspace_id = uuid4()
        self.collection = "test_storico_extractions"
        self.qdrant_url = "http://localhost:6333"

    # ── search_similar — success ────────────────────────────────────

    @pytest.mark.asyncio
    async def test_search_similar_success(self) -> None:
        """Successful search returns ExtractionExample list."""
        port = _make_embedding_port()
        port.embed.return_value = [0.1, 0.2, 0.3]

        mock_point = MagicMock()
        mock_point.score = 0.92
        mock_point.payload = {
            "user_story_text": "As a user, I want login",
            "tasks_summary": "1. Implement auth\n2. Create login form",
            "model_used": "llama3.2",
            "confidence_score": 0.85,
            "workspace_id": str(self.workspace_id),
        }

        adapter = QdrantAdapter(
            embedding_port=port,
            qdrant_url=self.qdrant_url,
            collection_name=self.collection,
            vector_size=3,
        )

        # Mock the internal AsyncQdrantClient
        mock_client = AsyncMock()
        mock_client.get_collections.return_value = MagicMock(collections=[])
        mock_client.create_payload_index = AsyncMock()
        mock_client.query_points.return_value = _make_query_response([mock_point])
        adapter._client = mock_client

        results = await adapter.search_similar(
            text="As a user, I want login",
            limit=3,
            threshold=0.85,
            workspace_id=self.workspace_id,
        )

        assert len(results) == 1
        assert results[0].user_story_text == "As a user, I want login"
        assert results[0].similarity_score == 0.92
        assert results[0].confidence_score == 0.85

    @pytest.mark.asyncio
    async def test_search_similar_uses_workspace_filter(self) -> None:
        """The search sends a filter scoped to the workspace id."""
        port = _make_embedding_port()
        port.embed.return_value = [0.1, 0.2, 0.3]

        adapter = QdrantAdapter(
            embedding_port=port,
            qdrant_url=self.qdrant_url,
            collection_name=self.collection,
            vector_size=3,
        )

        mock_client = AsyncMock()
        mock_client.get_collections.return_value = MagicMock(collections=[])
        mock_client.create_payload_index = AsyncMock()
        mock_client.query_points.return_value = _make_query_response([])
        adapter._client = mock_client

        await adapter.search_similar(
            text="test",
            workspace_id=self.workspace_id,
        )

        mock_client.query_points.assert_called_once()
        call_kwargs = mock_client.query_points.call_args[1]
        query_filter = call_kwargs["query_filter"]
        # The filter restricts results to this workspace
        assert query_filter.must[0].key == "workspace_id"
        assert query_filter.must[0].match.value == str(self.workspace_id)

    @pytest.mark.asyncio
    async def test_search_similar_without_workspace_sends_no_filter(self) -> None:
        """No workspace id means no filter (unchanged legacy search path)."""
        port = _make_embedding_port()
        port.embed.return_value = [0.1, 0.2, 0.3]

        adapter = QdrantAdapter(
            embedding_port=port,
            qdrant_url=self.qdrant_url,
            collection_name=self.collection,
            vector_size=3,
        )

        mock_client = AsyncMock()
        mock_client.query_points.return_value = _make_query_response([])
        adapter._client = mock_client

        await adapter.search_similar(text="test")

        call_kwargs = mock_client.query_points.call_args[1]
        assert call_kwargs["query_filter"] is None

    @pytest.mark.asyncio
    async def test_search_similar_empty(self) -> None:
        """Empty search results return empty list."""
        port = _make_embedding_port()
        port.embed.return_value = [0.1, 0.2, 0.3]

        adapter = QdrantAdapter(
            embedding_port=port,
            qdrant_url=self.qdrant_url,
            collection_name=self.collection,
            vector_size=3,
        )

        mock_client = AsyncMock()
        mock_client.query_points.return_value = _make_query_response([])
        adapter._client = mock_client

        results = await adapter.search_similar(text="test")
        assert results == []

    # ── search_similar — graceful degradation ────────────────────────

    @pytest.mark.asyncio
    async def test_search_similar_embedding_fails(self) -> None:
        """Embedding failure returns empty list gracefully."""
        port = _make_embedding_port()
        port.embed.return_value = []

        adapter = QdrantAdapter(
            embedding_port=port,
            qdrant_url=self.qdrant_url,
            collection_name=self.collection,
        )

        results = await adapter.search_similar(text="test")
        assert results == []

    @pytest.mark.asyncio
    async def test_search_similar_qdrant_error(self) -> None:
        """Qdrant search error returns empty list gracefully."""
        port = _make_embedding_port()
        port.embed.return_value = [0.1, 0.2, 0.3]

        adapter = QdrantAdapter(
            embedding_port=port,
            qdrant_url=self.qdrant_url,
            collection_name=self.collection,
            vector_size=3,
        )

        mock_client = AsyncMock()
        mock_client.query_points.side_effect = RuntimeError("Qdrant down")
        adapter._client = mock_client

        results = await adapter.search_similar(text="test")
        assert results == []

    # ── store_extraction — success ───────────────────────────────────

    @pytest.mark.asyncio
    async def test_store_extraction_success(self) -> None:
        """Successful store calls upsert with correct payload."""
        port = _make_embedding_port()
        port.embed.return_value = [0.1, 0.2, 0.3]

        adapter = QdrantAdapter(
            embedding_port=port,
            qdrant_url=self.qdrant_url,
            collection_name=self.collection,
            vector_size=3,
        )

        mock_client = AsyncMock()
        mock_client.get_collections.return_value = MagicMock(collections=[])
        mock_client.create_payload_index = AsyncMock()
        adapter._client = mock_client

        await adapter.store_extraction(
            extraction_id="ext-123",
            user_story_text="As a user, I want login",
            tasks_summary="1. Implement auth",
            model_used="llama3.2",
            workspace_id=self.workspace_id,
            confidence_score=0.85,
            user_story_id="story-456",
        )

        mock_client.upsert.assert_called_once()
        call_args = mock_client.upsert.call_args[1]
        assert call_args["collection_name"] == self.collection
        points = call_args["points"]
        assert len(points) == 1
        assert points[0].id == "ext-123"
        assert points[0].vector == [0.1, 0.2, 0.3]
        assert points[0].payload["model_used"] == "llama3.2"

    @pytest.mark.asyncio
    async def test_store_extraction_writes_workspace_id(self) -> None:
        """Stored point payload contains the workspace_id."""
        port = _make_embedding_port()
        port.embed.return_value = [0.1, 0.2, 0.3]

        adapter = QdrantAdapter(
            embedding_port=port,
            qdrant_url=self.qdrant_url,
            collection_name=self.collection,
            vector_size=3,
        )

        mock_client = AsyncMock()
        mock_client.get_collections.return_value = MagicMock(collections=[])
        mock_client.create_payload_index = AsyncMock()
        adapter._client = mock_client

        await adapter.store_extraction(
            extraction_id="ext-1",
            user_story_text="story text",
            tasks_summary="task list",
            model_used="llama3.2",
            workspace_id=self.workspace_id,
        )

        call_args = mock_client.upsert.call_args[1]
        payload = call_args["points"][0].payload
        assert payload["workspace_id"] == str(self.workspace_id)

    # ── store_extraction — graceful degradation ──────────────────────

    @pytest.mark.asyncio
    async def test_store_extraction_embedding_fails(self) -> None:
        """Embedding failure silently skips store (no qdrant call)."""
        port = _make_embedding_port()
        port.embed.return_value = []

        adapter = QdrantAdapter(
            embedding_port=port,
            qdrant_url=self.qdrant_url,
            collection_name=self.collection,
        )

        mock_client = AsyncMock()
        adapter._client = mock_client

        await adapter.store_extraction(
            extraction_id="ext-123",
            user_story_text="test",
            tasks_summary="tasks",
            model_used="test",
            workspace_id=self.workspace_id,
        )

        mock_client.upsert.assert_not_called()

    @pytest.mark.asyncio
    async def test_store_extraction_qdrant_error(self) -> None:
        """Qdrant error silently skips store (graceful degradation)."""
        port = _make_embedding_port()
        port.embed.return_value = [0.1, 0.2, 0.3]

        adapter = QdrantAdapter(
            embedding_port=port,
            qdrant_url=self.qdrant_url,
            collection_name=self.collection,
            vector_size=3,
        )

        mock_client = AsyncMock()
        mock_client.upsert.side_effect = RuntimeError("Qdrant down")
        adapter._client = mock_client

        await adapter.store_extraction(
            extraction_id="ext-123",
            user_story_text="test",
            tasks_summary="tasks",
            model_used="test",
            workspace_id=self.workspace_id,
        )

    # ── Lazy init / collection ensure ─────────────────────────────────

    @pytest.mark.asyncio
    async def test_lazy_init_creates_collection_and_index(self) -> None:
        """Collection and payload index created on first use if missing."""
        port = _make_embedding_port()
        port.embed.return_value = [0.1, 0.2, 0.3]

        adapter = QdrantAdapter(
            embedding_port=port,
            qdrant_url=self.qdrant_url,
            collection_name=self.collection,
            vector_size=3,
        )

        mock_client = AsyncMock()
        mock_get_collections = MagicMock()
        mock_get_collections.collections = []
        mock_client.get_collections.return_value = mock_get_collections
        mock_client.create_payload_index = AsyncMock()

        with patch(
            "storico.infrastructure.vector.qdrant_adapter.AsyncQdrantClient",
            return_value=mock_client,
        ):
            client = await adapter._get_client()

        assert client is mock_client
        mock_client.create_collection.assert_called_once()
        mock_client.create_payload_index.assert_called_once()
        # Index is created with the keyword schema on workspace_id
        idx_call = mock_client.create_payload_index.call_args[1]
        assert idx_call["field_name"] == "workspace_id"

    @pytest.mark.asyncio
    async def test_existing_collection_skips_create_but_ensures_index(self) -> None:
        """Existing collection is not recreated; payload index still ensured."""
        port = _make_embedding_port()
        port.embed.return_value = [0.1, 0.2, 0.3]

        adapter = QdrantAdapter(
            embedding_port=port,
            qdrant_url=self.qdrant_url,
            collection_name=self.collection,
            vector_size=3,
        )

        mock_client = AsyncMock()
        mock_get_collections = MagicMock()
        mock_get_collections.collections = [SimpleNamespace(name=self.collection)]
        mock_client.get_collections.return_value = mock_get_collections
        mock_client.create_payload_index = AsyncMock()

        with patch(
            "storico.infrastructure.vector.qdrant_adapter.AsyncQdrantClient",
            return_value=mock_client,
        ):
            client = await adapter._get_client()

        assert client is mock_client
        mock_client.create_collection.assert_not_called()
        mock_client.create_payload_index.assert_called_once()

    @pytest.mark.asyncio
    async def test_dimension_mismatch_raises(self) -> None:
        """A provider whose dimensions differ from the collection fails fast."""
        port = _make_embedding_port(dimensions=1536)
        adapter = QdrantAdapter(
            embedding_port=port,
            qdrant_url=self.qdrant_url,
            collection_name=self.collection,
            vector_size=768,
        )
        # Force a fresh lazy init so dimensions are validated before any client
        # connection attempt.
        adapter._client = None

        with pytest.raises(ValueError, match="dimensions"):
            await adapter.search_similar(text="test", workspace_id=self.workspace_id)

    @pytest.mark.asyncio
    async def test_lazy_init_connection_error_returns_empty(self) -> None:
        """Connection error during lazy init returns None; methods return empty."""
        port = _make_embedding_port(dimensions=768)
        port.embed.return_value = [0.1, 0.2, 0.3]

        adapter = QdrantAdapter(
            embedding_port=port,
            qdrant_url="http://invalid:6333",
            collection_name=self.collection,
        )
        # Force a fresh lazy init and make the client connection fail gracefully.
        adapter._client = None

        with patch(
            "storico.infrastructure.vector.qdrant_adapter.AsyncQdrantClient",
            side_effect=RuntimeError("connection refused"),
        ):
            results = await adapter.search_similar(text="test")
            assert results == []

            await adapter.store_extraction(
                extraction_id="ext-1",
                user_story_text="test",
                tasks_summary="tasks",
                model_used="test",
                workspace_id=self.workspace_id,
            )

    # ── Payload structure ────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_store_extraction_payload_has_all_fields(self) -> None:
        """Stored point payload contains all expected fields."""
        port = _make_embedding_port()
        port.embed.return_value = [0.1, 0.2, 0.3]

        adapter = QdrantAdapter(
            embedding_port=port,
            qdrant_url=self.qdrant_url,
            collection_name=self.collection,
            vector_size=3,
        )

        mock_client = AsyncMock()
        adapter._client = mock_client

        await adapter.store_extraction(
            extraction_id="ext-1",
            user_story_text="story text",
            tasks_summary="task list",
            model_used="llama3.2",
            workspace_id=self.workspace_id,
            confidence_score=0.9,
            user_story_id="story-1",
        )

        call_args = mock_client.upsert.call_args[1]
        payload = call_args["points"][0].payload
        assert payload["user_story_text"] == "story text"
        assert payload["tasks_summary"] == "task list"
        assert payload["model_used"] == "llama3.2"
        assert payload["workspace_id"] == str(self.workspace_id)
        assert payload["confidence_score"] == 0.9
        assert payload["user_story_id"] == "story-1"
        assert "created_at" in payload

    @pytest.mark.asyncio
    async def test_search_similar_maps_null_score(self) -> None:
        """Null score in qdrant result maps to 0.0 similarity."""
        port = _make_embedding_port()
        port.embed.return_value = [0.1, 0.2, 0.3]

        adapter = QdrantAdapter(
            embedding_port=port,
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

        mock_client = AsyncMock()
        mock_client.query_points.return_value = _make_query_response([mock_point])
        adapter._client = mock_client

        results = await adapter.search_similar(text="test", workspace_id=self.workspace_id)
        assert len(results) == 1
        assert results[0].similarity_score == 0.0
