"""Integration tests for the workspace Trello credential settings routes.

Covers ``GET``/``PUT /api/v1/workspaces/{workspace_id}/settings/trello`` (admin-only,
returning the decrypted pair) and ``GET .../settings/trello/status`` (member-readable,
answering field names only). The conventions follow the sibling LLM config module:
the admin reads back what it saved, the member learns readiness without the secret,
and a missing master key surfaces through the cipher error envelope.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from storico.config.settings import _reset_settings_cache
from storico.domain.entities.workspace_member import WorkspaceRole
from storico.domain.entities.workspace_trello_config import WorkspaceTrelloConfig
from storico.infrastructure.crypto import FernetCipher
from storico.infrastructure.database.models import WorkspaceTrelloConfigModel
from storico.infrastructure.database.repositories import (
    SQLAlchemyWorkspaceTrelloConfigRepository,
)

_MASTER_KEY = Fernet.generate_key().decode("ascii")
_API_KEY = "trello-api-key-visible"
_TOKEN = "trello-token-visible"


@pytest.fixture(autouse=True)
def _master_key(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Give the app a master key, so a route-level save encrypts like production."""
    monkeypatch.setenv("STORICO_ENCRYPTION_KEY", _MASTER_KEY)
    _reset_settings_cache()
    yield
    _reset_settings_cache()


def _repo(session: AsyncSession) -> SQLAlchemyWorkspaceTrelloConfigRepository:
    """The repository as the app wires it: a session plus the cipher."""
    return SQLAlchemyWorkspaceTrelloConfigRepository(session, FernetCipher(_MASTER_KEY))


def _url(workspace_id) -> str:
    return f"/api/v1/workspaces/{workspace_id}/settings/trello"


def _status_url(workspace_id) -> str:
    return f"/api/v1/workspaces/{workspace_id}/settings/trello/status"


async def _stored_values(db_session: AsyncSession, workspace_id) -> tuple[str | None, str | None]:
    """The raw ``api_key``/``token`` columns, read without going through the repository."""
    stmt = select(WorkspaceTrelloConfigModel.api_key, WorkspaceTrelloConfigModel.token).where(
        WorkspaceTrelloConfigModel.workspace_id == workspace_id
    )
    row = (await db_session.execute(stmt)).one()
    return (row[0], row[1])


class TestAdminConfigRoundTrip:
    """The admin stores the pair, and reads the pair back — never ciphertext."""

    @pytest.mark.asyncio
    async def test_an_unconfigured_workspace_answers_nulls(
        self, authed_client, seed_workspace
    ) -> None:
        """No row at all is not an error: the form just loads empty fields."""
        seeded = await seed_workspace(stories=0)

        response = await authed_client.get(_url(seeded.workspace_id))

        assert response.status_code == 200
        assert response.json() == {"api_key": None, "token": None}

    @pytest.mark.asyncio
    async def test_put_stores_ciphertext_and_get_returns_plaintext(
        self, authed_client, db_session: AsyncSession, seed_workspace
    ) -> None:
        """Encryption is invisible to the admin who owns the credential — and real."""
        seeded = await seed_workspace(stories=0)

        saved = await authed_client.put(
            _url(seeded.workspace_id), json={"api_key": _API_KEY, "token": _TOKEN}
        )
        assert saved.status_code == 200

        # The column holds ciphertext, not the credentials.
        stored_api_key, stored_token = await _stored_values(db_session, seeded.workspace_id)
        assert stored_api_key is not None and stored_api_key.startswith("v1:")
        assert _API_KEY not in stored_api_key
        assert stored_token is not None and stored_token.startswith("v1:")
        assert _TOKEN not in stored_token

        response = await authed_client.get(_url(seeded.workspace_id))
        assert response.status_code == 200
        assert response.json() == {"api_key": _API_KEY, "token": _TOKEN}

    @pytest.mark.asyncio
    async def test_a_blank_credential_is_stored_as_absent(
        self, authed_client, db_session: AsyncSession, seed_workspace
    ) -> None:
        """A key made of whitespace is not a key, and is not encrypted into one either."""
        seeded = await seed_workspace(stories=0)

        response = await authed_client.put(
            _url(seeded.workspace_id), json={"api_key": "   ", "token": _TOKEN}
        )

        assert response.status_code == 200
        stored_api_key, stored_token = await _stored_values(db_session, seeded.workspace_id)
        assert stored_api_key is None
        assert stored_token is not None and stored_token.startswith("v1:")

    @pytest.mark.asyncio
    async def test_an_omitted_field_leaves_the_stored_value_alone(
        self, authed_client, db_session: AsyncSession, seed_workspace
    ) -> None:
        """Normalizing must not turn "not part of this update" into "clear it"."""
        seeded = await seed_workspace(stories=0)
        await _repo(db_session).upsert(
            WorkspaceTrelloConfig(workspace_id=seeded.workspace_id, token=_TOKEN)
        )

        response = await authed_client.put(_url(seeded.workspace_id), json={"api_key": _API_KEY})

        assert response.status_code == 200
        stored_api_key, stored_token = await _stored_values(db_session, seeded.workspace_id)
        assert stored_api_key is not None and stored_api_key.startswith("v1:")
        assert stored_token is not None and stored_token.startswith("v1:")
        read_back = await _repo(db_session).get(seeded.workspace_id)
        assert read_back is not None
        assert read_back.api_key == _API_KEY
        assert read_back.token == _TOKEN


