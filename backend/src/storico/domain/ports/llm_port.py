"""LLMPort — abstract interface for LLM interaction."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class LLMConfig:
    """Configuration for an LLM generation request."""

    model: str
    temperature: float = 0.1
    max_tokens: int = 2048
    timeout: int = 120


@dataclass(frozen=True, slots=True)
class ParsedTask:
    """A single task parsed from LLM output."""

    summary: str
    description: str
    labels: tuple[str, ...] = ()
    dependencies: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ExtractionResult:
    """Result of an extraction containing parsed tasks and metadata."""

    tasks: tuple[ParsedTask, ...]
    raw_response: str
    confidence_score: float | None = None


class LLMPort(ABC):
    """Port for LLM interaction — send prompts and receive raw text responses."""

    @abstractmethod
    async def generate(self, prompt: str, config: LLMConfig) -> str:
        """Send a prompt to the LLM and return the raw response text.

        Args:
            prompt: The full prompt (system + instruction + user story) to send.
            config: Configuration for the LLM request.

        Returns:
            Raw text response from the LLM.

        Raises:
            LLMConnectionError: If the LLM service cannot be reached.
            LLMModelNotFoundError: If the requested model is not available.
            LLMResponseError: If the response is invalid or unprocessable.
        """
        ...
