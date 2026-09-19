"""Unit tests for extraction-side LLM adapter selection.

Selection is pure, so these tests exercise it without a database session or a
running event loop.  What matters is that the workspace-configured provider —
not a silent default — decides which endpoint receives the extraction.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from storico.domain.entities.exceptions import LLMError
from storico.infrastructure.llm import (
    CUSTOM_PROVIDER_PLACEHOLDER_KEY,
    AnthropicAdapter,
    GeminiAdapter,
    OllamaAdapter,
    OpenAIAdapter,
)
from storico.infrastructure.tasks import extraction_task

OLLAMA_HOST = "http://ollama.internal:11434"
CUSTOM_BASE_URL = "https://api.deepseek.com/v1"


@pytest.fixture
def adapter_spies(monkeypatch: pytest.MonkeyPatch) -> dict[str, list[dict[str, Any]]]:
    """Record every adapter construction while still returning the real adapter.

    Real adapters keep instance assertions meaningful and the recorded kwargs
    prove which endpoint the workspace config reached.  ``AsyncOpenAI`` is
    replaced as the sibling adapter test does, so the SDK's own credential
    enforcement cannot masquerade as the selection behaviour under test.
    """
    monkeypatch.setattr("storico.infrastructure.llm.openai_adapter.AsyncOpenAI", MagicMock())

    calls: dict[str, list[dict[str, Any]]] = {}

    for name in ("GeminiAdapter", "OpenAIAdapter", "AnthropicAdapter", "OllamaAdapter"):
        real_cls = getattr(extraction_task, name)
        calls[name] = []

        def spy(
            *args: Any,
            _name: str = name,
            _real_cls: type = real_cls,
            **kwargs: Any,
        ) -> Any:
            calls[_name].append({"args": args, "kwargs": kwargs})
            return _real_cls(*args, **kwargs)

        monkeypatch.setattr(extraction_task, name, spy)

    return calls


class TestKnownCloudProviders:
    """The four known provider names keep their existing adapter mapping."""

    @pytest.mark.unit
    def test_gemini_with_key_selects_gemini_adapter(
        self, adapter_spies: dict[str, list[dict[str, Any]]]
    ) -> None:
        """Gemini routes to GeminiAdapter and is given no base URL."""
        result = extraction_task._build_llm_port(
            "gemini", api_key="gemini-key", base_url="https://ignored.example/v1"
        )

        assert isinstance(result, GeminiAdapter)
        assert adapter_spies["GeminiAdapter"][0]["kwargs"] == {"api_key": "gemini-key"}

    @pytest.mark.unit
    def test_openai_with_key_forwards_base_url(
        self, adapter_spies: dict[str, list[dict[str, Any]]]
    ) -> None:
        """OpenAI forwards the configured base URL for compatible gateways."""
        result = extraction_task._build_llm_port(
            "openai", api_key="openai-key", base_url="https://proxy.example/v1"
        )

        assert isinstance(result, OpenAIAdapter)
        assert adapter_spies["OpenAIAdapter"][0]["kwargs"] == {
            "api_key": "openai-key",
            "base_url": "https://proxy.example/v1",
        }

    @pytest.mark.unit
    def test_anthropic_with_key_forwards_base_url(
        self, adapter_spies: dict[str, list[dict[str, Any]]]
    ) -> None:
        """Anthropic forwards the configured base URL for compatible gateways."""
        result = extraction_task._build_llm_port(
            "anthropic", api_key="anthropic-key", base_url="https://proxy.example/v1"
        )

        assert isinstance(result, AnthropicAdapter)
        assert adapter_spies["AnthropicAdapter"][0]["kwargs"] == {
            "api_key": "anthropic-key",
            "base_url": "https://proxy.example/v1",
        }

    @pytest.mark.unit
    @pytest.mark.parametrize(
        ("provider", "message"),
        [
            (
                "gemini",
                "Gemini API key is not configured for this workspace. "
                "Set it in Workspace Settings before extracting.",
            ),
            (
                "openai",
                "OpenAI API key is not configured for this workspace. "
                "Set it in Workspace Settings before extracting.",
            ),
            (
                "anthropic",
                "Anthropic API key is not configured for this workspace. "
                "Set it in Workspace Settings before extracting.",
            ),
        ],
    )
    def test_cloud_provider_without_key_raises(
        self,
        provider: str,
        message: str,
        adapter_spies: dict[str, list[dict[str, Any]]],
    ) -> None:
        """A cloud provider with no workspace key fails instead of degrading."""
        with pytest.raises(LLMError) as exc_info:
            extraction_task._build_llm_port(provider, api_key=None, base_url="https://proxy/v1")

        assert str(exc_info.value) == message


class TestOllamaProvider:
    """Ollama is an explicit branch, no longer the catch-all fallback."""

    @pytest.mark.unit
    def test_ollama_uses_configured_base_url(
        self, adapter_spies: dict[str, list[dict[str, Any]]]
    ) -> None:
        """A configured base URL wins over the host default."""
        result = extraction_task._build_llm_port(
            "ollama", base_url="http://gpu-box:11434", ollama_host=OLLAMA_HOST
        )

        assert isinstance(result, OllamaAdapter)
        assert result._base_url == "http://gpu-box:11434"
        assert adapter_spies["OllamaAdapter"][0]["kwargs"] == {"base_url": "http://gpu-box:11434"}

    @pytest.mark.unit
    def test_ollama_falls_back_to_ollama_host(
        self, adapter_spies: dict[str, list[dict[str, Any]]]
    ) -> None:
        """Without an override the caller-supplied Ollama host is used."""
        result = extraction_task._build_llm_port("ollama", base_url=None, ollama_host=OLLAMA_HOST)

        assert isinstance(result, OllamaAdapter)
        assert result._base_url == OLLAMA_HOST
        assert adapter_spies["OllamaAdapter"][0]["kwargs"] == {"base_url": OLLAMA_HOST}

    @pytest.mark.unit
    @pytest.mark.parametrize("blank", ["", "   ", "\t\n"])
    def test_a_blank_endpoint_is_the_default_not_a_url_of_spaces(
        self, adapter_spies: dict[str, list[dict[str, Any]]], blank: str
    ) -> None:
        """A blank endpoint is absent, so the host default wins.

        Before this, the spaces were truthy: the adapter was built with a URL of spaces and
        the call failed inside the background task, after the extraction record existed.
        """
        result = extraction_task._build_llm_port("ollama", base_url=blank, ollama_host=OLLAMA_HOST)

        assert isinstance(result, OllamaAdapter)
        assert result._base_url == OLLAMA_HOST
        assert adapter_spies["OllamaAdapter"][0]["kwargs"] == {"base_url": OLLAMA_HOST}


class TestBlankCredentials:
    """A credential made of whitespace is a missing credential, at the last boundary."""

    @pytest.mark.unit
    @pytest.mark.parametrize("provider", ["openai", "anthropic", "gemini"])
    @pytest.mark.parametrize("blank", ["", "   ", "\t\n"])
    def test_a_blank_credential_is_refused(self, provider: str, blank: str) -> None:
        """It used to build an adapter with a blank key and fail on the call instead."""
        with pytest.raises(LLMError):
            extraction_task._build_llm_port(provider, api_key=blank)

    @pytest.mark.unit
    def test_a_blank_credential_on_a_custom_provider_uses_the_placeholder(
        self, adapter_spies: dict[str, list[dict[str, Any]]]
    ) -> None:
        """A custom provider's key is optional, so blank means "no key", not "a blank key"."""
        result = extraction_task._build_llm_port(
            "deepseek", api_key="   ", base_url=CUSTOM_BASE_URL
        )

        assert isinstance(result, OpenAIAdapter)
        # The placeholder the port substitutes when a gateway needs no credential.
        assert (
            adapter_spies["OpenAIAdapter"][0]["kwargs"]["api_key"]
            == CUSTOM_PROVIDER_PLACEHOLDER_KEY
        )


