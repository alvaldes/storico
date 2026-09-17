"""Model-discovery tests for the workspace settings LLM endpoint.

Covers the OpenAI-compatible prober that backs custom providers (``deepseek``,
``groq``, self-hosted gateways) plus the endpoint branch that routes unknown
providers through it. The prober is exercised with an injected
``httpx.MockTransport`` client so no test touches the network.
"""

from __future__ import annotations

from collections.abc import Callable

import httpx
import jwt as pyjwt
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from storico.api.routes import workspace_settings
from storico.api.routes.workspace_settings import (
    fetch_openai_compatible_models,
    fetch_openai_models,
)
from storico.config.settings import Settings
from storico.domain.entities.user import User
from storico.domain.entities.workspace_llm_config import WorkspaceLLMConfig
from storico.infrastructure.database.repositories import (
    SQLAlchemyUserRepository,
    SQLAlchemyWorkspaceLLMConfigRepository,
)


def _auth_headers(user_id: str) -> dict:
    """Generate JWT auth headers."""
    secret = Settings.load().auth_jwt_secret
    token = pyjwt.encode({"sub": user_id}, secret, algorithm="HS256")
    return {"Authorization": f"Bearer {token}"}


async def _create_user(db_session: AsyncSession, email: str = "models@test.com") -> User:
    """Create a user in the test database."""
    repo = SQLAlchemyUserRepository(db_session)
    user = User(email=email, name="Models Test")
    saved = await repo.save(user)
    await repo.link_account(saved.id, "google", f"g-{email}")
    return saved


def _stub_client(handler: Callable[[httpx.Request], httpx.Response]) -> httpx.AsyncClient:
    """Return a prober client whose transport answers with ``handler``."""
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def _patch_client_factory(
    monkeypatch: pytest.MonkeyPatch,
    handler: Callable[[httpx.Request], httpx.Response],
) -> None:
    """Route the prober's self-created client through ``handler``.

    ``fetch_openai_compatible_models`` owns its client when none is injected,
    so intercepting the module-level factory is the only way to observe the
    URL a caller with no injection point actually requests.
    """
    real_client = httpx.AsyncClient
    monkeypatch.setattr(
        workspace_settings.httpx,
        "AsyncClient",
        lambda *args, **kwargs: real_client(transport=httpx.MockTransport(handler)),
    )


