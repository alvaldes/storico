"""Integration tests for the member-readable LLM config status route.

Covers ``GET /api/v1/workspaces/{workspace_id}/settings/llm/status``: the one route
in the settings module a member may read. It has to answer the readiness question
before a member attempts an extraction, and it has to do that without handing them
the credential or the endpoint the configuration holds.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from cryptography.fernet import Fernet
from sqlalchemy.ext.asyncio import AsyncSession

from storico.config.settings import _reset_settings_cache
from storico.domain.entities.workspace_llm_config import WorkspaceLLMConfig
from storico.domain.entities.workspace_member import WorkspaceRole
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


def _status_url(workspace_id) -> str:
    return f"/api/v1/workspaces/{workspace_id}/settings/llm/status"


async def _seed_config(
    db_session: AsyncSession,
    workspace_id,
    *,
    provider: str,
    model: str | None = None,
    api_key: str | None = None,
    base_url: str | None = None,
) -> None:
    """Persist the workspace's LLM row exactly as the settings form would."""
    await _repo(db_session).upsert(
        WorkspaceLLMConfig(
            workspace_id=workspace_id,
            provider=provider,
            model=model,
            api_key=api_key,
            base_url=base_url,
        )
    )


class TestReadinessAnswer:
    """What the route reports for each configuration shape."""

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_a_member_may_read_the_status(
        self, authed_client, db_session: AsyncSession, seed_workspace
    ) -> None:
        """The route is the member-level exception in an admin-only module."""
        seeded = await seed_workspace(stories=0, role=WorkspaceRole.MEMBER)

        response = await authed_client.get(_status_url(seeded.workspace_id))

        assert response.status_code == 200

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_an_unconfigured_workspace_reports_the_missing_model(
        self, authed_client, seed_workspace
    ) -> None:
        """No row at all resolves to Ollama, whose single requirement is the model."""
        seeded = await seed_workspace(stories=0)

        response = await authed_client.get(_status_url(seeded.workspace_id))

        assert response.json() == {"configured": False, "provider": "ollama", "missing": ["model"]}

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_a_cloud_provider_without_a_key_reports_only_the_key(
        self, authed_client, db_session: AsyncSession, seed_workspace
    ) -> None:
        """A model alone leaves exactly one gap for a cloud provider."""
        seeded = await seed_workspace(stories=0)
        await _seed_config(db_session, seeded.workspace_id, provider="openai", model="gpt-4o-mini")

        response = await authed_client.get(_status_url(seeded.workspace_id))

        assert response.json() == {
            "configured": False,
            "provider": "openai",
            "missing": ["api_key"],
        }

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_a_complete_cloud_configuration_is_reported_ready(
        self, authed_client, db_session: AsyncSession, seed_workspace
    ) -> None:
        """Model plus key is the whole requirement, and the route says so."""
        seeded = await seed_workspace(stories=0)
        await _seed_config(
            db_session,
            seeded.workspace_id,
            provider="gemini",
            model="gemini-2.5-flash",
            api_key="gemini-key",
        )

        response = await authed_client.get(_status_url(seeded.workspace_id))

        assert response.json() == {"configured": True, "provider": "gemini", "missing": []}

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_a_custom_provider_without_an_endpoint_reports_the_base_url(
        self, authed_client, db_session: AsyncSession, seed_workspace
    ) -> None:
        """A custom provider is unusable without the endpoint it should be called at."""
        seeded = await seed_workspace(stories=0)
        await _seed_config(
            db_session, seeded.workspace_id, provider="deepseek", model="deepseek-chat"
        )

        response = await authed_client.get(_status_url(seeded.workspace_id))

        assert response.json() == {
            "configured": False,
            "provider": "deepseek",
            "missing": ["base_url"],
        }

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_a_custom_provider_without_a_key_is_reported_ready(
        self, authed_client, db_session: AsyncSession, seed_workspace
    ) -> None:
        """A self-hosted gateway commonly accepts unauthenticated requests."""
        seeded = await seed_workspace(stories=0)
        await _seed_config(
            db_session,
            seeded.workspace_id,
            provider="deepseek",
            model="deepseek-chat",
            base_url="https://api.deepseek.com/v1",
        )

        response = await authed_client.get(_status_url(seeded.workspace_id))

        assert response.json() == {"configured": True, "provider": "deepseek", "missing": []}

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_an_ollama_workspace_with_a_model_is_ready(
        self, authed_client, db_session: AsyncSession, seed_workspace
    ) -> None:
        """Ollama's host falls back to the configured default, so it is never a gap."""
        seeded = await seed_workspace(stories=0)
        await _seed_config(db_session, seeded.workspace_id, provider="ollama", model="llama3.2")

        response = await authed_client.get(_status_url(seeded.workspace_id))

        assert response.json() == {"configured": True, "provider": "ollama", "missing": []}


class TestDisclosure:
    """What the member-readable answer must not carry."""

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_the_answer_names_fields_and_no_values(
        self, authed_client, db_session: AsyncSession, seed_workspace
    ) -> None:
        """The route reports a gap, never the credential or the endpoint behind it."""
        seeded = await seed_workspace(stories=0, role=WorkspaceRole.MEMBER)
        await _seed_config(
            db_session,
            seeded.workspace_id,
            provider="openai",
            model="gpt-4o-mini",
            api_key="sk-super-secret",
            base_url="https://gateway.internal/v1",
        )

        response = await authed_client.get(_status_url(seeded.workspace_id))

        assert set(response.json()) == {"configured", "provider", "missing"}
        body = response.text
        assert "sk-super-secret" not in body
        assert "https://gateway.internal/v1" not in body


class TestAccessControl:
    """Who may read the status."""

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_a_non_member_is_refused(self, authed_client, seed_workspace) -> None:
        """Readability for members is not readability for everyone."""
        seeded = await seed_workspace(stories=0, member=False)

        response = await authed_client.get(_status_url(seeded.workspace_id))

        assert response.status_code == 403

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_an_unknown_workspace_is_a_not_found(self, authed_client) -> None:
        """Membership is resolved first, so an unknown workspace never leaks existence."""
        from uuid import uuid4

        response = await authed_client.get(_status_url(uuid4()))

        assert response.status_code == 404
