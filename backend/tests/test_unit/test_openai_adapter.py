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


def _mock_response(
    content: str | None,
    usage: dict | None = None,
    finish_reason: str | None = "stop",
    refusal: str | None = None,
) -> MagicMock:
    """Build a fake chat completion response exposing .choices[0].message.content.

    ``usage`` is the dict the SDK's ``response.usage.model_dump()`` would return;
    ``None`` builds a response with no usage object at all, like a provider that
    omits the container. ``finish_reason`` and ``refusal`` are set explicitly because
    a bare ``MagicMock`` invents truthy attributes for both, and the empty-response
    diagnosis reads them.
    """
    response = MagicMock()
    response.choices = [MagicMock()]
    response.choices[0].message.content = content
    response.choices[0].finish_reason = finish_reason
    response.choices[0].message.refusal = refusal
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

        assert "Task one" in result.text
        assert result.usage is None
        mock_client_cls.assert_called_once_with(api_key="test-key", base_url=None)

    @patch("storico.infrastructure.llm.openai_adapter.AsyncOpenAI")
    @pytest.mark.asyncio
    async def test_generate_carries_the_provider_usage_container_verbatim(
        self, mock_client_cls: MagicMock
    ) -> None:
        """The SDK usage object's ``model_dump()`` rides along untouched (2.7).

        The OpenAI SDK exposes token usage as ``response.usage``, a pydantic
        model with ``model_dump()``. The adapter copies that dump verbatim —
        no renaming, no derived totals, no normalization into a common shape.
        """
        create = AsyncMock(
            return_value=_mock_response(
                "1. summary: Task one\ndescription: Do it",
                usage={"prompt_tokens": 41, "completion_tokens": 117, "total_tokens": 158},
            )
        )
        mock_client_cls.return_value.chat.completions.create = create

        adapter = OpenAIAdapter(api_key="test-key")
        result = await adapter.generate("Test prompt", self.config)

        assert result.usage == {
            "prompt_tokens": 41,
            "completion_tokens": 117,
            "total_tokens": 158,
        }

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


class TestEmptyResponseDiagnosis:
    """A 200 with no content is diagnosed from what the provider did report.

    The adapter serves OpenAI *and* every workspace-registered OpenAI-compatible
    provider (``_build_llm_port`` sends any unknown name here), so the failure has to be
    readable without knowing which one it was. The provider's own facts —
    ``finish_reason``, whether a refusal came back, the completion-token count against
    the budget that was sent — are the difference between "it returned nothing" and a
    cause the reader can act on.
    """

    def setup_method(self) -> None:
        self.config = LLMConfig(model="gpt-3.5-turbo", max_tokens=2048)

    @patch("storico.infrastructure.llm.openai_adapter.AsyncOpenAI")
    @pytest.mark.asyncio
    async def test_the_message_names_no_vendor(self, mock_client_cls: MagicMock) -> None:
        """The shared adapter does not attribute a custom provider's failure to OpenAI."""
        mock_client_cls.return_value.chat.completions.create = AsyncMock(
            return_value=_mock_response(None)
        )

        adapter = OpenAIAdapter(api_key="test-key")
        with pytest.raises(LLMResponseError) as exc_info:
            await adapter.generate("Test prompt", self.config)

        assert "OpenAI" not in str(exc_info.value)
        assert "empty response" in str(exc_info.value)

    @patch("storico.infrastructure.llm.openai_adapter.AsyncOpenAI")
    @pytest.mark.asyncio
    async def test_a_budget_exhaustion_names_the_budget_and_the_way_out(
        self, mock_client_cls: MagicMock
    ) -> None:
        """``finish_reason: length`` says the output budget ran out and how to raise it."""
        mock_client_cls.return_value.chat.completions.create = AsyncMock(
            return_value=_mock_response(
                None,
                usage={
                    "prompt_tokens": 900,
                    "completion_tokens": 2048,
                    "total_tokens": 2948,
                },
                finish_reason="length",
            )
        )

        adapter = OpenAIAdapter(api_key="test-key")
        with pytest.raises(LLMResponseError) as exc_info:
            await adapter.generate("Test prompt", self.config)

        message = str(exc_info.value)
        assert "length" in message
        assert "2048" in message
        assert "max tokens" in message.lower()

    @patch("storico.infrastructure.llm.openai_adapter.AsyncOpenAI")
    @pytest.mark.asyncio
    async def test_a_refusal_is_reported_as_a_refusal(self, mock_client_cls: MagicMock) -> None:
        """A refusal returned with no content is not reported as an unexplained emptiness."""
        mock_client_cls.return_value.chat.completions.create = AsyncMock(
            return_value=_mock_response(None, refusal="I cannot help with that")
        )

        adapter = OpenAIAdapter(api_key="test-key")
        with pytest.raises(LLMResponseError) as exc_info:
            await adapter.generate("Test prompt", self.config)

        assert "refus" in str(exc_info.value).lower()

    @patch("storico.infrastructure.llm.openai_adapter.AsyncOpenAI")
    @pytest.mark.asyncio
    async def test_the_log_carries_the_provider_facts(
        self, mock_client_cls: MagicMock, caplog: pytest.LogCaptureFixture
    ) -> None:
        """The warning records finish_reason, refusal presence and the budget that was sent.

        The message reaches the user through the extraction row; the log is where an
        operator reads the numbers. Neither may carry the response body — a provider's
        text is exactly what this diagnosis is not allowed to publish.
        """
        mock_client_cls.return_value.chat.completions.create = AsyncMock(
            return_value=_mock_response(
                None,
                usage={
                    "prompt_tokens": 900,
                    "completion_tokens": 2048,
                    "total_tokens": 2948,
                },
                finish_reason="length",
            )
        )

        adapter = OpenAIAdapter(api_key="test-key")
        with caplog.at_level("WARNING", logger="storico.infrastructure.llm.openai_adapter"):
            with pytest.raises(LLMResponseError):
                await adapter.generate("Test prompt", self.config)

        record = caplog.records[0]
        assert record.finish_reason == "length"
        assert record.completion_tokens == 2048
        assert record.max_tokens == 2048
        assert record.refusal_present is False
        assert record.model == "gpt-3.5-turbo"


