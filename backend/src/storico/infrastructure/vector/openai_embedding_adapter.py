"""OpenAIEmbeddingAdapter — EmbeddingPort implementation for OpenAI embeddings via openai SDK."""

from __future__ import annotations

import logging

from openai import APIConnectionError as OpenAIAPIConnectionError
from openai import AsyncOpenAI
from openai import NotFoundError as OpenAINotFoundError
from openai import OpenAIError as BaseOpenAIError

from storico.domain.ports import EmbeddingPort

logger = logging.getLogger(__name__)


class OpenAIEmbeddingAdapter(EmbeddingPort):
    """Adapter that generates embeddings via OpenAI's embedding models using the openai SDK."""

    def __init__(
        self,
        api_key: str,
        base_url: str | None = None,
        model: str = "text-embedding-3-small",
        dimensions: int = 768,
    ) -> None:
        """Initialize the adapter.

        Args:
            api_key: OpenAI API key.
            base_url: Optional base URL for OpenAI-compatible endpoints.
            model: The embedding model to use (e.g., "text-embedding-3-small").
            dimensions: The output dimensionality of the embeddings (default 768 to match Ollama).
        """
        self._client = AsyncOpenAI(api_key=api_key, base_url=base_url or None)
        self._model = model
        self._dimensions = dimensions

    @property
    def dimensions(self) -> int:
        """Dimensionality of the embedding vectors."""
        return self._dimensions

    async def embed(self, text: str) -> list[float]:
        """Generate an embedding vector for the given text via OpenAI's embedding model.

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
            response = await self._client.embeddings.create(
                model=self._model,
                input=text,
                dimensions=self._dimensions,
            )
        except OpenAIAPIConnectionError as e:
            logger.error(
                "OpenAI API connection failed",
                extra={
                    "model": self._model,
                    "error": str(e),
                    "error_type": type(e).__name__,
                },
            )
            return []
        except OpenAINotFoundError as e:
            logger.error(
                "OpenAI model not found",
                extra={"model": self._model, "error": str(e)},
            )
            return []
        except BaseOpenAIError as e:
            logger.error(
                "OpenAI API error",
                extra={
                    "model": self._model,
                    "error": str(e),
                    "error_type": type(e).__name__,
                },
            )
            return []
        except Exception as e:
            logger.error(
                "OpenAI embedding failed unexpectedly",
                extra={
                    "model": self._model,
                    "error": str(e),
                    "error_type": type(e).__name__,
                },
            )
            return []

        if not response.data or not response.data[0].embedding:
            logger.warning("OpenAI returned empty embedding")
            return []

        return response.data[0].embedding