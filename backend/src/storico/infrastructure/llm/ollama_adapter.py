"""OllamaAdapter — LLMPort implementation for local models via Ollama API."""

from __future__ import annotations

import logging
from typing import Any

import httpx
from httpx import AsyncClient, ConnectError, Timeout, TimeoutException

from storico.domain.entities import LLMConnectionError, LLMModelNotFoundError, LLMResponseError
from storico.domain.ports import LLMConfig, LLMPort

logger = logging.getLogger(__name__)


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

    async def generate(
        self,
        prompt: str,
        config: LLMConfig,
        system_prompt: str | None = None,
    ) -> str:
        """Send a prompt to the Ollama model and return the raw response.

        Args:
            prompt: The instruction/user content to send.
            config: LLM configuration (model, temperature, max_tokens, timeout).
            system_prompt: Optional system message. If ``None``, no system
                message is included in the request.

        Returns:
            Raw text response from the model.

        Raises:
            LLMConnectionError: If the Ollama service cannot be reached.
            LLMModelNotFoundError: If the requested model is not available.
            LLMResponseError: If the response is invalid or unparseable.
        """
        payload = self._build_payload(prompt, config, system_prompt)
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
                logger.warning(
                    "Ollama connection attempt failed, will retry",
                    extra={
                        "attempt": attempt + 1,
                        "max_attempts": 3,
                        "error": str(e),
                        "error_type": type(e).__name__,
                        "base_url": self._base_url,
                        "model": config.model,
                    },
                )
                if attempt < 2:
                    wait = 2**attempt  # 1, 2, 4 seconds
                    import asyncio

                    await asyncio.sleep(wait)
                continue
            except httpx.HTTPError as e:
                logger.error(
                    "Ollama HTTP error",
                    extra={"error": str(e), "error_type": type(e).__name__},
                )
                raise LLMResponseError(f"HTTP error from Ollama: {e}") from e

            if response.status_code == 404:
                raise LLMModelNotFoundError(config.model)

            if response.status_code != 200:
                logger.error(
                    "Ollama returned error status",
                    extra={"status_code": response.status_code, "response_text": response.text},
                )
                raise LLMResponseError(
                    f"Ollama returned status {response.status_code}: {response.text}"
                )

            return self._parse_response(response.json())

        logger.error(
            "All Ollama connection attempts exhausted",
            extra={
                "max_attempts": 3,
                "base_url": self._base_url,
                "model": config.model,
                "last_error": str(last_exception) if last_exception else None,
            },
        )
        raise LLMConnectionError(
            f"Failed to connect to Ollama at {self._base_url} after 3 attempts"
        ) from last_exception

    def _build_payload(
        self,
        prompt: str,
        config: LLMConfig,
        system_prompt: str | None = None,
    ) -> dict[str, Any]:
        """Build the Ollama API request payload.

        The system message is included only when ``system_prompt`` is
        provided — extraction passes the workspace-configured prompt, while
        calls without one (e.g. health check "Hello") send only the user
        message.

        ``stream`` is explicit, not optional. Ollama's ``/api/chat`` defaults
        to streaming NDJSON, so the real response for a payload without this
        key is several JSON objects, one per line — and this adapter reads the
        body with a single ``response.json()``, which then fails with
        ``json.JSONDecodeError: Extra data: line 2 column 1``. ``stream: False``
        makes the server answer with exactly one JSON object. Measured against
        Ollama 0.32.5 in ``tests/test_integration/test_ollama_chat_live.py``.
        """
        messages: list[dict[str, str]] = [{"role": "user", "content": prompt}]
        if system_prompt:
            messages.insert(0, {"role": "system", "content": system_prompt})
        return {
            "model": config.model,
            "messages": messages,
            "stream": False,
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
