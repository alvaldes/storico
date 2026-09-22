"""Resolution tests for the workspace LLM config read path.

``resolve_llm_config`` backs both ``GET`` and ``PUT`` on
``/settings/llm``, and the settings form treats its answer as *the workspace's own
values* — it loads them into the fields and posts them back as the pending
selection. So the resolved ``base_url`` has to mean "the endpoint this workspace
configured", never "an endpoint some other provider defaults to": a cloud
provider handed the Ollama host would probe and extract against a local Ollama.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from cryptography.fernet import Fernet

from storico.api.routes.workspace_settings import resolve_llm_config
from storico.config.settings import Settings, _reset_settings_cache
from storico.domain.entities.workspace_llm_config import WorkspaceLLMConfig
from storico.infrastructure.crypto import FernetCipher
from storico.infrastructure.database.repositories import (
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


def _settings(ollama_host: str = "http://ollama.test:11434") -> Settings:
    """Settings with a recognizable Ollama host, so a leak is unmistakable."""
    return Settings(ollama_host=ollama_host)


class _SettingsWithoutAMasterKey:
    """Stand-in for ``Settings`` where ``get_cipher`` reads the master key.

    ``get_cipher`` does ``Settings.load().encryption_key``. A real ``Settings`` reads the
    absolute ``_ENV_FILE``, so it answers with whatever key the developer's ``.env`` holds —
    which is the environment dependence this test has to remove, not assert around.
    """

    @staticmethod
    def load() -> Settings:
        """A keyless ``Settings`` built without reading the developer's ``.env``.

        ``_env_file=None`` drops the dotenv source, and the explicit ``encryption_key=None``
        outranks the process environment, so the premise holds on any machine. The ignore is
        for Pyright's pydantic plugin, which exposes only declared fields on the generated
        ``__init__`` and so cannot see pydantic-settings' underscore parameters.
        """
        return Settings(_env_file=None, encryption_key=None)  # type: ignore[call-arg]


@pytest.mark.integration
class TestResolveLLMConfigBaseUrl:
    """The Ollama host is Ollama's default, not a universal one."""

    @pytest.mark.asyncio
    async def test_cloud_provider_without_a_base_url_resolves_to_none(
        self, db_session, seed_workspace
    ) -> None:
        """A cloud provider has no base URL, and must not be given Ollama's."""
        workspace = await seed_workspace(stories=0)
        repo = _repo(db_session)
        await repo.upsert(
            WorkspaceLLMConfig(
                workspace_id=workspace.workspace_id,
                provider="gemini",
                model="gemini-2.5-flash",
                api_key="key",
            )
        )

        resolved = await resolve_llm_config(workspace.workspace_id, repo, _settings())

        assert resolved.provider == "gemini"
        assert resolved.base_url is None

    @pytest.mark.asyncio
    async def test_ollama_without_a_base_url_resolves_to_the_ollama_host(
        self, db_session, seed_workspace
    ) -> None:
        """Ollama's own default endpoint is the one it should fall back to."""
        workspace = await seed_workspace(stories=0)
        repo = _repo(db_session)
        await repo.upsert(
            WorkspaceLLMConfig(workspace_id=workspace.workspace_id, provider="ollama")
        )

        resolved = await resolve_llm_config(workspace.workspace_id, repo, _settings())

        assert resolved.base_url == "http://ollama.test:11434"

    @pytest.mark.asyncio
    async def test_a_configured_base_url_is_preserved_for_any_provider(
        self, db_session, seed_workspace
    ) -> None:
        """An OpenAI-compatible proxy is a real value and must survive resolution."""
        workspace = await seed_workspace(stories=0)
        repo = _repo(db_session)
        await repo.upsert(
            WorkspaceLLMConfig(
                workspace_id=workspace.workspace_id,
                provider="openai",
                base_url="https://gateway.internal/v1",
                api_key="key",
            )
        )

        resolved = await resolve_llm_config(workspace.workspace_id, repo, _settings())

        assert resolved.base_url == "https://gateway.internal/v1"

    @pytest.mark.asyncio
    async def test_unconfigured_workspace_defaults_to_ollama(
        self, db_session, seed_workspace
    ) -> None:
        """With no row at all the default provider is Ollama, host included."""
        workspace = await seed_workspace(stories=0)
        repo = _repo(db_session)

        resolved = await resolve_llm_config(workspace.workspace_id, repo, _settings())

        assert resolved.provider == "ollama"
        assert resolved.base_url == "http://ollama.test:11434"


