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
from storico.domain.ports.llm_port import LLMResponse

logger = logging.getLogger(__name__)

#: Credential to send to an OpenAI-compatible endpoint that requires none.
#:
#: ``AsyncOpenAI`` rejects an empty key, and ``None`` would let the SDK read the ambient
#: ``OPENAI_API_KEY`` instead — a credential source a workspace-scoped call must not reach
#: for. Self-hosted gateways commonly accept unauthenticated requests, so they need a value
#: that means "no credential": this one, shared by every caller that builds the adapter from
#: a workspace configuration or from the connection test.
CUSTOM_PROVIDER_PLACEHOLDER_KEY = "no-key-required"


def _empty_response_message(finish_reason: str | None, refusal: str | None, max_tokens: int) -> str:
    """Explain an empty completion from the one cause the provider reported.

    The message is named after no vendor on purpose. This adapter serves OpenAI **and**
    every workspace-registered OpenAI-compatible provider — ``_build_llm_port`` routes
    any unknown provider name here — so "OpenAI returned an empty response" attributed a
    custom endpoint's failure to the wrong service and sent the reader looking at the
    wrong place.

    Three shapes, in the order they can be trusted: a refusal came back with no text; the
    output budget stopped the answer (``finish_reason: length``, and the budget is
    configurable in Workspace Settings); or the provider stopped for a reason it named.
    A provider that reported nothing keeps the plain sentence — inventing a cause here is
    worse than admitting there is none.
    """
    if refusal:
        return "The provider refused to answer: no content and a refusal were returned"
    if finish_reason == "length":
        return (
            "The provider returned an empty response: the output budget stopped it "
            f"(finish_reason: length, max_tokens: {max_tokens}). Raise max tokens in "
            "Workspace Settings."
        )
    if finish_reason:
        return f"The provider returned an empty response (finish_reason: {finish_reason})"
    return "The provider returned an empty response"


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
            api_key: OpenAI API key, or :data:`CUSTOM_PROVIDER_PLACEHOLDER_KEY`
                for an endpoint that needs no credential.
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
    ) -> LLMResponse:
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

        raw_usage = getattr(response, "usage", None)
        usage = raw_usage.model_dump() if raw_usage is not None else None

        if not response.choices or not response.choices[0].message.content:
            # A 200 with no content is the least diagnosable failure a provider can give,
            # and the extraction row only carries the message. So the provider's own
            # report travels with it: the reason it stopped, whether it refused, and the
            # completion count against the budget that was sent. The response body never
            # does — diagnosis is not a licence to publish a provider's text.
            first_choice = response.choices[0] if response.choices else None
            finish_reason = getattr(first_choice, "finish_reason", None)
            refusal = getattr(first_choice.message, "refusal", None) if first_choice else None
            logger.warning(
                "The provider returned no content",
                extra={
                    "model": config.model,
                    "finish_reason": finish_reason,
                    "choice_count": len(response.choices or ()),
                    "refusal_present": bool(refusal),
                    "completion_tokens": (usage or {}).get("completion_tokens"),
                    "max_tokens": config.max_tokens,
                },
            )
            raise LLMResponseError(
                _empty_response_message(finish_reason, refusal, config.max_tokens)
            )

        return LLMResponse(text=response.choices[0].message.content, usage=usage)
