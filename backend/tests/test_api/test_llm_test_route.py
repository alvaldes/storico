"""Tests for the LLM connection probe — workspace-scoped, admin-gated.

The probe lives at ``POST /api/v1/workspaces/{workspace_id}/settings/llm/test``, inside the
workspace settings router, and resolves the workspace from the path with the same
``require_admin`` gate every other write route in that module uses. A caller therefore has to
be an admin of the workspace named in the path before the body's endpoint and credential
reach any adapter; a member, a non-member and an anonymous caller are refused before anything
is built.

The probe still takes the endpoint and the credential straight from the request body — that is
what a probe of not-yet-saved values is — so a blank value there has to mean "absent" exactly
as it does for a stored one, which is why the route normalizes before it builds anything.
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import uuid4

import pytest
from httpx import AsyncClient

from storico.config.settings import Settings
from storico.domain.entities.workspace_member import WorkspaceRole
from storico.domain.ports.llm_port import LLMResponse
from storico.infrastructure import llm as llm_module

URL_TEMPLATE = "/api/v1/workspaces/{workspace_id}/settings/llm/test"


def _url(workspace_id: Any) -> str:
    return URL_TEMPLATE.format(workspace_id=workspace_id)


@pytest.fixture
async def admin_ws_url(seed_workspace) -> str:
    """A workspace the ``authed_client`` caller administers, and the probe's URL in it."""
    seeded = await seed_workspace(stories=0)
    return _url(seeded.workspace_id)


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

        async def generate(self, prompt: str, config: Any) -> LLMResponse:  # noqa: ARG002
            return LLMResponse(text="stub response")

    for name in ("OllamaAdapter", "OpenAIAdapter", "AnthropicAdapter", "GeminiAdapter"):
        monkeypatch.setattr(llm_module, name, Recording)
    return built


async def _post(client: AsyncClient, payload: dict[str, Any], url: str):
    """Send a connection test."""
    return await client.post(url, json=payload)


