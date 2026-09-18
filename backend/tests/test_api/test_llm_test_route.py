"""Tests for ``POST /api/v1/llm/test`` — the connection probe.

This route takes the endpoint and the credential straight from the request body, so it is
the one place a user-supplied LLM credential reaches an adapter with no workspace row in
between. A blank value there has to mean "absent" exactly as it does for a stored one,
which is why the route normalizes before it builds anything.

The route had no tests before this: the only client helper is unused, so it was an
untested public endpoint that could hand an adapter a string of spaces.
"""

from __future__ import annotations

from typing import Any

import pytest
from httpx import AsyncClient

from storico.config.settings import Settings
from storico.infrastructure import llm as llm_module

URL = "/api/v1/llm/test"


@pytest.fixture
def adapter_kwargs(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    """Replace every adapter the route can build, recording its constructor kwargs.

    The route imports each adapter inside the branch that uses it, so patching the module
    attribute is enough — and the recording is what proves what the adapter would have
    received, without any network call.
    """
    built: list[dict[str, Any]] = []

    class Recording:
        def __init__(self, **kwargs: Any) -> None:
            built.append(kwargs)

        async def generate(self, prompt: str, config: Any) -> str:  # noqa: ARG002
            return "stub response"

    for name in ("OllamaAdapter", "OpenAIAdapter", "AnthropicAdapter", "GeminiAdapter"):
        monkeypatch.setattr(llm_module, name, Recording)
    return built


async def _post(client: AsyncClient, payload: dict[str, Any]):
    """Send a connection test."""
    return await client.post(URL, json=payload)


class TestBlankCredential:
    """A credential made of whitespace is a missing credential."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("provider", ["openai", "anthropic", "gemini"])
    async def test_it_is_refused_before_any_adapter_is_built(
        self, authed_client: AsyncClient, adapter_kwargs: list[dict[str, Any]], provider: str
    ) -> None:
        """It used to build an adapter with a blank key and spend a call failing."""
        response = await _post(
            authed_client, {"provider": provider, "model": "some-model", "api_key": "   "}
        )

        assert response.status_code == 200
        body = response.json()
        assert body["success"] is False
        assert "API key is required" in body["message"]
        assert adapter_kwargs == []


class TestBlankEndpoint:
    """A blank endpoint is absent, so the provider's own default applies."""

    @pytest.mark.asyncio
    async def test_ollama_falls_back_to_the_configured_host(
        self, authed_client: AsyncClient, adapter_kwargs: list[dict[str, Any]]
    ) -> None:
        """The host default, never a URL made of spaces."""
        response = await _post(
            authed_client, {"provider": "ollama", "model": "llama3.2", "base_url": "   "}
        )

        assert response.status_code == 200
        assert adapter_kwargs == [{"base_url": Settings.load().ollama_host}]

    @pytest.mark.asyncio
    async def test_a_cloud_adapter_is_built_without_an_endpoint(
        self, authed_client: AsyncClient, adapter_kwargs: list[dict[str, Any]]
    ) -> None:
        """``None`` means "use the provider's default"; ``'   '`` meant a broken URL."""
        response = await _post(
            authed_client,
            {
                "provider": "openai",
                "model": "gpt-4o-mini",
                "api_key": "sk-real",
                "base_url": "   ",
            },
        )

        assert response.status_code == 200
        assert adapter_kwargs == [{"api_key": "sk-real", "base_url": None}]


class TestRealValues:
    """Normalizing is not a filter for values that mean something."""

    @pytest.mark.asyncio
    async def test_a_padded_endpoint_reaches_the_adapter_trimmed(
        self, authed_client: AsyncClient, adapter_kwargs: list[dict[str, Any]]
    ) -> None:
        """A paste artifact goes; an endpoint with a path stays."""
        response = await _post(
            authed_client,
            {
                "provider": "openai",
                "model": "gpt-4o-mini",
                "api_key": "sk-real",
                "base_url": "  https://gateway.internal/v1  ",
            },
        )

        assert response.status_code == 200
        assert adapter_kwargs == [{"api_key": "sk-real", "base_url": "https://gateway.internal/v1"}]

    @pytest.mark.asyncio
    async def test_a_credential_with_internal_spaces_is_kept(
        self, authed_client: AsyncClient, adapter_kwargs: list[dict[str, Any]]
    ) -> None:
        """Only the surrounding whitespace is a paste artifact, not what is inside."""
        response = await _post(
            authed_client,
            {
                "provider": "anthropic",
                "model": "claude-3-haiku",
                "api_key": "  sk-ant-a b c  ",
            },
        )

        assert response.status_code == 200
        assert adapter_kwargs == [{"api_key": "sk-ant-a b c", "base_url": None}]
