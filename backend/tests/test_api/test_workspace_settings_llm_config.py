"""Resolution tests for the workspace LLM config read path.

``resolve_llm_config`` backs both ``GET`` and ``PUT`` on
``/settings/llm``, and the settings form treats its answer as *the workspace's own
values* — it loads them into the fields and posts them back as the pending
selection. So the resolved ``base_url`` has to mean "the endpoint this workspace
configured", never "an endpoint some other provider defaults to": a cloud
provider handed the Ollama host would probe and extract against a local Ollama.
"""

from __future__ import annotations

import pytest

from storico.api.routes.workspace_settings import resolve_llm_config
from storico.config.settings import Settings
from storico.domain.entities.workspace_llm_config import WorkspaceLLMConfig
from storico.infrastructure.database.repositories import (
    SQLAlchemyWorkspaceLLMConfigRepository,
)


def _settings(ollama_host: str = "http://ollama.test:11434") -> Settings:
    """Settings with a recognizable Ollama host, so a leak is unmistakable."""
    return Settings(ollama_host=ollama_host)


@pytest.mark.integration
class TestResolveLLMConfigBaseUrl:
    """The Ollama host is Ollama's default, not a universal one."""

    @pytest.mark.asyncio
    async def test_cloud_provider_without_a_base_url_resolves_to_none(
        self, db_session, seed_workspace
    ) -> None:
        """A cloud provider has no base URL, and must not be given Ollama's."""
        workspace = await seed_workspace(stories=0)
        repo = SQLAlchemyWorkspaceLLMConfigRepository(db_session)
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
        repo = SQLAlchemyWorkspaceLLMConfigRepository(db_session)
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
        repo = SQLAlchemyWorkspaceLLMConfigRepository(db_session)
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
        repo = SQLAlchemyWorkspaceLLMConfigRepository(db_session)

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
        stored = await SQLAlchemyWorkspaceLLMConfigRepository(db_session).get(seeded.workspace_id)
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
        stored = await SQLAlchemyWorkspaceLLMConfigRepository(db_session).get(seeded.workspace_id)
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
        stored = await SQLAlchemyWorkspaceLLMConfigRepository(db_session).get(seeded.workspace_id)
        assert stored is not None
        assert stored.base_url == "https://api.deepseek.com/v1"

    @pytest.mark.asyncio
    async def test_an_omitted_field_leaves_the_stored_value_alone(
        self, authed_client, db_session, seed_workspace
    ) -> None:
        """Normalizing must not turn "not part of this update" into "clear it"."""
        seeded = await seed_workspace(stories=0)
        repo = SQLAlchemyWorkspaceLLMConfigRepository(db_session)
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
        repo = SQLAlchemyWorkspaceLLMConfigRepository(db_session)
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
        repo = SQLAlchemyWorkspaceLLMConfigRepository(db_session)
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
        repo = SQLAlchemyWorkspaceLLMConfigRepository(db_session)
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