@pytest.mark.unit
class TestOpenAICompatibleProber:
    """``fetch_openai_compatible_models`` probes candidate URLs in order."""

    @pytest.mark.asyncio
    async def test_plain_base_probes_models_first(self) -> None:
        """``https://api.deepseek.com`` answers on its first candidate."""
        requested: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requested.append(str(request.url))
            return httpx.Response(200, json={"data": [{"id": "deepseek-chat"}]})

        async with _stub_client(handler) as client:
            models = await fetch_openai_compatible_models(
                "https://api.deepseek.com", "k", client=client
            )

        assert requested == ["https://api.deepseek.com/models"]
        assert [m.id for m in models] == ["deepseek-chat"]

    @pytest.mark.asyncio
    async def test_v1_base_never_doubles_the_version_segment(self) -> None:
        """A base already ending in ``/v1`` must not probe ``/v1/v1/models``."""
        requested: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requested.append(str(request.url))
            return httpx.Response(200, json={"data": [{"id": "llama-3.3-70b"}]})

        async with _stub_client(handler) as client:
            models = await fetch_openai_compatible_models(
                "https://api.groq.com/openai/v1", "k", client=client
            )

        assert requested == ["https://api.groq.com/openai/v1/models"]
        assert [m.id for m in models] == ["llama-3.3-70b"]

    @pytest.mark.asyncio
    async def test_falls_back_to_v1_suffix_when_bare_base_fails(self) -> None:
        """A 404 on the bare base keeps probing the ``/v1`` spelling."""
        requested: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requested.append(str(request.url))
            if request.url.path == "/openai/models":
                return httpx.Response(404)
            return httpx.Response(200, json={"data": [{"id": "llama-3.3-70b"}]})

        async with _stub_client(handler) as client:
            models = await fetch_openai_compatible_models(
                "https://api.groq.com/openai", "k", client=client
            )

        assert requested == [
            "https://api.groq.com/openai/models",
            "https://api.groq.com/openai/v1/models",
        ]
        assert [m.id for m in models] == ["llama-3.3-70b"]

    @pytest.mark.asyncio
    async def test_omitted_api_key_sends_no_authorization_header(self) -> None:
        """Unauthenticated local servers must answer without a bearer token."""
        seen: list[str | None] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append(request.headers.get("Authorization"))
            return httpx.Response(200, json={"data": [{"id": "local-model"}]})

        async with _stub_client(handler) as client:
            models = await fetch_openai_compatible_models(
                "http://localhost:8000/v1", None, client=client
            )

        assert seen == [None]
        assert [m.id for m in models] == ["local-model"]

    @pytest.mark.asyncio
    async def test_api_key_is_sent_as_bearer(self) -> None:
        """A configured key is forwarded as a bearer token."""
        seen: list[str | None] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append(request.headers.get("Authorization"))
            return httpx.Response(200, json={"data": []})

        async with _stub_client(handler) as client:
            await fetch_openai_compatible_models(
                "https://api.deepseek.com", "secret-key", client=client
            )

        assert seen == ["Bearer secret-key"]

    @pytest.mark.asyncio
    async def test_empty_data_list_is_a_valid_answer(self) -> None:
        """A provider with zero models answers truthfully; it is not a failure."""
        requested: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requested.append(str(request.url))
            return httpx.Response(200, json={"data": []})

        async with _stub_client(handler) as client:
            models = await fetch_openai_compatible_models(
                "https://api.deepseek.com", "k", client=client
            )

        assert models == []
        assert requested == ["https://api.deepseek.com/models"]

    @pytest.mark.asyncio
    async def test_non_data_body_is_not_a_candidate_success(self) -> None:
        """A 200 without a ``data`` list keeps probing the next candidate."""
        requested: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requested.append(str(request.url))
            if request.url.path == "/openai/models":
                return httpx.Response(200, json={"models": [{"id": "wrong"}]})
            return httpx.Response(200, json={"data": [{"id": "right"}]})

        async with _stub_client(handler) as client:
            models = await fetch_openai_compatible_models(
                "https://api.groq.com/openai", None, client=client
            )

        assert len(requested) == 2
        assert [m.id for m in models] == ["right"]

    @pytest.mark.asyncio
    async def test_unparsable_body_keeps_probing(self) -> None:
        """A 200 that is not even JSON must not end the probe as a success."""
        requested: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requested.append(str(request.url))
            if request.url.path == "/openai/models":
                return httpx.Response(200, text="<html>gateway error page</html>")
            return httpx.Response(200, json={"data": [{"id": "llama-3.3-70b"}]})

        async with _stub_client(handler) as client:
            models = await fetch_openai_compatible_models(
                "https://api.groq.com/openai", None, client=client
            )

        assert len(requested) == 2
        assert [m.id for m in models] == ["llama-3.3-70b"]

    @pytest.mark.asyncio
    async def test_entries_without_id_are_skipped(self) -> None:
        """Malformed entries cannot become models; the rest of the list still can."""

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={"data": [{"id": "kept"}, {"name": "no-id"}, "junk"]},
            )

        async with _stub_client(handler) as client:
            models = await fetch_openai_compatible_models(
                "https://api.deepseek.com", None, client=client
            )

        assert [m.id for m in models] == ["kept"]

    @pytest.mark.asyncio
    async def test_trailing_slash_on_base_url_is_normalized(self) -> None:
        """A pasted trailing slash must not produce a doubled path separator."""
        requested: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requested.append(str(request.url))
            return httpx.Response(200, json={"data": []})

        async with _stub_client(handler) as client:
            await fetch_openai_compatible_models("https://api.deepseek.com/", None, client=client)

        assert requested == ["https://api.deepseek.com/models"]

    @pytest.mark.asyncio
    async def test_bodies_without_data_list_raise_http_error(self) -> None:
        """With no transport error to re-raise, the probe still fails as HTTPError."""
        with pytest.raises(httpx.HTTPError):
            async with _stub_client(
                lambda request: httpx.Response(200, json={"models": []})
            ) as client:
                await fetch_openai_compatible_models(
                    "https://api.deepseek.com", None, client=client
                )

    @pytest.mark.asyncio
    async def test_all_candidates_failing_raises_http_error(self) -> None:
        """Every candidate failing surfaces the transport error to the caller."""
        with pytest.raises(httpx.HTTPError):
            async with _stub_client(lambda request: httpx.Response(503)) as client:
                await fetch_openai_compatible_models("https://api.deepseek.com", "k", client=client)

    @pytest.mark.asyncio
    async def test_injected_client_is_left_open(self) -> None:
        """The caller owns an injected client and must be able to reuse it."""
        async with _stub_client(
            lambda request: httpx.Response(200, json={"data": [{"id": "m"}]})
        ) as client:
            await fetch_openai_compatible_models("https://api.deepseek.com", "k", client=client)
            assert not client.is_closed

    @pytest.mark.asyncio
    async def test_openai_helper_requests_the_openai_base(self, monkeypatch) -> None:
        """``fetch_openai_models`` without a base URL targets OpenAI itself."""
        requested: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requested.append(str(request.url))
            return httpx.Response(200, json={"data": [{"id": "gpt-4o-mini"}]})

        _patch_client_factory(monkeypatch, handler)

        models = await fetch_openai_models("k", None)

        assert requested == ["https://api.openai.com/v1/models"]
        assert [m.id for m in models] == ["gpt-4o-mini"]


