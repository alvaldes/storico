"""LLMPort — abstract interface for LLM interaction."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

# The one literal for the default generation temperature. The route resolves the request
# value against it once and writes the same resolved value to the column it declares and
# to the ``LLMConfig`` the adapter runs at — two sources for one fact is the drift the
# single literal forbids.
DEFAULT_TEMPERATURE: float = 0.1


@dataclass(frozen=True, slots=True)
class LLMConfig:
    """Configuration for an LLM generation request."""

    model: str
    temperature: float = DEFAULT_TEMPERATURE
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
class LLMResponse:
    """What a provider answered, before any parsing.

    ``text`` is the raw completion the adapter extracted. ``usage`` is the
    provider's own token-usage container, copied verbatim — no renaming, no
    derived totals, no normalization into a common shape. ``None`` means the
    provider sent no usage information; it never means an empty container.
    """

    text: str
    usage: dict | None = None


@dataclass(frozen=True, slots=True)
class ExtractionResult:
    """Result of an extraction containing parsed tasks and metadata."""

    tasks: tuple[ParsedTask, ...]
    raw_response: str
    confidence_score: float | None = None
    usage: dict | None = None


class LLMPort(ABC):
    """Port for LLM interaction — send prompts and receive raw text responses."""

    @abstractmethod
    async def generate(
        self,
        prompt: str,
        config: LLMConfig,
        system_prompt: str | None = None,
    ) -> LLMResponse:
        """Send a prompt to the LLM and return the raw response.

        Args:
            prompt: The instruction/user content to send.
            config: Configuration for the LLM request.
            system_prompt: Optional system message. Each adapter delivers it
                using its provider-native mechanism (e.g. ``system_instruction``
                for Gemini, a ``system`` message for Ollama). If ``None``, no
                system message is sent.

        Returns:
            The provider's answer: the raw completion text plus its own usage
            container when the provider reports one (``usage`` is ``None``
            otherwise).

        Raises:
            LLMConnectionError: If the LLM service cannot be reached.
            LLMModelNotFoundError: If the requested model is not available.
            LLMResponseError: If the response is invalid or unprocessable.
        """
        ...