@pytest.mark.integration
class TestBlankValuesAreNotStored:
    """``PUT /settings/llm`` stores ``None`` where it used to store a string of spaces.

    "Not configured" then has one representation in the table, and it is the one every
    reader already understands.
    """

    async def _put(self, client, workspace_id, payload: dict):
        """Send a config update and return the response."""
        return await client.put(f"/api/v1/workspaces/{workspace_id}/settings/llm", json=payload)

    @pytest.mark.asyncio
    async def test_a_blank_endpoint_is_stored_as_absent(
        self, authed_client, db_session, seed_workspace
    ) -> None:
        """Spaces are not an endpoint, so they do not become one in the row."""
        seeded = await seed_workspace(stories=0)

        response = await self._put(
            authed_client,
            seeded.workspace_id,
            {"provider": "deepseek", "model": "deepseek-chat", "base_url": "   "},
        )

        assert response.status_code == 200
        stored = await _repo(db_session).get(seeded.workspace_id)
        assert stored is not None
        assert stored.base_url is None

    @pytest.mark.asyncio
    async def test_a_blank_credential_is_stored_as_absent(
        self, authed_client, db_session, seed_workspace
    ) -> None:
        """Same for the credential: a key made of whitespace is not a key."""
        seeded = await seed_workspace(stories=0)

        response = await self._put(
            authed_client,
            seeded.workspace_id,
            {"provider": "openai", "model": "gpt-4o-mini", "api_key": "\t\n"},
        )

        assert response.status_code == 200
        stored = await _repo(db_session).get(seeded.workspace_id)
        assert stored is not None
        assert stored.api_key is None

    @pytest.mark.asyncio
    async def test_a_padded_endpoint_is_stored_trimmed(
        self, authed_client, db_session, seed_workspace
    ) -> None:
        """A real value survives, without the padding a paste leaves behind."""
        seeded = await seed_workspace(stories=0)

        response = await self._put(
            authed_client,
            seeded.workspace_id,
            {
                "provider": "deepseek",
                "model": "deepseek-chat",
                "base_url": "  https://api.deepseek.com/v1  ",
            },
        )

        assert response.status_code == 200
        stored = await _repo(db_session).get(seeded.workspace_id)
        assert stored is not None
        assert stored.base_url == "https://api.deepseek.com/v1"

    @pytest.mark.asyncio
    async def test_an_omitted_field_leaves_the_stored_value_alone(
        self, authed_client, db_session, seed_workspace
    ) -> None:
        """Normalizing must not turn "not part of this update" into "clear it"."""
        seeded = await seed_workspace(stories=0)
        repo = _repo(db_session)
        await repo.upsert(
            WorkspaceLLMConfig(
                workspace_id=seeded.workspace_id,
                provider="openai",
                model="gpt-4o-mini",
                api_key="sk-kept",
                base_url="https://gateway.internal/v1",
            )
        )

        response = await self._put(authed_client, seeded.workspace_id, {"temperature": 0.5})

        assert response.status_code == 200
        stored = await repo.get(seeded.workspace_id)
        assert stored is not None
        assert stored.base_url == "https://gateway.internal/v1"
        assert stored.api_key == "sk-kept"

    @pytest.mark.asyncio
    async def test_a_save_cleans_a_legacy_blank(
        self, authed_client, db_session, seed_workspace
    ) -> None:
        """A row written before this change is repaired by the next save, not preserved."""
        seeded = await seed_workspace(stories=0)
        repo = _repo(db_session)
        await repo.upsert(
            WorkspaceLLMConfig(
                workspace_id=seeded.workspace_id,
                provider="ollama",
                model="llama3.2",
                base_url="   ",
            )
        )

        response = await self._put(authed_client, seeded.workspace_id, {"model": "llama3.2"})

        assert response.status_code == 200
        stored = await repo.get(seeded.workspace_id)
        assert stored is not None
        assert stored.base_url is None