def _route_not_found_error(url: str) -> NotFoundError:
    """A 404 for a path the server does not serve: no model is named anywhere."""
    request = MagicMock()
    request.url = url
    return NotFoundError(
        "Error code: 404 - Not Found",
        response=MagicMock(status_code=404, headers={}, request=request),
        body={"detail": "Not Found"},
    )


class TestOpenAICompatibleBaseUrl:
    """A base URL without ``/v1`` resolves the way the model listing resolves it."""

    def setup_method(self) -> None:
        self.config = LLMConfig(model="deepseek-v4.1-flash-free")

    @patch("storico.infrastructure.llm.openai_adapter.AsyncOpenAI")
    @pytest.mark.asyncio
    async def test_a_route_404_retries_once_under_v1_and_keeps_that_base(
        self, mock_client_cls: MagicMock
    ) -> None:
        bare = MagicMock()
        bare.chat.completions.create = AsyncMock(
            side_effect=_route_not_found_error("https://direct.example.io/chat/completions")
        )
        versioned = MagicMock()
        versioned.chat.completions.create = AsyncMock(return_value=_mock_response("1. summary: A"))
        mock_client_cls.side_effect = [bare, versioned]

        adapter = OpenAIAdapter(api_key="k", base_url="https://direct.example.io/")
        first = await adapter.generate("p", self.config)
        second = await adapter.generate("p", self.config)

        assert first.text == "1. summary: A"
        assert second.text == "1. summary: A"
        assert mock_client_cls.call_args_list[1].kwargs == {
            "api_key": "k",
            "base_url": "https://direct.example.io/v1",
        }
        # The bare base was tried once; every later call goes straight to /v1.
        assert bare.chat.completions.create.await_count == 1
        assert versioned.chat.completions.create.await_count == 2

    @patch("storico.infrastructure.llm.openai_adapter.AsyncOpenAI")
    @pytest.mark.asyncio
    async def test_a_route_404_on_both_bases_names_the_endpoint_not_the_model(
        self, mock_client_cls: MagicMock
    ) -> None:
        bare = MagicMock()
        bare.chat.completions.create = AsyncMock(
            side_effect=_route_not_found_error("https://gw.example.io/chat/completions")
        )
        versioned = MagicMock()
        versioned.chat.completions.create = AsyncMock(
            side_effect=_route_not_found_error("https://gw.example.io/v1/chat/completions")
        )
        mock_client_cls.side_effect = [bare, versioned]

        adapter = OpenAIAdapter(api_key="k", base_url="https://gw.example.io")
        with pytest.raises(LLMConnectionError) as exc_info:
            await adapter.generate("p", self.config)

        message = str(exc_info.value)
        assert "https://gw.example.io/v1/chat/completions" in message
        assert "Base URL" in message
        assert "deepseek-v4.1-flash-free" not in message

    @patch("storico.infrastructure.llm.openai_adapter.AsyncOpenAI")
    @pytest.mark.asyncio
    async def test_a_model_404_still_reports_the_model(self, mock_client_cls: MagicMock) -> None:
        bare = MagicMock()
        bare.chat.completions.create = AsyncMock(
            side_effect=_not_found_error("The model `deepseek-v4.1-flash-free` does not exist")
        )
        versioned = MagicMock()
        versioned.chat.completions.create = AsyncMock(
            side_effect=_not_found_error("The model `deepseek-v4.1-flash-free` does not exist")
        )
        mock_client_cls.side_effect = [bare, versioned]

        adapter = OpenAIAdapter(api_key="k", base_url="https://gw.example.io")
        with pytest.raises(LLMModelNotFoundError) as exc_info:
            await adapter.generate("p", self.config)
        assert exc_info.value.model == "deepseek-v4.1-flash-free"

    @patch("storico.infrastructure.llm.openai_adapter.AsyncOpenAI")
    @pytest.mark.asyncio
    async def test_a_base_that_already_ends_in_v1_is_not_retried(
        self, mock_client_cls: MagicMock
    ) -> None:
        mock_client_cls.return_value.chat.completions.create = AsyncMock(
            side_effect=_route_not_found_error("https://gw.example.io/v1/chat/completions")
        )

        adapter = OpenAIAdapter(api_key="k", base_url="https://gw.example.io/v1")
        with pytest.raises(LLMConnectionError):
            await adapter.generate("p", self.config)
        assert mock_client_cls.call_count == 1

    @patch("storico.infrastructure.llm.openai_adapter.AsyncOpenAI")
    @pytest.mark.asyncio
    async def test_openai_without_a_base_url_is_not_retried(
        self, mock_client_cls: MagicMock
    ) -> None:
        mock_client_cls.return_value.chat.completions.create = AsyncMock(
            side_effect=_not_found_error("gpt-x")
        )

        adapter = OpenAIAdapter(api_key="k")
        with pytest.raises(LLMModelNotFoundError):
            await adapter.generate("p", LLMConfig(model="gpt-x"))
        assert mock_client_cls.call_count == 1

    @patch("storico.infrastructure.llm.openai_adapter.AsyncOpenAI")
    @pytest.mark.asyncio
    async def test_a_failing_v1_retry_is_wrapped_like_any_other_call(
        self, mock_client_cls: MagicMock
    ) -> None:
        bare = MagicMock()
        bare.chat.completions.create = AsyncMock(
            side_effect=_route_not_found_error("https://gw.example.io/chat/completions")
        )
        versioned = MagicMock()
        versioned.chat.completions.create = AsyncMock(side_effect=OpenAIError("boom"))
        mock_client_cls.side_effect = [bare, versioned]

        adapter = OpenAIAdapter(api_key="k", base_url="https://gw.example.io")
        with pytest.raises(LLMResponseError):
            await adapter.generate("p", self.config)