@pytest.fixture
def failing_adapter_kwargs(
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[list[dict[str, Any]], list[Exception]]:
    """Replace every adapter the route can build with one whose ``generate`` raises.

    A sibling of ``adapter_kwargs``: same patch points, same recording of constructor
    kwargs, but ``generate`` raises the exception the test queued instead of answering.
    The exception is queued (not passed as a fixture argument) so one fixture serves both
    classifications — with and without a response attached.
    """
    built: list[dict[str, Any]] = []
    queued: list[Exception] = []

    class Failing:
        def __init__(self, **kwargs: Any) -> None:
            built.append(kwargs)

        async def generate(self, prompt: str, config: Any) -> LLMResponse:  # noqa: ARG002
            raise queued[0]

    for name in ("OllamaAdapter", "OpenAIAdapter", "AnthropicAdapter", "GeminiAdapter"):
        monkeypatch.setattr(llm_module, name, Failing)
    return built, queued


class _ResponseWithStatus:
    """The slice of an ``httpx.Response`` the route's classification reads."""

    def __init__(self, status_code: int) -> None:
        self.status_code = status_code


class TestAuthorization:
    """The probe is workspace-scoped and admin-gated, like its sibling routes.

    The path names the workspace and ``require_admin`` checks membership and role before the
    handler runs, so the body's endpoint and credential only reach an adapter for an admin of
    that workspace.
    """

    @pytest.mark.asyncio
    async def test_a_request_without_a_session_is_refused(
        self, async_client: AsyncClient, admin_ws_url: str, adapter_kwargs: list[dict[str, Any]]
    ) -> None:
        """No Authorization header, no probe: 401 before the workspace is even resolved."""
        response = await _post(
            async_client, {"provider": "ollama", "model": "llama3.2"}, admin_ws_url
        )

        assert response.status_code == 401
        assert adapter_kwargs == []

    @pytest.mark.asyncio
    async def test_a_member_who_is_not_an_admin_is_refused(
        self, seed_workspace, authed_client: AsyncClient, adapter_kwargs: list[dict[str, Any]]
    ) -> None:
        """A member can read the status route but cannot fire the probe."""
        seeded = await seed_workspace(stories=0, role=WorkspaceRole.MEMBER)

        response = await _post(
            authed_client,
            {"provider": "ollama", "model": "llama3.2"},
            _url(seeded.workspace_id),
        )

        assert response.status_code == 403
        assert response.json()["error_code"] == "ADMIN_ACCESS_REQUIRED"
        assert adapter_kwargs == []

    @pytest.mark.asyncio
    async def test_a_non_member_is_refused(
        self, seed_workspace, authed_client: AsyncClient, adapter_kwargs: list[dict[str, Any]]
    ) -> None:
        """A workspace the caller does not belong to refuses the probe with 403."""
        seeded = await seed_workspace(stories=0, member=False)

        response = await _post(
            authed_client,
            {"provider": "ollama", "model": "llama3.2"},
            _url(seeded.workspace_id),
        )

        assert response.status_code == 403
        assert response.json()["error_code"] == "NOT_A_WORKSPACE_MEMBER"
        assert adapter_kwargs == []

    @pytest.mark.asyncio
    async def test_an_unknown_workspace_is_refused(
        self, authed_client: AsyncClient, adapter_kwargs: list[dict[str, Any]]
    ) -> None:
        """A workspace id that does not exist answers 404, not 403."""
        response = await _post(
            authed_client,
            {"provider": "ollama", "model": "llama3.2"},
            _url(uuid4()),
        )

        assert response.status_code == 404
        assert response.json()["error_code"] == "WORKSPACE_NOT_FOUND"
        assert adapter_kwargs == []


class TestBlankCredential:
    """A credential made of whitespace is a missing credential."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("provider", ["openai", "anthropic", "gemini"])
    async def test_it_is_refused_before_any_adapter_is_built(
        self,
        authed_client: AsyncClient,
        admin_ws_url: str,
        adapter_kwargs: list[dict[str, Any]],
        provider: str,
    ) -> None:
        """It used to build an adapter with a blank key and spend a call failing."""
        response = await _post(
            authed_client,
            {"provider": provider, "model": "some-model", "api_key": "   "},
            admin_ws_url,
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
        self, authed_client: AsyncClient, admin_ws_url: str, adapter_kwargs: list[dict[str, Any]]
    ) -> None:
        """The host default, never a URL made of spaces."""
        response = await _post(
            authed_client,
            {"provider": "ollama", "model": "llama3.2", "base_url": "   "},
            admin_ws_url,
        )

        assert response.status_code == 200
        assert adapter_kwargs == [{"base_url": Settings.load().ollama_host}]

    @pytest.mark.asyncio
    async def test_a_cloud_adapter_is_built_without_an_endpoint(
        self, authed_client: AsyncClient, admin_ws_url: str, adapter_kwargs: list[dict[str, Any]]
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
            admin_ws_url,
        )

        assert response.status_code == 200
        assert adapter_kwargs == [{"api_key": "sk-real", "base_url": None}]


class TestRealValues:
    """Normalizing is not a filter for values that mean something."""

    @pytest.mark.asyncio
    async def test_a_padded_endpoint_reaches_the_adapter_trimmed(
        self, authed_client: AsyncClient, admin_ws_url: str, adapter_kwargs: list[dict[str, Any]]
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
            admin_ws_url,
        )

        assert response.status_code == 200
        assert adapter_kwargs == [{"api_key": "sk-real", "base_url": "https://gateway.internal/v1"}]

    @pytest.mark.asyncio
    async def test_a_credential_with_internal_spaces_is_kept(
        self, authed_client: AsyncClient, admin_ws_url: str, adapter_kwargs: list[dict[str, Any]]
    ) -> None:
        """Only the surrounding whitespace is a paste artifact, not what is inside."""
        response = await _post(
            authed_client,
            {
                "provider": "anthropic",
                "model": "claude-3-haiku",
                "api_key": "  sk-ant-a b c  ",
            },
            admin_ws_url,
        )

        assert response.status_code == 200
        assert adapter_kwargs == [{"api_key": "sk-ant-a b c", "base_url": None}]


class TestCustomProviders:
    """A name outside the four built-ins is a workspace-registered OpenAI-compatible endpoint.

    ``_build_llm_port`` already routes every such name to ``OpenAIAdapter``. This endpoint used
    to answer ``422`` from its own ``Literal`` of the four built-in names, which is why the
    branch that named the provider here was unreachable and why a custom provider could not be
    tested at all.
    """

    @pytest.mark.asyncio
    async def test_it_reaches_the_openai_compatible_adapter_with_the_placeholder(
        self, authed_client: AsyncClient, admin_ws_url: str, adapter_kwargs: list[dict[str, Any]]
    ) -> None:
        """A gateway that needs no credential stays reachable without one, as in extraction."""
        response = await _post(
            authed_client,
            {
                "provider": "deepseek",
                "model": "deepseek-chat",
                "base_url": "https://api.deepseek.com/v1",
            },
            admin_ws_url,
        )

        assert response.status_code == 200
        assert response.json()["success"] is True
        assert adapter_kwargs == [
            {
                "api_key": llm_module.CUSTOM_PROVIDER_PLACEHOLDER_KEY,
                "base_url": "https://api.deepseek.com/v1",
            }
        ]

    @pytest.mark.asyncio
    async def test_a_custom_provider_without_an_endpoint_is_refused(
        self, authed_client: AsyncClient, admin_ws_url: str, adapter_kwargs: list[dict[str, Any]]
    ) -> None:
        """No endpoint means nothing to call: extraction's rule, answered as a refused test."""
        response = await _post(
            authed_client,
            {"provider": "deepseek", "model": "deepseek-chat"},
            admin_ws_url,
        )

        assert response.status_code == 200
        body = response.json()
        assert body["success"] is False
        assert "deepseek" in body["message"]
        assert "Base URL is required" in body["message"]
        assert adapter_kwargs == []

    @pytest.mark.asyncio
    async def test_an_explicit_key_replaces_the_placeholder(
        self, authed_client: AsyncClient, admin_ws_url: str, adapter_kwargs: list[dict[str, Any]]
    ) -> None:
        """The placeholder is a fallback: a supplied credential is the one that goes through."""
        response = await _post(
            authed_client,
            {
                "provider": "deepseek",
                "model": "deepseek-chat",
                "base_url": "https://api.deepseek.com/v1",
                "api_key": "deepseek-key",
            },
            admin_ws_url,
        )

        assert response.status_code == 200
        assert adapter_kwargs == [
            {"api_key": "deepseek-key", "base_url": "https://api.deepseek.com/v1"}
        ]


class TestTheProviderNameItself:
    """The name is validated with the registry's rule, not a second one.

    Widening the field from a ``Literal`` to a bounded ``str`` removed the refusal that used
    to happen by accident: a ``Literal`` rejected ``" "`` for the same reason it rejected every
    other unknown name, and widening it would have let a whitespace-only provider through to an
    adapter while the registry that stores custom providers refuses that same name. The rule is
    imported rather than re-derived so the two surfaces cannot disagree.
    """

    @pytest.mark.asyncio
    @pytest.mark.parametrize("name", ["", " ", "   ", "x" * 51])
    async def test_a_name_the_registry_would_refuse_is_refused_here(
        self,
        authed_client: AsyncClient,
        admin_ws_url: str,
        adapter_kwargs: list[dict[str, Any]],
        name: str,
    ) -> None:
        response = await _post(
            authed_client,
            {"provider": name, "base_url": "https://x.test/v1"},
            admin_ws_url,
        )

        assert response.status_code == 422
        assert adapter_kwargs == []

    @pytest.mark.asyncio
    async def test_a_padded_name_is_trimmed_before_it_is_used(
        self, authed_client: AsyncClient, admin_ws_url: str, adapter_kwargs: list[dict[str, Any]]
    ) -> None:
        """The registry trims before it measures, so a padded name that fits must be accepted."""
        response = await _post(
            authed_client,
            {"provider": "  deepseek  ", "base_url": "https://api.deepseek.com/v1"},
            admin_ws_url,
        )

        assert response.status_code == 200
        assert response.json()["success"] is True
        assert len(adapter_kwargs) == 1
        # The name the user sees is the trimmed one, and the padding never reached the adapter.
        assert "deepseek responded" in response.json()["message"]
        assert "  deepseek  " not in response.json()["message"]


# A marker that, if it were real, is a credential or an internal URL: the shape of what an
# httpx error embeds (the request URL) and what one provider used to put inside it (the key).
MARKER = "https://internal.test/v1?key=LEAKMARKER"


def _leaking_error(with_response: bool) -> Exception:
    """The failure the adapter raises: a dependency message carrying the leak-shaped marker."""
    error = RuntimeError(f"boom {MARKER}")
    if with_response:
        error.response = _ResponseWithStatus(502)  # type: ignore[attr-defined]
    return error


class TestTransportFailureMessages:
    """A failed probe answers with a reason this application owns, not the exception's text.

    The failure branches used to interpolate ``{e}`` into the response. An ``httpx`` error's
    text embeds the request URL, and one provider historically put the API key inside that
    URL, so the echo handed whatever the dependency knew straight back to the caller. The
    classified reason (``HTTP {status}`` when the exception carries a response, otherwise
    "the provider could not be reached") replaces it, and the full text goes to the log
    instead. Parametrized across all five branches because a branch left unsanitized is
    exactly the failure mode a single-provider test misses.
    """

    @pytest.mark.parametrize(
        ("payload", "provider"),
        [
            ({"provider": "ollama", "model": "llama3.2"}, "ollama"),
            ({"provider": "gemini", "model": "gemini-1.5-flash", "api_key": "g-key"}, "gemini"),
            ({"provider": "openai", "model": "gpt-4o-mini", "api_key": "sk-real"}, "openai"),
            (
                {"provider": "anthropic", "model": "claude-3-haiku", "api_key": "sk-ant"},
                "anthropic",
            ),
            (
                {
                    "provider": "deepseek",
                    "model": "deepseek-chat",
                    "base_url": "https://api.deepseek.com/v1",
                },
                "deepseek",
            ),
        ],
        ids=["ollama", "gemini", "openai", "anthropic", "custom"],
    )
    @pytest.mark.parametrize(
        ("with_response", "expected_reason"),
        [
            (True, "HTTP 502"),
            (False, "the provider could not be reached"),
        ],
        ids=["with-http-status", "without-response"],
    )
    @pytest.mark.asyncio
    async def test_a_failed_probe_never_echoes_the_exception_text(
        self,
        authed_client: AsyncClient,
        admin_ws_url: str,
        failing_adapter_kwargs: tuple[list[dict[str, Any]], list[Exception]],
        caplog: pytest.LogCaptureFixture,
        payload: dict[str, Any],
        provider: str,
        with_response: bool,
        expected_reason: str,
    ) -> None:
        """The marker stays out of the body, the classified reason stays in, and the
        exception text — marker included — reaches the log at warning level."""
        _, queued = failing_adapter_kwargs
        queued.append(_leaking_error(with_response))
        caplog.set_level(logging.WARNING, logger="storico.api.routes.workspace_settings")

        response = await _post(authed_client, payload, admin_ws_url)

        assert response.status_code == 200
        body = response.json()
        assert body["success"] is False
        message = body["message"]
        assert MARKER not in message
        # The built-in prefixes capitalize the provider ("OpenAI connection failed: ");
        # the custom branch uses the name as registered. Compare case-insensitively.
        assert message.lower().startswith(f"{provider} connection failed: ")
        assert expected_reason in message
        assert MARKER in caplog.text
        assert any(
            record.levelno == logging.WARNING and MARKER in record.getMessage()
            for record in caplog.records
        )
