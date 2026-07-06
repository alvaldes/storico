"""Unit tests for OllamaAdapter — EXT-T20.

Uses unittest.mock to mock httpx.AsyncClient so no real network calls happen.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock

from httpx import ConnectError

from storico.domain.entities import LLMConnectionError, LLMModelNotFoundError, LLMResponseError
from storico.domain.ports import LLMConfig
from storico.infrastructure.llm.ollama_adapter import OllamaAdapter


class TestOllamaAdapter:
    """OllamaAdapter wraps the Ollama /api/chat endpoint.

    Tests use a mock httpx.AsyncClient to avoid real HTTP calls.
    """

    def setup_method(self) -> None:
        self.config = LLMConfig(model="llama3.2")
        self.base_url = "http://localhost:11434"

    # ── Successful generation ───────────────────────────────────────

    @pytest.mark.asyncio
    async def test_generate_success(self) -> None:
        """Successful LLM call returns raw text."""
        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "message": {"content": "1. summary: Task one\ndescription: Do it"}
        }
        mock_client.post.return_value = mock_response

        adapter = OllamaAdapter(base_url=self.base_url, client=mock_client)
        result = await adapter.generate("Test prompt", self.config)
        assert "Task one" in result

    @pytest.mark.asyncio
    async def test_generate_returns_full_text(self) -> None:
        """Full response text is returned as-is."""
        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        expected = "1. summary: Task one\ndescription: Do it\n2. summary: Task two\ndescription: Do that"
        mock_response.json.return_value = {"message": {"content": expected}}
        mock_client.post.return_value = mock_response

        adapter = OllamaAdapter(base_url=self.base_url, client=mock_client)
        result = await adapter.generate("Prompt", self.config)
        assert result == expected

    # ── Retries on connection error ─────────────────────────────────

    @pytest.mark.asyncio
    async def test_generate_connection_error_retries(self) -> None:
        """Connection error retries 3 times then raises LLMConnectionError."""
        mock_client = AsyncMock()
        mock_client.post.side_effect = ConnectError("Connection refused")

        adapter = OllamaAdapter(base_url=self.base_url, client=mock_client)
        with pytest.raises(LLMConnectionError):
            await adapter.generate("Test prompt", self.config)
        assert mock_client.post.call_count == 3

    @pytest.mark.asyncio
    async def test_generate_timeout_retries(self) -> None:
        """Timeout error also triggers retry then raises LLMConnectionError."""
        mock_client = AsyncMock()
        from httpx import TimeoutException

        mock_client.post.side_effect = TimeoutException("Timed out")

        adapter = OllamaAdapter(base_url=self.base_url, client=mock_client)
        with pytest.raises(LLMConnectionError):
            await adapter.generate("Test prompt", self.config)
        assert mock_client.post.call_count == 3

    @pytest.mark.asyncio
    async def test_generate_retry_succeeds_on_second_attempt(self) -> None:
        """Retry succeeds after an initial connection failure."""
        mock_client = AsyncMock()
        mock_client.post.side_effect = [
            ConnectError("First attempt failed"),
            MagicMock(
                status_code=200,
                json=lambda: {"message": {"content": "1. summary: Retried task\ndescription: Done"}},
            ),
        ]

        adapter = OllamaAdapter(base_url=self.base_url, client=mock_client)
        result = await adapter.generate("Test prompt", self.config)
        assert "Retried task" in result
        assert mock_client.post.call_count == 2

    # ── HTTP error responses ────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_generate_404_raises_model_not_found(self) -> None:
        """404 from Ollama raises LLMModelNotFoundError."""
        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_client.post.return_value = mock_response

        adapter = OllamaAdapter(base_url=self.base_url, client=mock_client)
        with pytest.raises(LLMModelNotFoundError):
            await adapter.generate("Test prompt", self.config)

    @pytest.mark.asyncio
    async def test_generate_500_raises_response_error(self) -> None:
        """500 from Ollama raises LLMResponseError."""
        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"
        mock_client.post.return_value = mock_response

        adapter = OllamaAdapter(base_url=self.base_url, client=mock_client)
        with pytest.raises(LLMResponseError):
            await adapter.generate("Test prompt", self.config)

    @pytest.mark.asyncio
    async def test_generate_400_raises_response_error(self) -> None:
        """400 from Ollama raises LLMResponseError."""
        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.text = "Bad Request"
        mock_client.post.return_value = mock_response

        adapter = OllamaAdapter(base_url=self.base_url, client=mock_client)
        with pytest.raises(LLMResponseError):
            await adapter.generate("Test prompt", self.config)

    # ── Payload structure ──────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_build_payload(self) -> None:
        """Payload structure matches Ollama /api/chat format."""
        adapter = OllamaAdapter(base_url=self.base_url)
        payload = adapter._build_payload("Test prompt", self.config)
        assert payload["model"] == "llama3.2"
        assert len(payload["messages"]) == 2
        assert payload["messages"][0]["role"] == "system"
        assert payload["messages"][1]["role"] == "user"
        assert payload["messages"][1]["content"] == "Test prompt"
        assert payload["options"]["temperature"] == 0.1
        assert payload["options"]["num_predict"] == 2048

    @pytest.mark.asyncio
    async def test_build_payload_custom_model(self) -> None:
        """Custom model name appears in payload."""
        custom_config = LLMConfig(model="mistral")
        adapter = OllamaAdapter(base_url=self.base_url)
        payload = adapter._build_payload("Prompt", custom_config)
        assert payload["model"] == "mistral"

    @pytest.mark.asyncio
    async def test_build_payload_custom_params(self) -> None:
        """Custom temperature and max_tokens appear in payload."""
        custom = LLMConfig(model="test", temperature=0.5, max_tokens=4096)
        adapter = OllamaAdapter(base_url=self.base_url)
        payload = adapter._build_payload("Prompt", custom)
        assert payload["options"]["temperature"] == 0.5
        assert payload["options"]["num_predict"] == 4096

    # ── Response parsing ────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_parse_response_missing_message_key(self) -> None:
        """Missing 'message' key raises LLMResponseError."""
        adapter = OllamaAdapter(base_url=self.base_url)
        with pytest.raises(LLMResponseError):
            adapter._parse_response({"wrong_key": "value"})

    @pytest.mark.asyncio
    async def test_parse_response_missing_content_key(self) -> None:
        """Missing 'content' in message raises LLMResponseError."""
        adapter = OllamaAdapter(base_url=self.base_url)
        with pytest.raises(LLMResponseError):
            adapter._parse_response({"message": {"role": "assistant"}})

    # ── No retry on non-connection errors ──────────────────────────

    @pytest.mark.asyncio
    async def test_generate_404_no_retry(self) -> None:
        """404 does NOT retry — only connection errors retry."""
        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_client.post.return_value = mock_response

        adapter = OllamaAdapter(base_url=self.base_url, client=mock_client)
        with pytest.raises(LLMModelNotFoundError):
            await adapter.generate("Test prompt", self.config)
        assert mock_client.post.call_count == 1
