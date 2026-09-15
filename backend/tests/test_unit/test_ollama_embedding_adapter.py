"""Unit tests for OllamaEmbeddingAdapter."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from storico.infrastructure.vector.ollama_embedding_adapter import OllamaEmbeddingAdapter


@pytest.mark.unit
def test_ollama_embedding_adapter_dimensions() -> None:
    """OllamaEmbeddingAdapter reports fixed 768 dimensions."""
    adapter = OllamaEmbeddingAdapter()
    assert adapter.dimensions == 768


@pytest.mark.unit
async def test_ollama_embedding_adapter_embed_success() -> None:
    """OllamaEmbeddingAdapter.embed returns embedding from wrapped service."""
    mock_service = AsyncMock()
    mock_service.embed.return_value = [0.1, 0.2, 0.3]
    adapter = OllamaEmbeddingAdapter()
    adapter._service = mock_service  # type: ignore[assignment]

    embedding = await adapter.embed("hello world")

    assert embedding == [0.1, 0.2, 0.3]
    assert mock_service.embed.await_count == 1
    assert mock_service.embed.await_args[0][0] == "hello world"


@pytest.mark.unit
async def test_ollama_embedding_adapter_embed_empty_text() -> None:
    """OllamaEmbeddingAdapter.embed returns empty list for empty text."""
    adapter = OllamaEmbeddingAdapter()
    assert await adapter.embed("") == []
    assert await adapter.embed("   ") == []


@pytest.mark.unit
async def test_ollama_embedding_adapter_embed_service_failure() -> None:
    """OllamaEmbeddingAdapter.embed returns empty list on service failure."""
    mock_service = AsyncMock()
    mock_service.embed.side_effect = Exception("Service down")
    adapter = OllamaEmbeddingAdapter()
    adapter._service = mock_service  # type: ignore[assignment]

    embedding = await adapter.embed("hello world")

    assert embedding == []
    assert mock_service.embed.await_count == 1
    assert mock_service.embed.await_args[0][0] == "hello world"
