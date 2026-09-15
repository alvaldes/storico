"""Unit tests for OpenAIEmbeddingAdapter."""

from __future__ import annotations

import sys

sys.path.insert(0, '../../src')

from unittest.mock import AsyncMock, patch

import pytest

from storico.infrastructure.vector.openai_embedding_adapter import OpenAIEmbeddingAdapter


@pytest.mark.unit
def test_openai_embedding_adapter_dimensions() -> None:
    """OpenAIEmbeddingAdapter reports configured dimensions."""
    adapter = OpenAIEmbeddingAdapter(api_key="test-key", dimensions=768)
    assert adapter.dimensions == 768
    adapter2 = OpenAIEmbeddingAdapter(api_key="test-key", dimensions=512)
    assert adapter2.dimensions == 512


@pytest.mark.unit
async def test_openai_embedding_adapter_embed_success() -> None:
    """OpenAIEmbeddingAdapter.embed returns embedding from mocked client."""
    # Mock the AsyncOpenAI client and its embeddings.create method
    mock_response = AsyncMock()
    mock_response.data = [AsyncMock()]
    mock_response.data[0].embedding = [0.1, 0.2, 0.3]

    mock_client = AsyncMock()
    mock_client.embeddings.create.return_value = mock_response

    with patch("storico.infrastructure.vector.openai_embedding_adapter.AsyncOpenAI", return_value=mock_client):
        adapter = OpenAIEmbeddingAdapter(api_key="test-key")
        embedding = await adapter.embed("hello world")
        assert embedding == [0.1, 0.2, 0.3]
        mock_client.embeddings.create.assert_awaited_once()


@pytest.mark.unit
async def test_openai_embedding_adapter_embed_empty_text() -> None:
    """OpenAIEmbeddingAdapter.embed returns empty list for empty text."""
    adapter = OpenAIEmbeddingAdapter(api_key="test-key")
    embedding = await adapter.embed("")
    assert embedding == []
    embedding = await adapter.embed("   ")
    assert embedding == []


@pytest.mark.unit
async def test_openai_embedding_adapter_embed_api_failure() -> None:
    """OpenAIEmbeddingAdapter.embed returns empty list on API failure."""
    with patch("storico.infrastructure.vector.openai_embedding_adapter.AsyncOpenAI") as mock_client_class:
        mock_client = AsyncMock()
        mock_client.embeddings.create.side_effect = Exception("API error")
        mock_client_class.return_value = mock_client

        adapter = OpenAIEmbeddingAdapter(api_key="test-key")
        embedding = await adapter.embed("hello world")
        assert embedding == []
        mock_client.embeddings.create.assert_awaited_once()