"""Unit tests for OpenAIAdapter.

Uses unittest.mock to mock the openai.AsyncOpenAI client so no real API calls
happen. Verifies that OpenAI sends the system prompt as a system message.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from openai import APIConnectionError, NotFoundError, OpenAIError

from storico.domain.entities import LLMConnectionError, LLMModelNotFoundError, LLMResponseError
from storico.domain.ports import LLMConfig
from storico.infrastructure.llm.openai_adapter import OpenAIAdapter


def _mock_response(content: str | None) -> MagicMock:
    """Build a fake chat completion response exposing .choices[0].message.content."""
    response = MagicMock()
    response.choices = [MagicMock()]
    response.choices[0].message.content = content
    return response


def _not_found_error(model: str) -> NotFoundError:
    """Build a real NotFoundError with the response/body the SDK requires."""
    return NotFoundError(
        model,
        response=MagicMock(status_code=404, headers={}, request=MagicMock()),
        body=None,
    )


class TestOpenAIAdapter:
    """OpenAIAdapter wraps the openai client's chat.completions.create."""

    def setup_method(self) -> None:
        self.config = LLMConfig(model="gpt-3.5-turbo")

    @patch("storico.infrastructure.llm.openai_adapter.AsyncOpenAI")
    @pytest.mark.asyncio
    async def test_generate_success(self, mock_client_cls: MagicMock) -> None:
        """Successful generation returns the model text response."""
        mock_client_cls.return_value.chat.completions.create = AsyncMock(
            return_value=_mock_response("1. summary: Task one\ndescription: Do it")
        )

        adapter = OpenAIAdapter(api_key="test-key")
        result = await adapter.generate("Test prompt", self.config)

        assert "Task one" in result
        mock_client_cls.assert_called_once_with(api_key="test-key", base_url=None)

    @patch("storico.infrastructure.llm.openai_adapter.AsyncOpenAI")
    @pytest.mark.asyncio
    async def test_generate_sends_passed_system_prompt(self, mock_client_cls: MagicMock) -> None:
        """Passed system prompt is sent as a system message."""
        create = AsyncMock(return_value=_mock_response("ok"))
        mock_client_cls.return_value.chat.completions.create = create

        adapter = OpenAIAdapter(api_key="test-key")
        await adapter.generate("Test prompt", self.config, system_prompt="System role")

        call_kwargs = create.call_args.kwargs
        assert call_kwargs["model"] == "gpt-3.5-turbo"
        assert call_kwargs["temperature"] == 0.1
        assert call_kwargs["max_tokens"] == 2048
        assert call_kwargs["messages"] == [
            {"role": "system", "content": "System role"},
            {"role": "user", "content": "Test prompt"},
        ]

    @patch("storico.infrastructure.llm.openai_adapter.AsyncOpenAI")
    @pytest.mark.asyncio
    async def test_generate_without_system_prompt(self, mock_client_cls: MagicMock) -> None:
        """No system message when system_prompt is None."""
        create = AsyncMock(return_value=_mock_response("ok"))
        mock_client_cls.return_value.chat.completions.create = create

        adapter = OpenAIAdapter(api_key="test-key")
        await adapter.generate("Test prompt", self.config)

        assert create.call_args.kwargs["messages"] == [
            {"role": "user", "content": "Test prompt"},
        ]

    @patch("storico.infrastructure.llm.openai_adapter.AsyncOpenAI")
    @pytest.mark.asyncio
    async def test_generate_sdk_connection_error_raises(self, mock_client_cls: MagicMock) -> None:
        """OpenAI APIConnectionError is wrapped in LLMConnectionError."""
        mock_client_cls.return_value.chat.completions.create = AsyncMock(
            side_effect=APIConnectionError(request=MagicMock())
        )

        adapter = OpenAIAdapter(api_key="test-key")
        with pytest.raises(LLMConnectionError):
            await adapter.generate("Test prompt", self.config)

    @patch("storico.infrastructure.llm.openai_adapter.AsyncOpenAI")
    @pytest.mark.asyncio
    async def test_generate_sdk_not_found_error_raises(self, mock_client_cls: MagicMock) -> None:
        """OpenAI NotFoundError is wrapped in LLMModelNotFoundError."""
        mock_client_cls.return_value.chat.completions.create = AsyncMock(
            side_effect=_not_found_error("gpt-3.5-turbo")
        )

        adapter = OpenAIAdapter(api_key="test-key")
        with pytest.raises(LLMModelNotFoundError) as exc_info:
            await adapter.generate("Test prompt", self.config)
        assert exc_info.value.model == "gpt-3.5-turbo"

    @patch("storico.infrastructure.llm.openai_adapter.AsyncOpenAI")
    @pytest.mark.asyncio
    async def test_generate_sdk_other_error_raises(self, mock_client_cls: MagicMock) -> None:
        """Other OpenAI errors are wrapped in LLMResponseError."""
        mock_client_cls.return_value.chat.completions.create = AsyncMock(
            side_effect=OpenAIError("Bad request")
        )

        adapter = OpenAIAdapter(api_key="test-key")
        with pytest.raises(LLMResponseError):
            await adapter.generate("Test prompt", self.config)

    @patch("storico.infrastructure.llm.openai_adapter.AsyncOpenAI")
    @pytest.mark.asyncio
    async def test_generate_empty_response_raises(self, mock_client_cls: MagicMock) -> None:
        """Empty response content raises LLMResponseError."""
        mock_client_cls.return_value.chat.completions.create = AsyncMock(
            return_value=_mock_response(None)
        )

        adapter = OpenAIAdapter(api_key="test-key")
        with pytest.raises(LLMResponseError):
            await adapter.generate("Test prompt", self.config)