class TestAccessControl:
    """Who may read and write the credentials."""

    @pytest.mark.asyncio
    async def test_a_member_cannot_read_the_credentials(
        self, authed_client, seed_workspace
    ) -> None:
        """Membership alone is not the admin role the credential read requires."""
        seeded = await seed_workspace(stories=0, role=WorkspaceRole.MEMBER)

        response = await authed_client.get(_url(seeded.workspace_id))

        assert response.status_code == 403
        assert response.json()["error_code"] == "ADMIN_ACCESS_REQUIRED"

    @pytest.mark.asyncio
    async def test_a_member_cannot_write_the_credentials(
        self, authed_client, seed_workspace
    ) -> None:
        """The write gate is the same admin gate as the read."""
        seeded = await seed_workspace(stories=0, role=WorkspaceRole.MEMBER)

        response = await authed_client.put(
            _url(seeded.workspace_id), json={"api_key": _API_KEY, "token": _TOKEN}
        )

        assert response.status_code == 403
        assert response.json()["error_code"] == "ADMIN_ACCESS_REQUIRED"

    @pytest.mark.asyncio
    async def test_a_non_member_is_refused(self, authed_client, seed_workspace) -> None:
        """Not a member is refused with the membership code, before any role check."""
        seeded = await seed_workspace(stories=0, member=False)

        response = await authed_client.get(_url(seeded.workspace_id))

        assert response.status_code == 403
        assert response.json()["error_code"] == "NOT_A_WORKSPACE_MEMBER"

    @pytest.mark.asyncio
    async def test_an_unknown_workspace_is_a_not_found(self, authed_client) -> None:
        """Membership is resolved first, so an unknown workspace never leaks existence."""
        from uuid import uuid4

        response = await authed_client.get(_url(uuid4()))

        assert response.status_code == 404


