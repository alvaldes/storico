"""OllamaEmbeddingAdapter — EmbeddingPort implementation for Ollama embeddings."""

from __future__ import annotations

import logging

from storico.domain.ports import EmbeddingPort
from storico.infrastructure.vector.embedding_service import EmbeddingService

logger = logging.getLogger(__name__)


class OllamaEmbeddingAdapter(EmbeddingPort):
    """Adapter that generates embeddings via Ollama API, wrapping EmbeddingService."""

    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        model: str = "nomic-embed-text",
    ) -> None:
        """Initialize the adapter.

        Args:
            base_url: Ollama base URL.
            model: Embedding model name.
        """
        self._service = EmbeddingService(base_url=base_url, model=model)
        # nomic-embed-text and other Ollama embedding models used with Storico produce 768d
        self._dimensions = 768

    @property
    def dimensions(self) -> int:
        """Dimensionality of the embedding vectors (768 for Ollama nomic-embed-text)."""
        return self._dimensions

    async def embed(self, text: str) -> list[float]:
        """Generate an embedding vector for the given text via Ollama.

        Delegates to the wrapped EmbeddingService, with fallback to empty list on any error.

        Args:
            text: Input text to embed.

        Returns:
            Embedding vector as a list of floats.
            Empty list on any failure (logged as warning).
        """
        if not text or not text.strip():
            logger.warning("Empty text provided for embedding")
            return []

        try:
            return await self._service.embed(text)
        except (
            Exception
        ) as e:  # pragma: no cover - defensive, EmbeddingService already handles errors
            logger.warning("Ollama embedding service failed: %s", e)
            return []
