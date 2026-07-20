"""GeminiAdapter — LLMPort implementation for Google Gemini models via google-genai SDK."""

from __future__ import annotations

from typing import Any

from google import genai
from google.genai import types as genai_types

from storico.domain.entities import LLMConnectionError, LLMResponseError
from storico.domain.ports import LLMConfig, LLMPort


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

    async def generate(self, prompt: str, config: LLMConfig) -> str:
        """Send a prompt to a Gemini model and return the raw response.

        Args:
            prompt: The full prompt text to send.
            config: LLM configuration (model, temperature, max_tokens).

        Returns:
            Raw text response from the model.

        Raises:
            LLMConnectionError: If the Gemini API cannot be reached.
            LLMResponseError: If the response is invalid or unprocessable.
        """
        try:
            response = self._client.models.generate_content(
                model=config.model,
                contents=prompt,
                config=genai_types.GenerateContentConfig(
                    temperature=config.temperature,
                    max_output_tokens=config.max_tokens,
                ),
            )
        except Exception as e:
            raise LLMConnectionError(f"Gemini API call failed: {e}") from e

        if response.text is None:
            raise LLMResponseError("Gemini returned an empty response")

        return response.text