class TestMissingMasterKey:
    """A deployment without a master key must fail loudly, not leak plaintext."""

    @pytest.mark.asyncio
    async def test_saving_without_a_master_key_is_refused(
        self, authed_client, db_session: AsyncSession, seed_workspace, monkeypatch
    ) -> None:
        """No master key means no write — never a plaintext one."""
        from tests.test_api.test_workspace_settings_llm_config import (
            _SettingsWithoutAMasterKey,
        )

        seeded = await seed_workspace(stories=0)
        # Same trick as the LLM sibling: patch the lookup ``get_cipher`` performs, because
        # a real ``Settings`` reads the absolute ``_ENV_FILE`` and keeps supplying the key
        # this machine already has configured.
        monkeypatch.setattr("storico.api.dependencies.Settings", _SettingsWithoutAMasterKey)

        response = await authed_client.put(
            _url(seeded.workspace_id), json={"api_key": _API_KEY, "token": _TOKEN}
        )

        assert response.status_code == 500
        assert response.json()["error_code"] == "ENCRYPTION_KEY_MISSING"
        # The refusal is a refusal: no row reached the table, not even a partial one.
        assert await _repo(db_session).get(seeded.workspace_id) is None

    @pytest.mark.asyncio
    async def test_reading_ciphertext_without_a_master_key_answers_the_envelope(
        self, authed_client, db_session: AsyncSession, seed_workspace, monkeypatch
    ) -> None:
        """A stored pair that cannot be opened is a 500, not a crash or a null pair."""
        from tests.test_api.test_workspace_settings_llm_config import (
            _SettingsWithoutAMasterKey,
        )

        seeded = await seed_workspace(stories=0)
        await _repo(db_session).upsert(
            WorkspaceTrelloConfig(workspace_id=seeded.workspace_id, token=_TOKEN)
        )
        monkeypatch.setattr("storico.api.dependencies.Settings", _SettingsWithoutAMasterKey)

        response = await authed_client.get(_url(seeded.workspace_id))

        assert response.status_code == 500
        assert response.json()["error_code"] == "CREDENTIAL_UNDECRYPTABLE"


class TestMemberStatus:
    """The member-readable answer: configured or not, and which fields are missing."""

    @pytest.mark.asyncio
    async def test_an_unconfigured_workspace_names_both_fields(
        self, authed_client, seed_workspace
    ) -> None:
        """No row means both credentials are missing, by name."""
        seeded = await seed_workspace(stories=0)

        response = await authed_client.get(_status_url(seeded.workspace_id))

        assert response.status_code == 200
        assert response.json() == {"configured": False, "missing": ["api_key", "token"]}

    @pytest.mark.asyncio
    async def test_a_member_may_read_the_status(
        self, authed_client, db_session: AsyncSession, seed_workspace
    ) -> None:
        """The route is the member-level exception, exactly like /settings/llm/status."""
        seeded = await seed_workspace(stories=0, role=WorkspaceRole.MEMBER)
        await _repo(db_session).upsert(
            WorkspaceTrelloConfig(workspace_id=seeded.workspace_id, token=_TOKEN)
        )

        response = await authed_client.get(_status_url(seeded.workspace_id))

        assert response.status_code == 200
        assert response.json() == {"configured": False, "missing": ["api_key"]}

    @pytest.mark.asyncio
    async def test_a_complete_configuration_is_reported_ready(
        self, authed_client, db_session: AsyncSession, seed_workspace
    ) -> None:
        """Both credentials present means configured, with an empty missing list."""
        seeded = await seed_workspace(stories=0)
        await _repo(db_session).upsert(
            WorkspaceTrelloConfig(workspace_id=seeded.workspace_id, api_key=_API_KEY, token=_TOKEN)
        )

        response = await authed_client.get(_status_url(seeded.workspace_id))

        assert response.status_code == 200
        assert response.json() == {"configured": True, "missing": []}

    @pytest.mark.asyncio
    async def test_the_answer_names_fields_and_no_values(
        self, authed_client, db_session: AsyncSession, seed_workspace
    ) -> None:
        """The route reports a gap, never the credential behind it."""
        seeded = await seed_workspace(stories=0, role=WorkspaceRole.MEMBER)
        await _repo(db_session).upsert(
            WorkspaceTrelloConfig(workspace_id=seeded.workspace_id, token=_TOKEN)
        )

        response = await authed_client.get(_status_url(seeded.workspace_id))

        assert set(response.json()) == {"configured", "missing"}
        assert _TOKEN not in response.text
        assert _API_KEY not in response.text

    @pytest.mark.asyncio
    async def test_a_non_member_is_refused_on_status_too(
        self, authed_client, seed_workspace
    ) -> None:
        """Readability for members is not readability for everyone."""
        seeded = await seed_workspace(stories=0, member=False)

        response = await authed_client.get(_status_url(seeded.workspace_id))

        assert response.status_code == 403
        assert response.json()["error_code"] == "NOT_A_WORKSPACE_MEMBER"
