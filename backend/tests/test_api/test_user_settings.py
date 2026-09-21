"""Tests for the user preferences endpoints.

``GET``/``PUT /api/v1/users/me/settings``. They had no coverage before this change, which is
how a per-user LLM block — with an ``api_key`` field per provider — stayed in the contract
long after the editor that wrote it was deleted.

The two behaviours worth pinning are the ones a schema change puts at risk: the payload
carries no credential, and a document written by the *previous* version still answers instead
of failing validation.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from storico.domain.entities.user import User
from storico.infrastructure.database.repositories import (
    SQLAlchemyUserPreferencesRepository,
)

URL = "/api/v1/users/me/settings"

#: The shape the per-user LLM editor used to write, before revision 0022 removed it.
LEGACY_DOCUMENT: dict = {
    "llm": {
        "provider": "openai",
        "openai": {"model": "gpt-4o-mini", "apiKey": "sk-legacy-plaintext"},
    },
    "export": {"defaultFormat": "markdown"},
}


class TestGetPreferences:
    """What the endpoint answers."""

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_it_requires_a_session(self, async_client: AsyncClient) -> None:
        """An unauthenticated read is refused."""
        response = await async_client.get(URL)

        assert response.status_code == 401

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_a_user_without_a_row_gets_the_defaults(self, authed_client: AsyncClient) -> None:
        """No row is not an error: the export default comes back."""
        response = await authed_client.get(URL)

        assert response.status_code == 200
        body = response.json()
        assert body["preferences"] == {"export": {"defaultFormat": "json"}}
        assert "updatedAt" in body

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_the_payload_carries_no_llm_block(
        self, authed_client: AsyncClient, db_session: AsyncSession, authed_user: User
    ) -> None:
        """Even a row that still holds one: the credential never leaves the database again.

        This is the whole point of the change — the field has no reader, and it was reachable
        over the API for as long as the schema declared it.
        """
        repo = SQLAlchemyUserPreferencesRepository(db_session)
        await repo.upsert(authed_user.id, LEGACY_DOCUMENT)

        response = await authed_client.get(URL)

        assert response.status_code == 200
        # Asserted on the raw text, not on the parsed body: a key that vanished from the model
        # would also vanish from a dict comparison, so only the body itself shows the absence.
        assert "llm" not in response.text
        assert "sk-legacy-plaintext" not in response.text
        assert response.json()["preferences"] == {"export": {"defaultFormat": "markdown"}}

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_a_stored_document_is_not_rewritten_by_reading_it(
        self, authed_client: AsyncClient, db_session: AsyncSession, authed_user: User
    ) -> None:
        """The read is tolerant, not a migration: storage keeps what it has until 0022 runs."""
        repo = SQLAlchemyUserPreferencesRepository(db_session)
        await repo.upsert(authed_user.id, LEGACY_DOCUMENT)

        await authed_client.get(URL)

        stored = await repo.get(authed_user.id)
        assert stored is not None
        assert "llm" in stored.preferences

    @pytest.mark.asyncio
    @pytest.mark.integration
    @pytest.mark.parametrize("spelling", ["default_format", "defaultFormat"])
    async def test_a_retired_export_format_is_served_as_json(
        self,
        authed_client: AsyncClient,
        db_session: AsyncSession,
        authed_user: User,
        spelling: str,
    ) -> None:
        """A stored ``trello`` reads as ``json`` instead of failing validation.

        The ``Literal`` no longer declares the value, so without the rewrite this row raises
        inside the route and answers 500. Both spellings the store can hold are covered:
        ``model_dump()`` writes ``default_format``, a client on the old contract wrote
        ``defaultFormat``. The rewrite is a read, not a write-back — storage keeps what it has.
        """
        repo = SQLAlchemyUserPreferencesRepository(db_session)
        await repo.upsert(authed_user.id, {"export": {spelling: "trello"}})

        response = await authed_client.get(URL)

        assert response.status_code == 200
        assert response.json()["preferences"] == {"export": {"defaultFormat": "json"}}
        stored = await repo.get(authed_user.id)
        assert stored is not None
        assert stored.preferences == {"export": {spelling: "trello"}}


class TestPutPreferences:
    """What the endpoint accepts."""

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_it_round_trips_the_export_default(self, authed_client: AsyncClient) -> None:
        """The preference the UI exposes is the one this endpoint carries."""
        response = await authed_client.put(
            URL, json={"preferences": {"export": {"defaultFormat": "markdown"}}}
        )

        assert response.status_code == 200
        assert response.json()["preferences"] == {"export": {"defaultFormat": "markdown"}}

        read_back = await authed_client.get(URL)
        assert read_back.json()["preferences"] == {"export": {"defaultFormat": "markdown"}}

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_an_llm_block_in_the_body_is_refused(self, authed_client: AsyncClient) -> None:
        """``422``, not a silent drop: there is no way to put a key back through this endpoint."""
        response = await authed_client.put(
            URL,
            json={
                "preferences": {
                    "llm": {"provider": "openai", "openai": {"apiKey": "sk-new"}},
                    "export": {"defaultFormat": "json"},
                }
            },
        )

        assert response.status_code == 422
        body = response.text
        assert "llm" in body

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_an_unknown_field_is_still_refused(self, authed_client: AsyncClient) -> None:
        """The tolerant read is narrow: only the removed key is dropped, and only on read."""
        response = await authed_client.put(
            URL,
            json={"preferences": {"export": {"defaultFormat": "json"}, "surprise": 1}},
        )

        assert response.status_code == 422

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_an_invalid_export_format_is_refused(self, authed_client: AsyncClient) -> None:
        """The enum is still enforced."""
        response = await authed_client.put(
            URL, json={"preferences": {"export": {"defaultFormat": "pdf"}}}
        )

        assert response.status_code == 422

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_a_retired_export_format_is_refused(self, authed_client: AsyncClient) -> None:
        """``422``, not a silent rewrite: the read tolerates a stored ``trello``, a write does not.

        Rewriting here would answer ``200`` with ``json`` and tell the client it stored what it
        sent. Refusing is the honest answer, and it is what makes the asymmetry observable.
        """
        response = await authed_client.put(
            URL, json={"preferences": {"export": {"defaultFormat": "trello"}}}
        )

        assert response.status_code == 422
        assert "trello" in response.text
