"""GoogleEmbeddingAdapter — EmbeddingPort implementation for Google embeddings via google-genai."""

from __future__ import annotations

import asyncio
import logging

from google import genai
from google.genai import types as genai_types

from storico.domain.ports import EmbeddingPort

logger = logging.getLogger(__name__)


class GoogleEmbeddingAdapter(EmbeddingPort):
    """Adapter that generates embeddings via Google's text-embedding models using google-genai."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str = "text-embedding-004",
        dimensions: int = 768,
    ) -> None:
        """Initialize the adapter.

        Args:
            api_key: Google AI API key. If None, the SDK falls back to the GOOGLE_API_KEY environment variable.
            model: The embedding model to use (e.g., "text-embedding-004").
            dimensions: The output dimensionality of the embeddings (default 768 to match Ollama).
        """
        self._client = genai.Client(api_key=api_key) if api_key else genai.Client()
        self._model = model
        self._dimensions = dimensions

    @property
    def dimensions(self) -> int:
        """Dimensionality of the embedding vectors."""
        return self._dimensions

    async def embed(self, text: str) -> list[float]:
        """Generate an embedding vector for the given text via Google's embedding model.

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
            # google-genai has no async client in this version; run the sync
            # embed_content in a worker thread so we don't block the event loop.
            response = await asyncio.to_thread(
                self._client.models.embed_content,
                model=self._model,
                contents=text,
                config=genai_types.EmbedContentConfig(
                    output_dimensionality=self._dimensions,
                    task_type="RETRIEVAL_DOCUMENT",
                ),
            )
        except Exception as e:
            logger.error(
                "Google embedding API call failed",
                extra={
                    "model": self._model,
                    "error": str(e),
                    "error_type": type(e).__name__,
                },
            )
            return []

        # The response.embeddings is a list of ContentEmbedding objects (one per input).
        # We only have one input, so we take the first.
        if not response.embeddings:
            logger.warning("Google returned empty embeddings")
            return []

        # The embedding values are in response.embeddings[0].values
        embedding = response.embeddings[0].values
        if not embedding:
            logger.warning("Google embedding returned empty values")
            return []

        return embedding