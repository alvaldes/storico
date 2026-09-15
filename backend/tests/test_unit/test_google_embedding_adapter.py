"""Unit tests for GoogleEmbeddingAdapter."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from storico.infrastructure.vector.google_embedding_adapter import GoogleEmbeddingAdapter


@pytest.mark.unit
def test_google_embedding_adapter_dimensions() -> None:
    """GoogleEmbeddingAdapter reports configured dimensions."""
    assert GoogleEmbeddingAdapter(api_key="test-key", dimensions=768).dimensions == 768
    assert GoogleEmbeddingAdapter(api_key="test-key", dimensions=512).dimensions == 512


@pytest.mark.unit
async def test_google_embedding_adapter_embed_success() -> None:
    """GoogleEmbeddingAdapter.embed returns embedding from mocked client."""
    mock_response = MagicMock()
    mock_response.embeddings = [MagicMock()]
    mock_response.embeddings[0].values = [0.1, 0.2, 0.3]

    mock_client = MagicMock()
    mock_client.models.embed_content.return_value = mock_response

    with patch(
        "storico.infrastructure.vector.google_embedding_adapter.genai.Client",
        return_value=mock_client,
    ):
        adapter = GoogleEmbeddingAdapter(api_key="test-key")
        embedding = await adapter.embed("hello world")

    assert embedding == [0.1, 0.2, 0.3]
    mock_client.models.embed_content.assert_called_once()


@pytest.mark.unit
async def test_google_embedding_adapter_embed_empty_text() -> None:
    """GoogleEmbeddingAdapter.embed returns empty list for empty text."""
    adapter = GoogleEmbeddingAdapter(api_key="test-key")
    assert await adapter.embed("") == []
    assert await adapter.embed("   ") == []


@pytest.mark.unit
async def test_google_embedding_adapter_embed_api_failure() -> None:
    """GoogleEmbeddingAdapter.embed returns empty list on API failure."""
    with patch(
        "storico.infrastructure.vector.google_embedding_adapter.genai.Client"
    ) as mock_client_class:
        mock_client = MagicMock()
        mock_client.models.embed_content.side_effect = Exception("API error")
        mock_client_class.return_value = mock_client

        adapter = GoogleEmbeddingAdapter(api_key="test-key")
        embedding = await adapter.embed("hello world")

    assert embedding == []
    mock_client.models.embed_content.assert_called_once()
