"""OllamaAdapter — LLMPort implementation for local models via Ollama API."""

from __future__ import annotations

from typing import Any

import httpx
from httpx import AsyncClient, ConnectError, Timeout, TimeoutException

from storico.domain.entities import LLMConnectionError, LLMModelNotFoundError, LLMResponseError
from storico.domain.ports import LLMConfig, LLMPort


class OllamaAdapter(LLMPort):
    """Adapter that sends prompts to a local Ollama instance.

    Uses HTTP POST to ``{base_url}/api/chat`` with a JSON payload containing
    ``model``, ``messages`` (system + user), and generation parameters.

    Retries on connection errors with exponential backoff (1s, 2s, 4s).
    """

    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        client: AsyncClient | None = None,
    ) -> None:
        """Initialize the adapter.

        Args:
            base_url: Ollama server URL (default ``http://localhost:11434``).
            client: Optional pre-configured ``httpx.AsyncClient``. If omitted,
                a new client with a 120-second timeout is created.
        """
        self._base_url = base_url.rstrip("/")
        self._client = client or AsyncClient(timeout=Timeout(120.0))

    async def generate(self, prompt: str, config: LLMConfig) -> str:
        """Send a prompt to the Ollama model and return the raw response.

        Args:
            prompt: The full prompt text to send.
            config: LLM configuration (model, temperature, max_tokens, timeout).

        Returns:
            Raw text response from the model.

        Raises:
            LLMConnectionError: If the Ollama service cannot be reached.
            LLMModelNotFoundError: If the requested model is not available.
            LLMResponseError: If the response is invalid or unparseable.
        """
        payload = self._build_payload(prompt, config)
        last_exception: Exception | None = None

        for attempt in range(3):
            try:
                response = await self._client.post(
                    f"{self._base_url}/api/chat",
                    json=payload,
                    timeout=Timeout(config.timeout),
                )
            except (ConnectError, TimeoutException) as e:
                last_exception = e
                if attempt < 2:
                    wait = 2**attempt  # 1, 2, 4 seconds
                    import asyncio

                    await asyncio.sleep(wait)
                continue
            except httpx.HTTPError as e:
                raise LLMResponseError(f"HTTP error from Ollama: {e}") from e

            if response.status_code == 404:
                raise LLMModelNotFoundError(config.model)

            if response.status_code != 200:
                raise LLMResponseError(
                    f"Ollama returned status {response.status_code}: {response.text}"
                )

            return self._parse_response(response.json())

        raise LLMConnectionError(
            f"Failed to connect to Ollama at {self._base_url} after 3 attempts"
        ) from last_exception

    def _build_payload(self, prompt: str, config: LLMConfig) -> dict[str, Any]:
        """Build the Ollama API request payload."""
        return {
            "model": config.model,
            "messages": [
                {
                    "role": "system",
                    "content": "You are an expert software development lead who excels at "
                    "breaking down user stories into clear, actionable development tasks.",
                },
                {"role": "user", "content": prompt},
            ],
            "options": {
                "temperature": config.temperature,
                "num_predict": config.max_tokens,
            },
        }

    def _parse_response(self, data: dict[str, Any]) -> str:
        """Extract message content from the Ollama chat response."""
        try:
            return data["message"]["content"]
        except (KeyError, TypeError) as e:
            raise LLMResponseError(f"Unexpected Ollama response format: {e}") from e
