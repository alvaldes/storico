"""Model-discovery tests for the workspace settings LLM endpoint.

Covers the OpenAI-compatible prober that backs custom providers (``deepseek``,
``groq``, self-hosted gateways) plus the endpoint branch that routes unknown
providers through it. The prober is exercised with an injected
``httpx.MockTransport`` client so no test touches the network.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterator
from uuid import uuid4

import httpx
import jwt as pyjwt
import pytest
from cryptography.fernet import Fernet
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from storico.api.routes import workspace_settings
from storico.api.routes.workspace_settings import (
    _resolve_probe,
    fetch_openai_compatible_models,
    fetch_openai_models,
)
from storico.api.schemas.workspace_llm_config import LLMModelProbeRequest
from storico.config.settings import Settings, _reset_settings_cache
from storico.domain.entities.user import User
from storico.domain.entities.workspace_llm_config import WorkspaceLLMConfig
from storico.infrastructure.crypto import FernetCipher
from storico.infrastructure.database.repositories import (
    SQLAlchemyUserRepository,
    SQLAlchemyWorkspaceLLMConfigRepository,
)

_MASTER_KEY = Fernet.generate_key().decode("ascii")


@pytest.fixture(autouse=True)
def _master_key(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Give the app a master key, so a route-level save encrypts like production."""
    monkeypatch.setenv("STORICO_ENCRYPTION_KEY", _MASTER_KEY)
    _reset_settings_cache()
    yield
    _reset_settings_cache()


