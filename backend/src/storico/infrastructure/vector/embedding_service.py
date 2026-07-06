"""EmbeddingService — generates text embeddings via Ollama API."""

from __future__ import annotations

import logging
from typing import Any

import httpx
from httpx import AsyncClient, ConnectError, TimeoutException

logger = logging.getLogger(__name__)


class EmbeddingService:
    """Generates embeddings by calling Ollama's /api/embeddings endpoint.

    Graceful degradation: returns empty list on any failure.
    """

    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        model: str = "nomic-embed-text",
        client: AsyncClient | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._client = client or AsyncClient(timeout=httpx.Timeout(30.0))

    async def embed(self, text: str) -> list[float]:
        """Generate an embedding vector for the given text.

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
            response = await self._client.post(
                f"{self._base_url}/api/embeddings",
                json={"model": self._model, "prompt": text},
                timeout=httpx.Timeout(30.0),
            )
        except (ConnectError, TimeoutException) as e:
            logger.warning("Ollama connection failed for embedding: %s", e)
            return []
        except httpx.HTTPError as e:
            logger.warning("HTTP error during embedding: %s", e)
            return []

        if response.status_code == 404:
            logger.warning(
                "Embedding model '%s' not found in Ollama. "
                "Run: ollama pull %s",
                self._model,
                self._model,
            )
            return []

        if response.status_code != 200:
            logger.warning(
                "Ollama embedding returned status %s: %s",
                response.status_code,
                response.text[:200],
            )
            return []

        try:
            data: dict[str, Any] = response.json()
            embedding = data.get("embedding", [])
            if not embedding:
                logger.warning("Ollama returned empty embedding")
                return []
            return embedding
        except (KeyError, ValueError, TypeError) as e:
            logger.warning("Failed to parse embedding response: %s", e)
            return []

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for multiple texts.

        Args:
            texts: List of input texts to embed.

        Returns:
            List of embedding vectors, one per input text.
            Empty vectors for failed items.
        """
        results: list[list[float]] = []
        for text in texts:
            embedding = await self.embed(text)
            results.append(embedding)
        return results
