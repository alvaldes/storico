"""EmbeddingPort — abstract interface for text embedding generation."""

from __future__ import annotations

from abc import ABC, abstractmethod


class EmbeddingPort(ABC):
    """Port for generating text embeddings."""

    @property
    @abstractmethod
    def dimensions(self) -> int:
        """Dimensionality of the embedding vectors produced by this port."""

    @abstractmethod
    async def embed(self, text: str) -> list[float]:
        """Generate an embedding vector for the given text.

        Args:
            text: Input text to embed.

        Returns:
            Embedding vector as a list of floats.
            Empty list on any failure (logged as warning by concrete adapters).
        """
        ...