@pytest.mark.integration
class TestCustomProviderModelDiscovery:
    """Custom providers reach the prober through the settings endpoint."""

    @pytest.mark.asyncio
    async def test_custom_provider_without_base_url_returns_empty(
        self, async_client, db_session, seed_workspace, monkeypatch
    ) -> None:
        """Without a base URL there is nothing to probe, so no request is made."""

        def handler(request: httpx.Request) -> httpx.Response:
            raise AssertionError(f"unexpected request to {request.url}")

        _patch_client_factory(monkeypatch, handler)

        user = await _create_user(db_session)
        ws_id = (await seed_workspace(user=user, stories=0)).workspace_id
        await SQLAlchemyWorkspaceLLMConfigRepository(db_session).upsert(
            WorkspaceLLMConfig(workspace_id=ws_id, provider="deepseek", api_key="secret")
        )

        response = await async_client.get(
            f"/api/v1/workspaces/{ws_id}/settings/llm/models",
            headers=_auth_headers(str(user.id)),
        )

        assert response.status_code == 200
        assert response.json() == []

    @pytest.mark.asyncio
    async def test_custom_provider_with_base_url_is_probed(
        self, async_client, db_session, seed_workspace, monkeypatch
    ) -> None:
        """The configured base URL and key reach the probe unchanged."""
        requested: list[tuple[str, str | None]] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requested.append((str(request.url), request.headers.get("Authorization")))
            return httpx.Response(200, json={"data": [{"id": "deepseek-chat"}]})

        _patch_client_factory(monkeypatch, handler)

        user = await _create_user(db_session)
        ws_id = (await seed_workspace(user=user, stories=0)).workspace_id
        await SQLAlchemyWorkspaceLLMConfigRepository(db_session).upsert(
            WorkspaceLLMConfig(
                workspace_id=ws_id,
                provider="deepseek",
                base_url="https://api.deepseek.com",
                api_key="secret",
            )
        )

        response = await async_client.get(
            f"/api/v1/workspaces/{ws_id}/settings/llm/models",
            headers=_auth_headers(str(user.id)),
        )

        assert response.status_code == 200
        assert requested == [("https://api.deepseek.com/models", "Bearer secret")]
        assert response.json() == [{"id": "deepseek-chat", "name": "deepseek-chat"}]
