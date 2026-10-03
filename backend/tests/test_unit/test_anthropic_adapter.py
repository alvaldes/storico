"""Unit tests for AnthropicAdapter.

Uses unittest.mock to mock the anthropic.AsyncAnthropic client so no real API
calls happen. Verifies that Anthropic sends the system prompt via the
``system`` parameter.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from anthropic import AnthropicError, APIConnectionError, NotFoundError

from storico.domain.entities import LLMConnectionError, LLMModelNotFoundError, LLMResponseError
from storico.domain.ports import LLMConfig
from storico.infrastructure.llm.anthropic_adapter import AnthropicAdapter


def _mock_response(text: str | None, usage: dict | None = None) -> MagicMock:
    """Build a fake messages response exposing a single text content block.

    ``usage`` is the dict the SDK's ``response.usage.model_dump()`` would return;
    ``None`` builds a response with no usage object at all, like a provider that
    omits the container.
    """
    response = MagicMock()
    block = MagicMock()
    block.type = "text"
    block.text = text
    response.content = [block] if text is not None else []
    if usage is None:
        response.usage = None
    else:
        usage_obj = MagicMock()
        usage_obj.model_dump.return_value = usage
        response.usage = usage_obj
    return response


def _not_found_error(model: str) -> NotFoundError:
    """Build a real NotFoundError with the response/body the SDK requires."""
    return NotFoundError(
        model,
        response=MagicMock(status_code=404, headers={}, request=MagicMock()),
        body=None,
    )


class TestAnthropicAdapter:
    """AnthropicAdapter wraps the anthropic client's messages.create."""

    def setup_method(self) -> None:
        self.config = LLMConfig(model="claude-3-haiku-20240307")

    @patch("storico.infrastructure.llm.anthropic_adapter.AsyncAnthropic")
    @pytest.mark.asyncio
    async def test_generate_success(self, mock_client_cls: MagicMock) -> None:
        """Successful generation returns the model text response."""
        mock_client_cls.return_value.messages.create = AsyncMock(
            return_value=_mock_response("1. summary: Task one\ndescription: Do it")
        )

        adapter = AnthropicAdapter(api_key="test-key")
        result = await adapter.generate("Test prompt", self.config)

        assert "Task one" in result.text
        assert result.usage is None
        mock_client_cls.assert_called_once_with(api_key="test-key", base_url=None)

    @patch("storico.infrastructure.llm.anthropic_adapter.AsyncAnthropic")
    @pytest.mark.asyncio
    async def test_generate_carries_the_provider_usage_container_verbatim(
        self, mock_client_cls: MagicMock
    ) -> None:
        """The SDK usage object's ``model_dump()`` rides along untouched (2.7).

        The Anthropic SDK exposes token usage as ``response.usage``, a pydantic
        model with ``model_dump()``. The adapter copies that dump verbatim —
        no renaming, no derived totals, no normalization into a common shape.
        """
        create = AsyncMock(
            return_value=_mock_response(
                "1. summary: Task one\ndescription: Do it",
                usage={"input_tokens": 41, "output_tokens": 117},
            )
        )
        mock_client_cls.return_value.messages.create = create

        adapter = AnthropicAdapter(api_key="test-key")
        result = await adapter.generate("Test prompt", self.config)

        assert result.usage == {"input_tokens": 41, "output_tokens": 117}

    @patch("storico.infrastructure.llm.anthropic_adapter.AsyncAnthropic")
    @pytest.mark.asyncio
    async def test_generate_sends_passed_system_prompt(self, mock_client_cls: MagicMock) -> None:
        """Passed system prompt is sent via the ``system`` kwarg."""
        create = AsyncMock(return_value=_mock_response("ok"))
        mock_client_cls.return_value.messages.create = create

        adapter = AnthropicAdapter(api_key="test-key")
        await adapter.generate("Test prompt", self.config, system_prompt="System role")

        call_kwargs = create.call_args.kwargs
        assert call_kwargs["model"] == "claude-3-haiku-20240307"
        assert call_kwargs["max_tokens"] == 2048
        assert call_kwargs["temperature"] == 0.1
        assert call_kwargs["system"] == "System role"
        assert call_kwargs["messages"] == [
            {"role": "user", "content": "Test prompt"},
        ]

    @patch("storico.infrastructure.llm.anthropic_adapter.AsyncAnthropic")
    @pytest.mark.asyncio
    async def test_generate_without_system_prompt(self, mock_client_cls: MagicMock) -> None:
        """No system kwarg when system_prompt is None."""
        create = AsyncMock(return_value=_mock_response("ok"))
        mock_client_cls.return_value.messages.create = create

        adapter = AnthropicAdapter(api_key="test-key")
        await adapter.generate("Test prompt", self.config)

        assert "system" not in create.call_args.kwargs
        assert create.call_args.kwargs["messages"] == [
            {"role": "user", "content": "Test prompt"},
        ]

    @patch("storico.infrastructure.llm.anthropic_adapter.AsyncAnthropic")
    @pytest.mark.asyncio
    async def test_generate_sdk_connection_error_raises(self, mock_client_cls: MagicMock) -> None:
        """Anthropic APIConnectionError is wrapped in LLMConnectionError."""
        mock_client_cls.return_value.messages.create = AsyncMock(
            side_effect=APIConnectionError(request=MagicMock())
        )

        adapter = AnthropicAdapter(api_key="test-key")
        with pytest.raises(LLMConnectionError):
            await adapter.generate("Test prompt", self.config)

    @patch("storico.infrastructure.llm.anthropic_adapter.AsyncAnthropic")
    @pytest.mark.asyncio
    async def test_generate_sdk_not_found_error_raises(self, mock_client_cls: MagicMock) -> None:
        """Anthropic NotFoundError is wrapped in LLMModelNotFoundError."""
        mock_client_cls.return_value.messages.create = AsyncMock(
            side_effect=_not_found_error("claude-3-haiku-20240307")
        )

        adapter = AnthropicAdapter(api_key="test-key")
        with pytest.raises(LLMModelNotFoundError) as exc_info:
            await adapter.generate("Test prompt", self.config)
        assert exc_info.value.model == "claude-3-haiku-20240307"

    @patch("storico.infrastructure.llm.anthropic_adapter.AsyncAnthropic")
    @pytest.mark.asyncio
    async def test_generate_sdk_other_error_raises(self, mock_client_cls: MagicMock) -> None:
        """Other Anthropic errors are wrapped in LLMResponseError."""
        mock_client_cls.return_value.messages.create = AsyncMock(
            side_effect=AnthropicError("Bad request")
        )

        adapter = AnthropicAdapter(api_key="test-key")
        with pytest.raises(LLMResponseError):
            await adapter.generate("Test prompt", self.config)

    @patch("storico.infrastructure.llm.anthropic_adapter.AsyncAnthropic")
    @pytest.mark.asyncio
    async def test_generate_empty_response_raises(self, mock_client_cls: MagicMock) -> None:
        """Empty response content raises LLMResponseError."""
        mock_client_cls.return_value.messages.create = AsyncMock(return_value=_mock_response(None))

        adapter = AnthropicAdapter(api_key="test-key")
        with pytest.raises(LLMResponseError):
            await adapter.generate("Test prompt", self.config)
