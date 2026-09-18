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
