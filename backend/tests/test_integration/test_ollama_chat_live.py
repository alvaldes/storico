"""Live integration test for the Ollama chat path — the extraction transport itself.

This is the runtime evidence the Qdrant + few-shot verification case is blocked
on. ``docs``/``odd/tasks/qdrant-few-shot-verification.md`` records that *every*
real extraction row in the database is ``gemini-2.5-flash``: the local Ollama
path is the one the few-shot feature is supposed to be verified through, and the
end-to-end check cannot even reach the extraction step.

The reason is a wire contract, and no mocked test can see it. ``OllamaAdapter``
POSTs to ``{base_url}/api/chat`` with a payload that never mentions ``stream``,
and Ollama's ``/api/chat`` **defaults to streaming NDJSON**. The real response is
several JSON objects, one per line; ``response.json()`` then raises
``json.JSONDecodeError: Extra data: line 2 column 1``. A mocked transport returns
whatever dict the test author wrote, so it stays green against a body the real
server never sends for this payload. Only a real server can contradict that.

Gate
----
The tests are opt-in and never probe reachability:

    cd backend && STORICO_TEST_LIVE_OLLAMA=1 .venv/bin/pytest \\
        tests/test_integration/test_ollama_chat_live.py -v

Without ``STORICO_TEST_LIVE_OLLAMA=1`` every test skips. Once an operator sets
the flag, an unreachable Ollama or an absent model **fails** the run instead of
skipping. That asymmetry is the point: a reachability probe in the skip
condition would let a skipped-on-absence test masquerade as a pass, and the
defect this module exists to catch is exactly a silent "the model path is fine"
conclusion drawn without ever calling the model. An explicit opt-in means the
human asserts the service is up; a skip then means "not opted in", never
"opted in but the service was down".

Model choice
------------
``llama3.1:8b`` is the model the adapter is configured with in this environment
and the one present locally, so no pull is needed for the opt-in run.
"""

from __future__ import annotations

import os
from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio

from storico.config.settings import Settings
from storico.domain.ports import LLMConfig
from storico.infrastructure.llm.ollama_adapter import OllamaAdapter

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.environ.get("STORICO_TEST_LIVE_OLLAMA") != "1",
        reason=(
            "Live Ollama chat integration is opt-in: set STORICO_TEST_LIVE_OLLAMA=1 to run it. "
            "With the flag set, an unreachable service fails the run instead of skipping."
        ),
    ),
]

MODEL = "llama3.1:8b"
# Short and deterministic on purpose: the assertion is about the transport
# parsing a real body, not about response quality, so the prompt asks for one
# word and ``num_predict`` caps the generation at a handful of tokens.
PROMPT = "Reply with the single word: ok"
SYSTEM_PROMPT = "You are a test."


@pytest.fixture
def settings() -> Settings:
    """The real application settings (environment + ``.env``), never hardcoded."""
    return Settings.load()


@pytest_asyncio.fixture
async def adapter(settings: Settings) -> AsyncGenerator[OllamaAdapter, None]:
    """A real adapter against the configured host, closed on teardown.

    The adapter lazily creates its own pooled ``httpx.AsyncClient`` and exposes
    no ``close()``, so a per-test fixture must release it explicitly.
    """
    live_adapter = OllamaAdapter(base_url=settings.ollama_host)
    try:
        yield live_adapter
    finally:
        await live_adapter._client.aclose()


def _config() -> LLMConfig:
    """The generation config: real model, low temperature, tiny completion."""
    return LLMConfig(model=MODEL, temperature=0.1, max_tokens=16, timeout=120)


class TestLiveChatTransport:
    """The transport contract against a real Ollama server."""

    @pytest.mark.asyncio
    async def test_generate_parses_a_real_chat_response(self, adapter: OllamaAdapter) -> None:
        """A real ``/api/chat`` body is parsed into a non-empty string.

        Before the fix this raises ``json.JSONDecodeError: Extra data: line 2
        column 1``, because the server answers with NDJSON while
        ``response.json()`` expects exactly one JSON document. There is no mock
        of ``httpx`` anywhere in this module — the failure and the pass both come
        from the real server.
        """
        result = await adapter.generate(PROMPT, _config(), system_prompt=SYSTEM_PROMPT)

        assert isinstance(result, str), f"expected a str, got {type(result).__name__}"
        assert result.strip() != "", "the model answered but the parsed content is empty"

    def test_the_adapter_really_sends_the_non_streaming_flag(self, settings: Settings) -> None:
        """Wire-contract assertion: the request payload opts out of streaming.

        This is a **wire-contract assertion built from the adapter's own payload
        builder**, not live proof — ``_build_payload`` is called directly here,
        and sending the request twice through ``generate`` would not expose the
        flag. The live proof is
        ``test_generate_parses_a_real_chat_response`` above: a real server only
        answers one JSON object for this request when ``stream`` is ``False``.

        The check exists separately because a mocked transport accepts the
        payload without ever validating it, so the fast unit suite needs a pin on
        the exact key that decides the response shape.
        """
        adapter = OllamaAdapter(base_url=settings.ollama_host)

        payload = adapter._build_payload(PROMPT, _config(), system_prompt=SYSTEM_PROMPT)

        assert payload["stream"] is False
