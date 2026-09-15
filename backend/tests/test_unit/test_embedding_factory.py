"""Unit tests for embedding factory."""

from __future__ import annotations

import sys

sys.path.insert(0, '../../src')

from unittest.mock import MagicMock

import pytest

from storico.config.settings import Settings
from storico.infrastructure.vector import get_embedding_port
from storico.infrastructure.vector.google_embedding_adapter import GoogleEmbeddingAdapter
from storico.infrastructure.vector.ollama_embedding_adapter import OllamaEmbeddingAdapter
from storico.infrastructure.vector.openai_embedding_adapter import OpenAIEmbeddingAdapter


@pytest.mark.unit
def test_get_embedding_port_ollama() -> None:
    """Factory returns OllamaEmbeddingAdapter for 'ollama' provider."""
    settings = MagicMock(spec=Settings)
    settings.embedding_provider = "ollama"
    settings.ollama_host = "http://test.host"
    settings.embedding_model = "test-model"
    settings.embedding_dimensions = 768
    settings.google_api_key = None
    settings.google_embedding_model = "test"
    settings.openai_api_key = None
    settings.openai_embedding_model = "test"

    port = get_embedding_port(settings)
    assert isinstance(port, OllamaEmbeddingAdapter)


@pytest.mark.unit
def test_get_embedding_port_google() -> None:
    """Factory returns GoogleEmbeddingAdapter for 'google' provider."""
    settings = MagicMock(spec=Settings)
    settings.embedding_provider = "google"
    settings.ollama_host = "http://localhost:11434"
    settings.embedding_model = "nomic-embed-text"
    settings.embedding_dimensions = 768
    settings.google_api_key = "test-key"
    settings.google_embedding_model = "test-model"
    settings.openai_api_key = None
    settings.openai_embedding_model = "test"

    port = get_embedding_port(settings)
    assert isinstance(port, GoogleEmbeddingAdapter)
    assert port.dimensions == 768


@pytest.mark.unit
def test_get_embedding_port_openai() -> None:
    """Factory returns OpenAIEmbeddingAdapter for 'openai' provider."""
    settings = MagicMock(spec=Settings)
    settings.embedding_provider = "openai"
    settings.ollama_host = "http://localhost:11434"
    settings.embedding_model = "nomic-embed-text"
    settings.embedding_dimensions = 768
    settings.google_api_key = None
    settings.google_embedding_model = "test"
    settings.openai_api_key = "test-key"
    settings.openai_embedding_model = "test-model"

    port = get_embedding_port(settings)
    assert isinstance(port, OpenAIEmbeddingAdapter)
    assert port.dimensions == 768


@pytest.mark.unit
def test_get_embedding_port_unknown_provider() -> None:
    """Factory raises ValueError for unknown provider."""
    settings = MagicMock(spec=Settings)
    settings.embedding_provider = "unknown"
    settings.ollama_host = "http://localhost:11434"
    settings.embedding_model = "nomic-embed-text"
    settings.embedding_dimensions = 768
    settings.google_api_key = None
    settings.google_embedding_model = "test"
    settings.openai_api_key = None
    settings.openai_embedding_model = "test"

    with pytest.raises(ValueError, match="Unknown embedding provider: unknown"):
        get_embedding_port(settings)