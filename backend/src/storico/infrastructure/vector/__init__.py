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
            model=settings.embedding_model,
        )
    if provider == "google":
        if not settings.google_api_key:
            raise ValueError("STORICO_GOOGLE_API_KEY is required for the google embedding provider")
        logger.info("Creating GoogleEmbeddingAdapter")
        return GoogleEmbeddingAdapter(
            api_key=settings.google_api_key,
            model=settings.google_embedding_model,
            dimensions=settings.embedding_dimensions,
        )
    if provider == "openai":
        if not settings.openai_api_key:
            raise ValueError("STORICO_OPENAI_API_KEY is required for the openai embedding provider")
        logger.info("Creating OpenAIEmbeddingAdapter")
        return OpenAIEmbeddingAdapter(
            api_key=settings.openai_api_key,
            model=settings.openai_embedding_model,
            dimensions=settings.embedding_dimensions,
        )
    logger.error("Unknown embedding provider: %s", provider)
    raise ValueError(f"Unknown embedding provider: {provider}")


__all__ = [
    "EmbeddingService",
    "OllamaEmbeddingAdapter",
    "GoogleEmbeddingAdapter",
    "OpenAIEmbeddingAdapter",
    "get_embedding_port",
]

if QdrantAdapter is not None:
    __all__.append("QdrantAdapter")
