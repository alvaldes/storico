"""Unit tests for GeminiAdapter.

Uses unittest.mock to mock the google-genai Client so no real API calls
happen. Verifies that Gemini sends the shared system prompt via the
``system_instruction`` field of ``GenerateContentConfig``.
"""

from unittest.mock import MagicMock, patch

import pytest

from storico.domain.entities import LLMConnectionError, LLMResponseError
from storico.domain.ports import LLMConfig
from storico.infrastructure.llm.gemini_adapter import GeminiAdapter
from storico.infrastructure.llm.ollama_adapter import OllamaAdapter


class TestGeminiAdapter:
    """GeminiAdapter wraps the google-genai client's generate_content."""

    def setup_method(self) -> None:
        self.config = LLMConfig(model="gemini-2.0-flash")

    @patch("storico.infrastructure.llm.gemini_adapter.genai.Client")
    @pytest.mark.asyncio
    async def test_generate_success(self, mock_client_cls: MagicMock) -> None:
        """Successful generation returns the model text response."""
        mock_response = MagicMock()
        mock_response.text = "1. summary: Task one\ndescription: Do it"
        mock_client_cls.return_value.models.generate_content.return_value = mock_response

        adapter = GeminiAdapter(api_key="test-key")
        result = await adapter.generate("Test prompt", self.config)

        assert "Task one" in result
        mock_client_cls.assert_called_once_with(api_key="test-key")

    @patch("storico.infrastructure.llm.gemini_adapter.genai.Client")
    @pytest.mark.asyncio
    async def test_generate_sends_passed_system_prompt(self, mock_client_cls: MagicMock) -> None:
        """Passed system prompt is sent via GenerateContentConfig.system_instruction."""
        mock_response = MagicMock()
        mock_response.text = "1. summary: Task one\ndescription: Do it"
        mock_client_cls.return_value.models.generate_content.return_value = mock_response

        adapter = GeminiAdapter(api_key="test-key")
        await adapter.generate("Test prompt", self.config, system_prompt="System role")

        call_kwargs = mock_client_cls.return_value.models.generate_content.call_args.kwargs
        assert call_kwargs["model"] == "gemini-2.0-flash"
        assert call_kwargs["contents"] == "Test prompt"
        config = call_kwargs["config"]
        assert config.system_instruction == "System role"

    @patch("storico.infrastructure.llm.gemini_adapter.genai.Client")
    @pytest.mark.asyncio
    async def test_generate_without_system_prompt(self, mock_client_cls: MagicMock) -> None:
        """No system_instruction when system_prompt is None."""
        mock_response = MagicMock()
        mock_response.text = "ok"
        mock_client_cls.return_value.models.generate_content.return_value = mock_response

        adapter = GeminiAdapter(api_key="test-key")
        await adapter.generate("Test prompt", self.config)

        config = mock_client_cls.return_value.models.generate_content.call_args.kwargs["config"]
        assert config.system_instruction is None

    @patch("storico.infrastructure.llm.gemini_adapter.genai.Client")
    @pytest.mark.asyncio
    async def test_adapters_use_exact_same_system_prompt(self, mock_client_cls: MagicMock) -> None:
        """Gemini and Ollama send the exact same system prompt string."""
        mock_response = MagicMock()
        mock_response.text = "ok"
        mock_client_cls.return_value.models.generate_content.return_value = mock_response

        gemini = GeminiAdapter(api_key="test-key")
        await gemini.generate("Test prompt", self.config, system_prompt="Shared role")

        ollama_payload = OllamaAdapter(base_url="http://localhost:11434")._build_payload(
            "Test prompt", self.config, system_prompt="Shared role"
        )

        gemini_system = (
            mock_client_cls.return_value.models.generate_content.call_args.kwargs["config"]
            .system_instruction
        )
        ollama_system = ollama_payload["messages"][0]["content"]

        assert gemini_system == ollama_system
        assert gemini_system == "Shared role"

    @patch("storico.infrastructure.llm.gemini_adapter.genai.Client")
    @pytest.mark.asyncio
    async def test_generate_sdk_error_raises_connection_error(
        self, mock_client_cls: MagicMock
    ) -> None:
        """SDK exceptions are wrapped in LLMConnectionError."""
        mock_client_cls.return_value.models.generate_content.side_effect = RuntimeError("boom")

        adapter = GeminiAdapter(api_key="test-key")
        with pytest.raises(LLMConnectionError):
            await adapter.generate("Test prompt", self.config)

    @patch("storico.infrastructure.llm.gemini_adapter.genai.Client")
    @pytest.mark.asyncio
    async def test_generate_empty_response_raises(self, mock_client_cls: MagicMock) -> None:
        """Empty response text raises LLMResponseError."""
        mock_response = MagicMock()
        mock_response.text = None
        mock_client_cls.return_value.models.generate_content.return_value = mock_response

        adapter = GeminiAdapter(api_key="test-key")
        with pytest.raises(LLMResponseError):
            await adapter.generate("Test prompt", self.config)