def _repo(session) -> SQLAlchemyWorkspaceLLMConfigRepository:
    """The repository as the app wires it: a session plus the cipher."""
    return SQLAlchemyWorkspaceLLMConfigRepository(session, FernetCipher(_MASTER_KEY))


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
        await _repo(db_session).upsert(
            WorkspaceLLMConfig(workspace_id=ws_id, provider="deepseek", api_key="secret")
        )

        response = await async_client.post(
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
        await _repo(db_session).upsert(
            WorkspaceLLMConfig(
                workspace_id=ws_id,
                provider="deepseek",
                base_url="https://api.deepseek.com",
                api_key="secret",
            )
        )

        response = await async_client.post(
            f"/api/v1/workspaces/{ws_id}/settings/llm/models",
            headers=_auth_headers(str(user.id)),
        )

        assert response.status_code == 200
        assert requested == [("https://api.deepseek.com/models", "Bearer secret")]
        assert response.json() == [{"id": "deepseek-chat", "name": "deepseek-chat"}]


@pytest.mark.unit
class TestProbeResolution:
    """``_resolve_probe`` decides which provider the list must describe.

    The rule is the whole point of the endpoint's body: a request that names a
    provider describes the probe entirely, and an absent one falls back to the
    saved row so the persisted state stays observable.
    """

    def test_missing_body_falls_back_to_the_saved_row(self) -> None:
        """No body means "describe what is saved"."""
        saved = WorkspaceLLMConfig(
            workspace_id=uuid4(),
            provider="gemini",
            base_url=None,
            api_key="saved-key",
        )

        probe = _resolve_probe(None, saved)

        assert probe is not None
        assert (probe.provider, probe.base_url, probe.api_key) == ("gemini", None, "saved-key")

    def test_missing_body_without_a_saved_row_has_nothing_to_probe(self) -> None:
        """An unconfigured workspace has no provider to ask."""
        assert _resolve_probe(None, None) is None

    def test_body_provider_is_taken_whole(self) -> None:
        """A named provider is described by the body, not by the saved row."""
        probe = _resolve_probe(
            LLMModelProbeRequest(
                provider="deepseek",
                base_url="https://api.deepseek.com",
                api_key="pending-key",
            ),
            WorkspaceLLMConfig(workspace_id=uuid4(), provider="gemini", api_key="saved-key"),
        )

        assert probe is not None
        assert (probe.provider, probe.base_url, probe.api_key) == (
            "deepseek",
            "https://api.deepseek.com",
            "pending-key",
        )

    def test_body_without_a_key_never_borrows_the_saved_one(self) -> None:
        """A key left out is missing for this probe, never the other provider's.

        Borrowing it would send the workspace's Gemini credential to whichever
        endpoint the pending provider names.
        """
        probe = _resolve_probe(
            LLMModelProbeRequest(provider="gemini", base_url=None, api_key=None),
            WorkspaceLLMConfig(
                workspace_id=uuid4(),
                provider="anthropic",
                base_url="https://api.anthropic.com",
                api_key="saved-anthropic-key",
            ),
        )

        assert probe is not None
        assert (probe.provider, probe.base_url, probe.api_key) == ("gemini", None, None)

    def test_empty_body_is_a_saved_row_probe(self) -> None:
        """An empty object carries no selection, so it is not a pending one."""
        probe = _resolve_probe(
            LLMModelProbeRequest(provider=None, base_url=None, api_key=None),
            WorkspaceLLMConfig(workspace_id=uuid4(), provider="ollama"),
        )

        assert probe is not None
        assert probe.provider == "ollama"

    def test_unknown_body_fields_are_rejected(self) -> None:
        """A typo in the payload must fail loudly, not probe the wrong provider."""
        with pytest.raises(ValidationError):
            LLMModelProbeRequest.model_validate({"provider": "gemini", "apiKey": "x"})


@pytest.mark.integration
class TestPendingSelectionProbe:
    """The endpoint probes the selection posted by the client.

    The workspace config is deliberately saved against a *different* provider in
    these cases: the request must win, which is exactly what the reported bug got
    wrong — the select showed one provider and the answer described another.
    """

    @pytest.mark.asyncio
    async def test_pending_provider_overrides_the_saved_row(
        self, async_client, db_session, seed_workspace, monkeypatch
    ) -> None:
        """A posted provider reaches its own endpoint while the saved row is ignored."""
        requested: list[tuple[str, str | None]] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requested.append((str(request.url), request.headers.get("Authorization")))
            return httpx.Response(200, json={"data": [{"id": "deepseek-chat"}]})

        _patch_client_factory(monkeypatch, handler)

        user = await _create_user(db_session)
        ws_id = (await seed_workspace(user=user, stories=0)).workspace_id
        # The saved row points somewhere unreachable; only the posted values may run.
        await _repo(db_session).upsert(
            WorkspaceLLMConfig(
                workspace_id=ws_id,
                provider="NaN",
                base_url="http://localhost:11434",
                api_key="saved-key",
            )
        )

        response = await async_client.post(
            f"/api/v1/workspaces/{ws_id}/settings/llm/models",
            headers=_auth_headers(str(user.id)),
            json={
                "provider": "deepseek",
                "base_url": "https://api.deepseek.com",
                "api_key": "pending-key",
            },
        )

        assert response.status_code == 200
        assert requested == [("https://api.deepseek.com/models", "Bearer pending-key")]

    @pytest.mark.asyncio
    async def test_pending_provider_without_a_key_probes_nothing(
        self, async_client, db_session, seed_workspace, monkeypatch
    ) -> None:
        """A keyless cloud provider has nothing to ask, and borrows no credential."""

        def handler(request: httpx.Request) -> httpx.Response:
            raise AssertionError(f"unexpected request to {request.url}")

        _patch_client_factory(monkeypatch, handler)

        user = await _create_user(db_session)
        ws_id = (await seed_workspace(user=user, stories=0)).workspace_id
        await _repo(db_session).upsert(
            WorkspaceLLMConfig(
                workspace_id=ws_id,
                provider="gemini",
                api_key="saved-gemini-key",
            )
        )

        response = await async_client.post(
            f"/api/v1/workspaces/{ws_id}/settings/llm/models",
            headers=_auth_headers(str(user.id)),
            json={"provider": "anthropic"},
        )

        assert response.status_code == 200
        assert response.json() == []

    @pytest.mark.asyncio
    async def test_pending_custom_provider_without_a_base_url_probes_nothing(
        self, async_client, db_session, seed_workspace, monkeypatch
    ) -> None:
        """An endpoint-less custom name has no host to ask.

        The saved row holds a reachable base URL, so an implementation that fell
        back to it would probe and be caught here.
        """
        requested: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requested.append(str(request.url))
            return httpx.Response(200, json={"data": [{"id": "deepseek-chat"}]})

        _patch_client_factory(monkeypatch, handler)

        user = await _create_user(db_session)
        ws_id = (await seed_workspace(user=user, stories=0)).workspace_id
        await _repo(db_session).upsert(
            WorkspaceLLMConfig(
                workspace_id=ws_id,
                provider="deepseek",
                base_url="https://api.deepseek.com",
                api_key="saved-key",
            )
        )

        response = await async_client.post(
            f"/api/v1/workspaces/{ws_id}/settings/llm/models",
            headers=_auth_headers(str(user.id)),
            json={"provider": "groq"},
        )

        assert response.status_code == 200
        assert response.json() == []
        assert requested == []


class TestBlankEndpointOnTheProbe:
    """A stored blank endpoint probes like an absent one.

    The blank string used to be truthy, so Ollama's branch skipped its own default host
    and httpx raised ``UnsupportedProtocol`` — which the route mapped to a 502 that reads
    as "the provider could not be reached", for what is really an empty stored value.
    """

    @pytest.mark.asyncio
    async def test_a_blank_ollama_endpoint_falls_back_to_the_default_host(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The request goes to Ollama's default, not to a URL made of spaces."""
        requested: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requested.append(str(request.url))
            return httpx.Response(200, json={"models": [{"name": "llama3.2"}]})

        _patch_client_factory(monkeypatch, handler)

        models = await workspace_settings._probe_models(
            workspace_settings._ProbeInputs(provider="ollama", base_url="   ", api_key=None)
        )

        assert requested == ["http://localhost:11434/api/tags"]
        assert [model.id for model in models] == ["llama3.2"]

    @pytest.mark.asyncio
    async def test_a_blank_custom_endpoint_is_not_probed_at_all(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A custom provider with no endpoint has nothing to ask, so nothing is asked."""
        requested: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requested.append(str(request.url))
            return httpx.Response(200, json={"data": []})

        _patch_client_factory(monkeypatch, handler)

        models = await workspace_settings._probe_models(
            workspace_settings._ProbeInputs(provider="deepseek", base_url="  \t ", api_key="k")
        )

        assert models == []
        assert requested == []

    @pytest.mark.asyncio
    async def test_a_blank_cloud_credential_asks_nothing(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A key made of spaces is not a key, so the provider is not called with one."""
        requested: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requested.append(str(request.url))
            return httpx.Response(200, json={"data": []})

        _patch_client_factory(monkeypatch, handler)

        models = await workspace_settings._probe_models(
            workspace_settings._ProbeInputs(provider="openai", base_url=None, api_key="   ")
        )

        assert models == []
        assert requested == []


@pytest.mark.unit
class TestTheProbeDoesNotLeakTheCredential:
    """The credential leaves in a header, and it does not come back in a response.

    Both halves were real. The Gemini fetch put the key in a ``?key=`` query parameter, which
    ``httpx`` logs at INFO for every request and which any transport error embeds into its message;
    and the route interpolated that message verbatim into its 502 body. The credential could be the
    workspace's *stored* one, because the probe falls back to the saved row when the body names no
    provider — so this route could hand a secret back to a caller who never supplied it.
    """

    @pytest.mark.asyncio
    async def test_the_gemini_probe_sends_the_credential_in_a_header(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The URL carries no credential, which is what keeps it out of the logs."""
        credential = "AIza-HEADER-STAND-IN"
        seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append(request)
            return httpx.Response(200, json={"models": []})

        _patch_client_factory(monkeypatch, handler)

        await workspace_settings.fetch_gemini_models(credential)

        assert len(seen) == 1
        assert credential not in str(seen[0].url)
        assert "key=" not in str(seen[0].url)
        assert seen[0].headers["x-goog-api-key"] == credential

    @pytest.mark.asyncio
    async def test_a_failed_probe_publishes_the_status_and_never_the_credential(
        self, async_client, db_session, seed_workspace, monkeypatch
    ) -> None:
        """A 502 may name the provider and the status. It may not carry the credential or the
        dependency's message — and the transport error crafted here is exactly the shape that used
        to do both, with the credential in it on purpose so the assertion has something to catch.
        """
        credential = "AIza-PROBE-SECRET-STAND-IN"
        seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append(request)
            response = httpx.Response(401, request=request)
            raise httpx.HTTPStatusError(
                f"Client error '401 Unauthorized' for url '{request.url}?key={credential}'",
                request=request,
                response=response,
            )

        _patch_client_factory(monkeypatch, handler)

        user = await _create_user(db_session)
        ws_id = (await seed_workspace(user=user, stories=0)).workspace_id
        await _repo(db_session).upsert(
            WorkspaceLLMConfig(
                workspace_id=ws_id,
                provider="gemini",
                model="gemini-2.0-flash",
                api_key=credential,
            )
        )

        response = await async_client.post(
            f"/api/v1/workspaces/{ws_id}/settings/llm/models",
            headers=_auth_headers(str(user.id)),
        )

        assert response.status_code == 502
        body = response.text
        # The credential is nowhere in the answer, not even the part the error handler wrote.
        assert credential not in body
        # And neither is the dependency's own sentence, which is what carried it.
        assert "Client error" not in body
        # What the caller does get: which provider, and how it failed.
        assert "gemini" in body
        assert "401" in body
        # The credential did travel — in the header, on a URL that cannot log it.
        assert len(seen) == 1
        assert credential not in str(seen[0].url)
        assert seen[0].headers["x-goog-api-key"] == credential

    @pytest.mark.asyncio
    async def test_no_fetcher_puts_the_credential_in_a_url(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Class-shaped on purpose: the bug was in one provider, the rule is all of them.

        A test that drove only the Gemini fetcher would have let the same mistake ship again in a
        sibling — which is not hypothetical: a review of the first version of this fix tried exactly
        that and the full suite stayed green. Every fetcher that takes a credential is driven here,
        and the assertion is on the requests they actually make.
        """
        credential = "URL-STAND-IN-CREDENTIAL"
        seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append(request)
            return httpx.Response(200, json={"models": [], "data": []})

        _patch_client_factory(monkeypatch, handler)

        await workspace_settings.fetch_gemini_models(credential)
        await workspace_settings.fetch_anthropic_models(credential)
        await workspace_settings.fetch_openai_models(credential, None)
        await workspace_settings.fetch_openai_compatible_models(
            "https://custom.example", credential
        )

        assert seen, "no fetcher made a request, so this guard would pass without testing anything"
        for request in seen:
            # Not in the URL, which is what the log line below is built from.
            assert credential not in str(request.url), f"{request.url}"
            assert "key=" not in str(request.url), f"{request.url}"
            # And it did travel, in a header — so a fetcher cannot pass this by dropping it. A
            # substring test, because the scheme is part of the value: OpenAI sends
            # ``Bearer <credential>`` and a whole-value comparison would fail on correct behaviour.
            assert any(credential in value for value in request.headers.values()), (
                f"{request.url} carried no credential"
            )

    @pytest.mark.asyncio
    async def test_a_successful_probe_does_not_log_the_credential(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        """The half of the leak no test asserted, on the path where it actually happened.

        Measured, because the intuition is backwards: ``httpx`` writes
        ``HTTP Request: GET <url> "HTTP/1.1 200 OK"`` at INFO for a request that **succeeds**, and
        writes nothing for one that fails to connect. So the URL landed in the log on every
        successful Gemini probe — the ordinary case — which is why this test probes successfully
        rather than failing. The handler below answers, and the assertion is on what got logged.
        """
        credential = "LOG-STAND-IN-CREDENTIAL"
        caplog.set_level(logging.INFO, logger="httpx")

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"models": []})

        _patch_client_factory(monkeypatch, handler)

        await workspace_settings.fetch_gemini_models(credential)

        # The logger really did record the request, so the assertion is about a credential that
        # would otherwise be in there rather than about a logger nobody configured.
        assert "HTTP Request" in caplog.text
        assert credential not in caplog.text