# ── Truncation with non-empty content (S4, extraction-truncation) ──


class TestTruncationDetection:
    """A non-empty answer cut by the output budget is a classified failure.

    The empty-content path already inspected ``finish_reason``; the hole was the
    answer the budget cut *after* it had written something: three of six tasks
    came back as a ``completed`` run. The installed SDK types the signal as
    ``Choice.finish_reason: Literal["stop", "length", "tool_calls",
    "content_filter", "function_call"]`` (``openai/types/chat/chat_completion.py``),
    so ``length`` with content in hand is the observable truncation report.
    """

    def setup_method(self) -> None:
        self.config = LLMConfig(model="gpt-3.5-turbo", max_tokens=2048)

    @patch("storico.infrastructure.llm.openai_adapter.AsyncOpenAI")
    @pytest.mark.asyncio
    async def test_a_truncated_answer_with_content_is_a_failure_not_a_partial_result(
        self, mock_client_cls: MagicMock
    ) -> None:
        """``finish_reason: length`` with content raises; it is never a partial result."""
        mock_client_cls.return_value.chat.completions.create = AsyncMock(
            return_value=_mock_response(
                "1. summary: Task one\ndescription: Do it",
                finish_reason="length",
            )
        )

        adapter = OpenAIAdapter(api_key="test-key")
        with pytest.raises(LLMResponseError) as exc_info:
            await adapter.generate("Test prompt", self.config)

        message = str(exc_info.value)
        assert "length" in message
        assert "max_tokens: 2048" in message
        assert "max tokens" in message.lower()

    @patch("storico.infrastructure.llm.openai_adapter.AsyncOpenAI")
    @pytest.mark.asyncio
    async def test_a_stop_finish_reason_with_content_still_returns_the_answer(
        self, mock_client_cls: MagicMock
    ) -> None:
        """A legitimately finished answer keeps flowing through unchanged."""
        mock_client_cls.return_value.chat.completions.create = AsyncMock(
            return_value=_mock_response(
                "1. summary: Task one\ndescription: Do it",
                finish_reason="stop",
            )
        )

        adapter = OpenAIAdapter(api_key="test-key")
        result = await adapter.generate("Test prompt", self.config)

        assert "Task one" in result.text