@pytest.mark.integration
class TestBlankValuesReadAsAbsent:
    """A row already holding spaces resolves exactly like a row holding ``NULL``.

    This is what fixes the reported defect for data that already exists: the row cannot be
    rewritten for every workspace, so the read path has to stop believing the spaces.
    """

    async def _seed(
        self, db_session, workspace_id, *, provider: str, base_url: str | None
    ) -> SQLAlchemyWorkspaceLLMConfigRepository:
        """Persist a row with the given endpoint, bypassing the route's normalization."""
        repo = _repo(db_session)
        await repo.upsert(
            WorkspaceLLMConfig(
                workspace_id=workspace_id,
                provider=provider,
                model="llama3.2",
                base_url=base_url,
            )
        )
        return repo

    @pytest.mark.asyncio
    async def test_a_blank_ollama_endpoint_resolves_to_the_default_host(
        self, db_session, seed_workspace
    ) -> None:
        """Ollama's own default, never a URL of spaces."""
        workspace = await seed_workspace(stories=0)
        repo = await self._seed(
            db_session, workspace.workspace_id, provider="ollama", base_url="   "
        )

        resolved = await resolve_llm_config(workspace.workspace_id, repo, _settings())

        assert resolved.base_url == "http://ollama.test:11434"

    @pytest.mark.asyncio
    async def test_a_blank_cloud_endpoint_resolves_to_none(
        self, db_session, seed_workspace
    ) -> None:
        """A cloud provider gets its own default, not a blank override."""
        workspace = await seed_workspace(stories=0)
        repo = await self._seed(
            db_session, workspace.workspace_id, provider="gemini", base_url="  \t "
        )

        resolved = await resolve_llm_config(workspace.workspace_id, repo, _settings())

        assert resolved.base_url is None

    @pytest.mark.asyncio
    async def test_a_blank_credential_resolves_to_none(self, db_session, seed_workspace) -> None:
        """The form must not receive a key made of spaces as if it were a key."""
        workspace = await seed_workspace(stories=0)
        repo = _repo(db_session)
        await repo.upsert(
            WorkspaceLLMConfig(
                workspace_id=workspace.workspace_id,
                provider="openai",
                model="gpt-4o-mini",
                api_key="   ",
            )
        )

        resolved = await resolve_llm_config(workspace.workspace_id, repo, _settings())

        assert resolved.api_key is None

    @pytest.mark.asyncio
    async def test_a_real_endpoint_survives_with_its_content(
        self, db_session, seed_workspace
    ) -> None:
        """Normalizing is not a filter for values that mean something."""
        workspace = await seed_workspace(stories=0)
        repo = await self._seed(
            db_session,
            workspace.workspace_id,
            provider="deepseek",
            base_url="  https://api.deepseek.com/v1  ",
        )

        resolved = await resolve_llm_config(workspace.workspace_id, repo, _settings())

        assert resolved.base_url == "https://api.deepseek.com/v1"


@pytest.mark.integration
class TestCredentialEncryptionThroughTheRoute:
    """The settings route is where an admin's key becomes a stored secret, and back."""

    async def _put(self, client, workspace_id, payload: dict):
        """Send a config update and return the response."""
        return await client.put(f"/api/v1/workspaces/{workspace_id}/settings/llm", json=payload)

    @pytest.mark.asyncio
    async def test_saving_a_key_without_a_master_key_is_refused(
        self, authed_client, db_session, seed_workspace, monkeypatch
    ) -> None:
        """No master key means no write -- never a plaintext one."""
        seeded = await seed_workspace(stories=0)
        # ``monkeypatch.delenv`` cannot establish this premise: ``Settings`` reads the
        # absolute ``_ENV_FILE`` (backend/.env -> repo-root .env), so the dotenv source kept
        # supplying the key this machine already has configured — and that production has too.
        # Patch the lookup ``get_cipher`` performs instead, with a Settings that is keyless by
        # construction.
        monkeypatch.setattr("storico.api.dependencies.Settings", _SettingsWithoutAMasterKey)

        response = await self._put(
            authed_client,
            seeded.workspace_id,
            {"provider": "openai", "model": "gpt-4o-mini", "api_key": "sk-would-be-plaintext"},
        )

        assert response.status_code == 500
        assert response.json()["error_code"] == "ENCRYPTION_KEY_MISSING"
        # The refusal is a refusal: no row reached the table, not even a partial one.
        assert await _repo(db_session).get(seeded.workspace_id) is None

    @pytest.mark.asyncio
    async def test_the_admin_reads_back_the_key_it_saved(
        self, authed_client, seed_workspace
    ) -> None:
        """Encryption must be invisible to the admin who owns the credential."""
        seeded = await seed_workspace(stories=0)

        saved = await self._put(
            authed_client,
            seeded.workspace_id,
            {"provider": "openai", "model": "gpt-4o-mini", "api_key": "sk-round-trip"},
        )
        assert saved.status_code == 200

        response = await authed_client.get(f"/api/v1/workspaces/{seeded.workspace_id}/settings/llm")

        assert response.status_code == 200
        assert response.json()["api_key"] == "sk-round-trip"
