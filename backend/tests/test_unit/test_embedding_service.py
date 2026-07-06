"""Unit tests for EmbeddingService — VEC-T10.

Uses unittest.mock to mock httpx.AsyncClient so no real network calls happen.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ConnectError, TimeoutException

from storico.infrastructure.vector.embedding_service import EmbeddingService


class TestEmbeddingService:
    """EmbeddingService wraps the Ollama /api/embeddings endpoint.

    Tests use a mock httpx.AsyncClient to avoid real HTTP calls.
    """

    def setup_method(self) -> None:
        self.base_url = "http://localhost:11434"
        self.model = "nomic-embed-text"

    # ── Successful embedding ─────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_embed_success(self) -> None:
        """Successful embedding call returns a vector."""
        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"embedding": [0.1, 0.2, 0.3]}
        mock_client.post.return_value = mock_response

        service = EmbeddingService(
            base_url=self.base_url,
            model=self.model,
            client=mock_client,
        )
        result = await service.embed("Test text")
        assert result == [0.1, 0.2, 0.3]

    @pytest.mark.asyncio
    async def test_embed_returns_correct_dimensions(self) -> None:
        """Embedding vector has expected dimensions."""
        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        expected = [0.1, 0.2, 0.3, 0.4, 0.5]
        mock_response.json.return_value = {"embedding": expected}
        mock_client.post.return_value = mock_response

        service = EmbeddingService(
            base_url=self.base_url,
            model=self.model,
            client=mock_client,
        )
        result = await service.embed("Test")
        assert len(result) == 5

    # ── Empty / whitespace input ─────────────────────────────────────

    @pytest.mark.asyncio
    async def test_embed_empty_text(self) -> None:
        """Empty text returns empty list without calling API."""
        mock_client = AsyncMock()
        service = EmbeddingService(
            base_url=self.base_url,
            model=self.model,
            client=mock_client,
        )
        result = await service.embed("")
        assert result == []
        mock_client.post.assert_not_called()

    @pytest.mark.asyncio
    async def test_embed_whitespace_text(self) -> None:
        """Whitespace-only text returns empty list without calling API."""
        mock_client = AsyncMock()
        service = EmbeddingService(
            base_url=self.base_url,
            model=self.model,
            client=mock_client,
        )
        result = await service.embed("   \n  \t  ")
        assert result == []
        mock_client.post.assert_not_called()

    # ── Connection errors (graceful degradation) ─────────────────────

    @pytest.mark.asyncio
    async def test_embed_connection_error(self) -> None:
        """Connection error returns empty list gracefully."""
        mock_client = AsyncMock()
        mock_client.post.side_effect = ConnectError("Connection refused")

        service = EmbeddingService(
            base_url=self.base_url,
            model=self.model,
            client=mock_client,
        )
        result = await service.embed("Test text")
        assert result == []

    @pytest.mark.asyncio
    async def test_embed_timeout(self) -> None:
        """Timeout returns empty list gracefully."""
        mock_client = AsyncMock()
        mock_client.post.side_effect = TimeoutException("Timed out")

        service = EmbeddingService(
            base_url=self.base_url,
            model=self.model,
            client=mock_client,
        )
        result = await service.embed("Test text")
        assert result == []

    # ── HTTP error responses (graceful degradation) ───────────────────

    @pytest.mark.asyncio
    async def test_embed_model_not_found_404(self) -> None:
        """404 from Ollama returns empty list gracefully."""
        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_client.post.return_value = mock_response

        service = EmbeddingService(
            base_url=self.base_url,
            model=self.model,
            client=mock_client,
        )
        result = await service.embed("Test text")
        assert result == []

    @pytest.mark.asyncio
    async def test_embed_http_500_returns_empty(self) -> None:
        """500 from Ollama returns empty list gracefully."""
        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"
        mock_client.post.return_value = mock_response

        service = EmbeddingService(
            base_url=self.base_url,
            model=self.model,
            client=mock_client,
        )
        result = await service.embed("Test text")
        assert result == []

    # ── Malformed response ───────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_embed_malformed_response(self) -> None:
        """Malformed JSON response returns empty list gracefully."""
        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.side_effect = ValueError("Invalid JSON")

        service = EmbeddingService(
            base_url=self.base_url,
            model=self.model,
            client=mock_client,
        )
        result = await service.embed("Test text")
        assert result == []

    @pytest.mark.asyncio
    async def test_embed_missing_embedding_key(self) -> None:
        """Response missing 'embedding' key returns empty list."""
        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"wrong_key": "value"}

        service = EmbeddingService(
            base_url=self.base_url,
            model=self.model,
            client=mock_client,
        )
        result = await service.embed("Test text")
        assert result == []

    @pytest.mark.asyncio
    async def test_embed_empty_embedding_list(self) -> None:
        """Empty embedding list in response returns empty list."""
        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"embedding": []}

        service = EmbeddingService(
            base_url=self.base_url,
            model=self.model,
            client=mock_client,
        )
        result = await service.embed("Test text")
        assert result == []

    # ── Batch embedding ──────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_embed_batch(self) -> None:
        """Batch embedding returns embeddings for each text."""
        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"embedding": [0.1, 0.2]}

        # Each call returns the same response
        mock_client.post.return_value = mock_response

        service = EmbeddingService(
            base_url=self.base_url,
            model=self.model,
            client=mock_client,
        )
        results = await service.embed_batch(["Text A", "Text B"])
        assert len(results) == 2
        assert results[0] == [0.1, 0.2]
        assert results[1] == [0.1, 0.2]

    @pytest.mark.asyncio
    async def test_embed_batch_empty_list(self) -> None:
        """Batch embedding with empty list returns empty list."""
        service = EmbeddingService(
            base_url=self.base_url,
            model=self.model,
        )
        results = await service.embed_batch([])
        assert results == []