class TestCustomProviders:
    """Workspace-defined providers are OpenAI-compatible endpoints."""

    @pytest.mark.unit
    def test_custom_provider_selects_openai_adapter(
        self, adapter_spies: dict[str, list[dict[str, Any]]]
    ) -> None:
        """``deepseek`` reaches its own endpoint instead of the local Ollama host."""
        result = extraction_task._build_llm_port(
            "deepseek",
            api_key="deepseek-key",
            base_url=CUSTOM_BASE_URL,
            ollama_host=OLLAMA_HOST,
        )

        assert not isinstance(result, OllamaAdapter)
        assert isinstance(result, OpenAIAdapter)
        assert adapter_spies["OllamaAdapter"] == []
        assert adapter_spies["OpenAIAdapter"][0]["kwargs"] == {
            "api_key": "deepseek-key",
            "base_url": CUSTOM_BASE_URL,
        }

    @pytest.mark.unit
    def test_custom_provider_without_key_uses_placeholder(
        self, adapter_spies: dict[str, list[dict[str, Any]]]
    ) -> None:
        """Unauthenticated gateways stay reachable without an ambient credential."""
        result = extraction_task._build_llm_port("local-vllm", base_url="http://vllm.lan:8000/v1")

        assert isinstance(result, OpenAIAdapter)
        assert adapter_spies["OpenAIAdapter"][0]["kwargs"] == {
            "api_key": "no-key-required",
            "base_url": "http://vllm.lan:8000/v1",
        }

    @pytest.mark.unit
    def test_custom_provider_with_key_ignores_placeholder(
        self, adapter_spies: dict[str, list[dict[str, Any]]]
    ) -> None:
        """A stored workspace key is the only credential a custom provider uses."""
        result = extraction_task._build_llm_port(
            "deepseek", api_key="deepseek-key", base_url=CUSTOM_BASE_URL
        )

        assert isinstance(result, OpenAIAdapter)
        assert adapter_spies["OpenAIAdapter"][0]["kwargs"] == {
            "api_key": "deepseek-key",
            "base_url": CUSTOM_BASE_URL,
        }

    @pytest.mark.unit
    def test_custom_provider_without_base_url_raises(
        self, adapter_spies: dict[str, list[dict[str, Any]]]
    ) -> None:
        """A custom provider with nowhere to call fails loudly."""
        with pytest.raises(LLMError) as exc_info:
            extraction_task._build_llm_port(
                "deepseek", api_key="deepseek-key", ollama_host=OLLAMA_HOST
            )

        message = str(exc_info.value)
        assert "deepseek" in message
        assert "Base URL" in message
        assert adapter_spies["OpenAIAdapter"] == []
        assert adapter_spies["OllamaAdapter"] == []

    @pytest.mark.unit
    @pytest.mark.parametrize("provider", ["deepseek", "mistral", "unknown-vendor", ""])
    def test_unknown_provider_never_selects_ollama(
        self, provider: str, adapter_spies: dict[str, list[dict[str, Any]]]
    ) -> None:
        """Branch ordering keeps every unknown name off the Ollama fallback."""
        result = extraction_task._build_llm_port(
            provider, api_key="key", base_url=CUSTOM_BASE_URL, ollama_host=OLLAMA_HOST
        )

        assert isinstance(result, OpenAIAdapter)
        assert not isinstance(result, OllamaAdapter)
        assert adapter_spies["OllamaAdapter"] == []
