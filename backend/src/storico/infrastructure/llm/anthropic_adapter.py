"""AnthropicAdapter — LLMPort implementation for Anthropic models via anthropic SDK."""

from __future__ import annotations

import logging
from typing import Any

from anthropic import AnthropicError as BaseAnthropicError
from anthropic import APIConnectionError as AnthropicAPIConnectionError
from anthropic import AsyncAnthropic
from anthropic import NotFoundError as AnthropicNotFoundError

from storico.domain.entities import LLMConnectionError, LLMModelNotFoundError, LLMResponseError
from storico.domain.ports import LLMConfig, LLMPort

logger = logging.getLogger(__name__)


class AnthropicAdapter(LLMPort):
    """Adapter that sends prompts to Anthropic models via the anthropic SDK.

    Uses the ``anthropic`` client library to call Anthropic models. Requires
    a valid API key passed at construction time.
    """

    def __init__(
        self,
        api_key: str,
        base_url: str | None = None,
        client: AsyncAnthropic | None = None,
    ) -> None:
        """Initialize the adapter.

        Args:
            api_key: Anthropic API key.
            base_url: Optional base URL for Anthropic-compatible endpoints.
            client: Optional pre-configured ``AsyncAnthropic`` client. If omitted,
                a new client is created with the given api_key and base_url.
        """
        self._client = client or AsyncAnthropic(api_key=api_key, base_url=base_url or None)

    async def generate(
        self,
        prompt: str,
        config: LLMConfig,
        system_prompt: str | None = None,
    ) -> str:
        """Send a prompt to an Anthropic model and return the raw response.

        Args:
            prompt: The instruction/user content to send.
            config: LLM configuration (model, temperature, max_tokens).
            system_prompt: Optional system prompt. If ``None``, no system
                message is included in the request.

        Returns:
            Raw text response from the model.

        Raises:
            LLMConnectionError: If the Anthropic API cannot be reached.
            LLMModelNotFoundError: If the requested model is not available.
            LLMResponseError: If the response is invalid or unprocessable.
        """
        # Build kwargs for messages.create
        kwargs: dict[str, Any] = {
            "model": config.model,
            "max_tokens": config.max_tokens,  # Anthropic requires max_tokens
            "temperature": config.temperature,
            "messages": [{"role": "user", "content": prompt}],
        }
        if system_prompt is not None:
            kwargs["system"] = system_prompt

        try:
            response = await self._client.messages.create(**kwargs)
        except AnthropicAPIConnectionError as e:
            logger.error(
                "Anthropic API connection failed",
                extra={
                    "model": config.model,
                    "error": str(e),
                    "error_type": type(e).__name__,
                },
            )
            raise LLMConnectionError(f"Anthropic API connection failed: {e}") from e
        except AnthropicNotFoundError as e:
            logger.error(
                "Anthropic model not found",
                extra={"model": config.model, "error": str(e)},
            )
            raise LLMModelNotFoundError(config.model) from e
        except BaseAnthropicError as e:
            logger.error(
                "Anthropic API error",
                extra={
                    "model": config.model,
                    "error": str(e),
                    "error_type": type(e).__name__,
                },
            )
            raise LLMResponseError(f"Anthropic API error: {e}") from e

        # Extract text from content blocks
        text_blocks = [
            block.text for block in response.content if getattr(block, "type", None) == "text"
        ]
        if not text_blocks:
            logger.warning(
                "Anthropic returned empty response",
                extra={"model": config.model},
            )
            raise LLMResponseError("Anthropic returned an empty response")

        return "".join(text_blocks)
