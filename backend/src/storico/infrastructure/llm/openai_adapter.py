"""OpenAIAdapter — LLMPort implementation for OpenAI models via openai SDK."""

from __future__ import annotations

import logging
from typing import Any

from openai import APIConnectionError as OpenAIAPIConnectionError
from openai import AsyncOpenAI
from openai import NotFoundError as OpenAINotFoundError
from openai import OpenAIError as BaseOpenAIError

from storico.domain.entities import LLMConnectionError, LLMModelNotFoundError, LLMResponseError
from storico.domain.ports import LLMConfig, LLMPort

logger = logging.getLogger(__name__)


class OpenAIAdapter(LLMPort):
    """Adapter that sends prompts to OpenAI models via the openai SDK.

    Uses the ``openai`` client library to call OpenAI models. Requires
    a valid API key passed at construction time.
    """

    def __init__(
        self,
        api_key: str,
        base_url: str | None = None,
        client: AsyncOpenAI | None = None,
    ) -> None:
        """Initialize the adapter.

        Args:
            api_key: OpenAI API key.
            base_url: Optional base URL for OpenAI-compatible endpoints.
            client: Optional pre-configured ``AsyncOpenAI`` client. If omitted,
                a new client is created with the given api_key and base_url.
        """
        self._client = client or AsyncOpenAI(api_key=api_key, base_url=base_url or None)

    async def generate(
        self,
        prompt: str,
        config: LLMConfig,
        system_prompt: str | None = None,
    ) -> str:
        """Send a prompt to an OpenAI model and return the raw response.

        Args:
            prompt: The instruction/user content to send.
            config: LLM configuration (model, temperature, max_tokens).
            system_prompt: Optional system prompt. If ``None``, no system
                message is included in the request.

        Returns:
            Raw text response from the model.

        Raises:
            LLMConnectionError: If the OpenAI API cannot be reached.
            LLMModelNotFoundError: If the requested model is not available.
            LLMResponseError: If the response is invalid or unprocessable.
        """
        # Build messages list: system (if provided) then user
        messages: list[dict[str, str]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        kwargs: dict[str, Any] = {
            "model": config.model,
            "messages": messages,
            "temperature": config.temperature,
            "max_tokens": config.max_tokens,
        }

        try:
            response = await self._client.chat.completions.create(**kwargs)
        except OpenAIAPIConnectionError as e:
            logger.error(
                "OpenAI API connection failed",
                extra={
                    "model": config.model,
                    "error": str(e),
                    "error_type": type(e).__name__,
                },
            )
            raise LLMConnectionError(f"OpenAI API connection failed: {e}") from e
        except OpenAINotFoundError as e:
            logger.error(
                "OpenAI model not found",
                extra={"model": config.model, "error": str(e)},
            )
            raise LLMModelNotFoundError(config.model) from e
        except BaseOpenAIError as e:
            logger.error(
                "OpenAI API error",
                extra={
                    "model": config.model,
                    "error": str(e),
                    "error_type": type(e).__name__,
                },
            )
            raise LLMResponseError(f"OpenAI API error: {e}") from e

        if not response.choices or not response.choices[0].message.content:
            logger.warning(
                "OpenAI returned empty response",
                extra={"model": config.model},
            )
            raise LLMResponseError("OpenAI returned an empty response")

        return response.choices[0].message.content
