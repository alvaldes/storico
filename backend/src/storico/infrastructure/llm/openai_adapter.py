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
from storico.infrastructure.llm.truncation import truncated_response_message

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


def _versioned_base(base_url: str | None) -> str | None:
    """Return the ``/v1`` spelling of a base URL that lacks it, else ``None``.

    Mirrors ``fetch_openai_compatible_models``: servers disagree on whether the
    configured base already carries ``/v1``, and the model listing probes both
    spellings. Extraction must resolve the same base the same way, or a model the
    listing found is reported missing when only the route was. No base means the
    SDK default (OpenAI itself), which already ends in ``/v1``.
    """
    if not base_url:
        return None
    stripped = base_url.rstrip("/")
    if stripped.endswith("/v1"):
        return None
    return f"{stripped}/v1"


def _names_the_model(error: OpenAINotFoundError, model: str) -> bool:
    """Tell a missing model from a missing route on a 404.

    A model 404 from an OpenAI-compatible server names the model in its message
    or carries ``code: model_not_found``; a 404 for a path the server does not
    serve names neither.
    """
    body = error.body
    if isinstance(body, dict):
        inner = body.get("error") if isinstance(body.get("error"), dict) else body
        if inner.get("code") == "model_not_found":
            return True
    return model in str(error)


def _request_url(error: OpenAINotFoundError) -> str:
    try:
        return str(error.request.url)
    except AttributeError:
        return "the configured endpoint"


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
        self._api_key = api_key
        # The ``/v1`` spelling to fall back to once, on a route 404. An injected client
        # has a base this adapter does not own, so it gets no fallback.
        self._fallback_base = None if client is not None else _versioned_base(base_url)

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
            response = await self._retry_under_v1_or_raise(e, kwargs, config)
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

        return self._to_response(response, config)

    async def _retry_under_v1_or_raise(
        self, error: OpenAINotFoundError, kwargs: dict[str, Any], config: LLMConfig
    ) -> Any:
        """Retry a 404 once under the ``/v1`` base, then classify what is left.

        A success keeps the ``/v1`` client for every later call, so the bare base
        costs one extra request per adapter, not per call.
        """
        if self._fallback_base is not None:
            versioned = AsyncOpenAI(api_key=self._api_key, base_url=self._fallback_base)
            self._fallback_base = None
            try:
                response = await versioned.chat.completions.create(**kwargs)
            except OpenAINotFoundError as retry_error:
                error = retry_error
            except OpenAIAPIConnectionError as retry_error:
                raise LLMConnectionError(
                    f"OpenAI API connection failed: {retry_error}"
                ) from retry_error
            except BaseOpenAIError as retry_error:
                raise LLMResponseError(f"OpenAI API error: {retry_error}") from retry_error
            else:
                logger.info(
                    "Resolved the provider base URL under /v1",
                    extra={"model": config.model},
                )
                self._client = versioned
                return response

        if _names_the_model(error, config.model):
            logger.error(
                "OpenAI model not found",
                extra={"model": config.model, "error": str(error)},
            )
            raise LLMModelNotFoundError(config.model) from error

        url = _request_url(error)
        logger.error(
            "The provider endpoint was not found",
            extra={"model": config.model, "url": url},
        )
        raise LLMConnectionError(
            f"Endpoint not found at {url} (HTTP 404). Check the provider Base URL in "
            "Workspace Settings."
        ) from error

    def _to_response(self, response: Any, config: LLMConfig) -> LLMResponse:
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

        # S4 (extraction-truncation): the budget can also cut an answer that has
        # already written something — three of six tasks arriving as a completed
        # run was the hole this closes. The installed SDK types the signal as
        # ``Choice.finish_reason: Literal["stop", "length", "tool_calls",
        # "content_filter", "function_call"]`` on the first choice
        # (``openai/types/chat/chat_completion.py``), so ``length`` with content
        # in hand is the provider's own truncation report. Raised as an
        # ``LLMResponseError`` — an ``LLMError`` — so the runner takes the
        # deterministic failure path without retrying (S3).
        choice = response.choices[0]
        content_finish_reason = getattr(choice, "finish_reason", None)
        if content_finish_reason == "length":
            logger.warning(
                "The provider stopped the answer at the output budget",
                extra={
                    "model": config.model,
                    "finish_reason": content_finish_reason,
                    "max_tokens": config.max_tokens,
                    "completion_tokens": (usage or {}).get("completion_tokens"),
                },
            )
            raise LLMResponseError(
                truncated_response_message("finish_reason: length", config.max_tokens)
            )

        return LLMResponse(text=choice.message.content, usage=usage)
