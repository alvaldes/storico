"""GeminiAdapter — LLMPort implementation for Google Gemini models via google-genai SDK."""

from __future__ import annotations

import logging
from typing import Any

from google import genai
from google.genai import types as genai_types

from storico.domain.entities import LLMConnectionError, LLMResponseError
from storico.domain.ports import LLMConfig, LLMPort
from storico.domain.ports.llm_port import LLMResponse
from storico.infrastructure.llm.truncation import truncated_response_message

logger = logging.getLogger(__name__)


class GeminiAdapter(LLMPort):
    """Adapter that sends prompts to Google Gemini models via the google-genai SDK.

    Uses the ``google-genai`` client library to call Gemini models. Requires
    a valid API key passed at construction time (either directly or via the
    ``GOOGLE_API_KEY`` environment variable).
    """

    def __init__(self, api_key: str | None = None) -> None:
        """Initialize the adapter.

        Args:
            api_key: Google AI API key. If ``None``, the SDK falls back to
                the ``GOOGLE_API_KEY`` environment variable.
        """
        self._client = genai.Client(api_key=api_key) if api_key else genai.Client()

    async def generate(
        self,
        prompt: str,
        config: LLMConfig,
        system_prompt: str | None = None,
    ) -> LLMResponse:
        """Send a prompt to a Gemini model and return the raw response.

        Args:
            prompt: The instruction/user content to send.
            config: LLM configuration (model, temperature, max_tokens).
            system_prompt: Optional system prompt delivered via
                ``system_instruction``. If ``None``, no system instruction
                is set.

        Returns:
            The model's answer: the raw completion text plus the provider's own
            usage container (``usage_metadata.model_dump()``) when the response
            reports one.

        Raises:
            LLMConnectionError: If the Gemini API cannot be reached.
            LLMResponseError: If the response is invalid or unprocessable.
        """
        gen_config: dict[str, Any] = {
            "temperature": config.temperature,
            "max_output_tokens": config.max_tokens,
        }
        if system_prompt:
            gen_config["system_instruction"] = system_prompt

        try:
            response = self._client.models.generate_content(
                model=config.model,
                contents=prompt,
                config=genai_types.GenerateContentConfig(**gen_config),
            )
        except Exception as e:
            logger.error(
                "Gemini API call failed",
                extra={
                    "model": config.model,
                    "error": str(e),
                    "error_type": type(e).__name__,
                },
            )
            raise LLMConnectionError(f"Gemini API call failed: {e}") from e

        if response.text is None:
            logger.warning(
                "Gemini returned empty response",
                extra={"model": config.model},
            )
            raise LLMResponseError("Gemini returned an empty response")

        # S4 (extraction-truncation): the budget can also cut an answer that has
        # already written something. The installed SDK types the signal as
        # ``Candidate.finish_reason: Optional[FinishReason]`` with
        # ``FinishReason.MAX_TOKENS`` (``google/genai/types.py``), read from the
        # first candidate — the same candidate ``response.text`` reads. Raised
        # as an ``LLMResponseError`` — an ``LLMError`` — so the runner takes the
        # deterministic failure path without retrying (S3).
        candidates = getattr(response, "candidates", None) or []
        first_candidate = candidates[0] if candidates else None
        finish_reason = (
            getattr(first_candidate, "finish_reason", None) if first_candidate is not None else None
        )
        if finish_reason == genai_types.FinishReason.MAX_TOKENS:
            logger.warning(
                "Gemini stopped the answer at the output budget",
                extra={
                    "model": config.model,
                    "finish_reason": str(finish_reason),
                    "max_tokens": config.max_tokens,
                },
            )
            raise LLMResponseError(
                truncated_response_message("finish_reason: MAX_TOKENS", config.max_tokens)
            )

        raw_usage = getattr(response, "usage_metadata", None)
        usage = raw_usage.model_dump() if raw_usage is not None else None
        return LLMResponse(text=response.text, usage=usage)
