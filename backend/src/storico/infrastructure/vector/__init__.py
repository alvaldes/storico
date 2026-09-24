"""Vector store infrastructure — Qdrant adapter, embedding service, and embedding providers."""

import logging

from storico.config.settings import Settings
from storico.domain.ports import EmbeddingPort
from storico.infrastructure.vector.embedding_service import EmbeddingService
from storico.infrastructure.vector.google_embedding_adapter import GoogleEmbeddingAdapter
from storico.infrastructure.vector.ollama_embedding_adapter import OllamaEmbeddingAdapter
from storico.infrastructure.vector.openai_embedding_adapter import OpenAIEmbeddingAdapter

logger = logging.getLogger(__name__)

try:
    from storico.infrastructure.vector.qdrant_adapter import QdrantAdapter
except ImportError as e:
    logger.warning(f"Could not import QdrantAdapter: {e}")
    QdrantAdapter = None


def embedding_model_for(settings: Settings) -> str:
    """The embedding model ``get_embedding_port`` will actually use.

    Single home for the provider→setting mapping. ``STORICO_EMBEDDING_MODEL`` is only the
    *Ollama* model; each cloud provider reads its own field. Any caller that wants to
    report which model is in use — a diagnostics probe, a log line — must ask this
    function rather than reading ``embedding_model`` directly, because that field names
    the wrong model for two of the three providers.
    """
    provider = settings.embedding_provider.lower()
    if provider == "google":
        return settings.google_embedding_model
    if provider == "openai":
        return settings.openai_embedding_model
    return settings.embedding_model


def get_embedding_port(settings: Settings) -> EmbeddingPort:
    """Factory to create an EmbeddingPort implementation based on settings.

    Args:
        settings: Application settings.

    Returns:
        An EmbeddingPort instance.

    Raises:
        ValueError: If the embedding provider is unknown, or a cloud provider is
            selected without its API key.
    """
    provider = settings.embedding_provider.lower()
    if provider == "ollama":
        logger.info("Creating OllamaEmbeddingAdapter")
        return OllamaEmbeddingAdapter(
            base_url=settings.ollama_host,
            model=embedding_model_for(settings),
        )
    if provider == "google":
        if not settings.google_api_key:
            raise ValueError("STORICO_GOOGLE_API_KEY is required for the google embedding provider")
        logger.info("Creating GoogleEmbeddingAdapter")
        return GoogleEmbeddingAdapter(
            api_key=settings.google_api_key,
            model=embedding_model_for(settings),
            dimensions=settings.embedding_dimensions,
        )
    if provider == "openai":
        if not settings.openai_api_key:
            raise ValueError("STORICO_OPENAI_API_KEY is required for the openai embedding provider")
        logger.info("Creating OpenAIEmbeddingAdapter")
        return OpenAIEmbeddingAdapter(
            api_key=settings.openai_api_key,
            model=embedding_model_for(settings),
            dimensions=settings.embedding_dimensions,
        )
    logger.error("Unknown embedding provider: %s", provider)
    raise ValueError(f"Unknown embedding provider: {provider}")


__all__ = [
    "EmbeddingService",
    "OllamaEmbeddingAdapter",
    "GoogleEmbeddingAdapter",
    "OpenAIEmbeddingAdapter",
    "embedding_model_for",
    "get_embedding_port",
]

if QdrantAdapter is not None:
    __all__.append("QdrantAdapter")
