"""Tests for the credential-encrypting workspace Trello config repository.

The repository mirrors ``SQLAlchemyWorkspaceLLMConfigRepository`` and so do these
tests: the repository is the choke point, the only code that turns a domain credential
into a stored value and back again. These tests read the raw columns *around* the
repository, because a test that reads the values back through the repository's own read
path would pass even if nothing were ever encrypted.
"""

from __future__ import annotations

from uuid import UUID

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import String, select
from sqlalchemy.ext.asyncio import AsyncSession

from storico.api.schemas.workspace_trello import TrelloConfigRequest
from storico.domain.entities import CredentialUndecryptable
from storico.domain.entities.workspace_trello_config import WorkspaceTrelloConfig
from storico.domain.ports import CipherPort
from storico.infrastructure.crypto import FernetCipher
from storico.infrastructure.database.models import WorkspaceTrelloConfigModel
from storico.infrastructure.database.repositories import (
    SQLAlchemyWorkspaceTrelloConfigRepository,
)
from tests._helpers import create_workspace

_API_KEY = "trello-api-key-0123456789abcdef"
_TOKEN = "trello-token-0123456789abcdef-0123456789abcdef"
_MASTER_KEY = Fernet.generate_key().decode("ascii")


class _RecordingCipher(CipherPort):
    """Records every call, so "the cipher was not consulted" is observable."""

    def __init__(self) -> None:
        self.calls: list[str] = []
        self._delegate = FernetCipher(_MASTER_KEY)

    def encrypt(self, plaintext: str) -> str:
        self.calls.append("encrypt")
        return self._delegate.encrypt(plaintext)

    def decrypt(self, stored: str) -> str:
        self.calls.append("decrypt")
        return self._delegate.decrypt(stored)


def _repo(
    session: AsyncSession, cipher: CipherPort | None = None
) -> SQLAlchemyWorkspaceTrelloConfigRepository:
    """The repository as the app wires it: a session plus a cipher."""
    return SQLAlchemyWorkspaceTrelloConfigRepository(session, cipher or FernetCipher(_MASTER_KEY))


async def _stored_values(
    session: AsyncSession, workspace_id: UUID
) -> tuple[str | None, str | None]:
    """The raw ``api_key``/``token`` columns, read without going through the repository."""
    stmt = select(WorkspaceTrelloConfigModel.api_key, WorkspaceTrelloConfigModel.token).where(
        WorkspaceTrelloConfigModel.workspace_id == workspace_id
    )
    row = (await session.execute(stmt)).one()
    return (row[0], row[1])


async def _workspace_id(session: AsyncSession, name: str) -> UUID:
    workspace = await create_workspace(session, name=name)
    return workspace.id


@pytest.mark.asyncio
async def test_upsert_stores_ciphertext_that_does_not_contain_the_plaintext(
    db_session: AsyncSession,
) -> None:
    """The security assertion: the columns hold ciphertext, not the credentials."""
    workspace_id = await _workspace_id(db_session, "Encrypted")

    await _repo(db_session).upsert(
        WorkspaceTrelloConfig(workspace_id=workspace_id, api_key=_API_KEY, token=_TOKEN)
    )

    stored_api_key, stored_token = await _stored_values(db_session, workspace_id)
    assert stored_api_key is not None
    assert stored_api_key.startswith("v1:")
    assert _API_KEY not in stored_api_key
    assert stored_token is not None
    assert stored_token.startswith("v1:")
    assert _TOKEN not in stored_token


@pytest.mark.asyncio
async def test_a_pre_encryption_row_reads_back_as_its_own_plaintext(
    db_session: AsyncSession,
) -> None:
    """The legacy path: a row written before this change is served, not rejected."""
    workspace_id = await _workspace_id(db_session, "Legacy")
    db_session.add(
        WorkspaceTrelloConfigModel(
            workspace_id=workspace_id,
            api_key=_API_KEY,
            token=_TOKEN,
            updated_at=WorkspaceTrelloConfig(workspace_id=workspace_id).updated_at,
        )
    )
    await db_session.commit()

    config = await _repo(db_session).get(workspace_id)

    assert config is not None
    assert config.api_key == _API_KEY
    assert config.token == _TOKEN


@pytest.mark.asyncio
async def test_a_partial_row_reads_back_with_the_other_credential_absent(
    db_session: AsyncSession,
) -> None:
    """One credential saved alone stays alone: a NULL column reads back as None."""
    workspace_id = await _workspace_id(db_session, "Partial")

    await _repo(db_session).upsert(WorkspaceTrelloConfig(workspace_id=workspace_id, token=_TOKEN))

    config = await _repo(db_session).get(workspace_id)
    assert config is not None
    assert config.api_key is None
    assert config.token == _TOKEN


@pytest.mark.asyncio
async def test_upserting_an_existing_row_re_encrypts_and_still_reads_back(
    db_session: AsyncSession,
) -> None:
    """The update branch encrypts too — not only the insert branch."""
    workspace_id = await _workspace_id(db_session, "Updated")
    repo = _repo(db_session)
    config = WorkspaceTrelloConfig(workspace_id=workspace_id, api_key=_API_KEY, token=_TOKEN)
    await repo.upsert(config)
    first = await _stored_values(db_session, workspace_id)

    await repo.upsert(config)

    second = await _stored_values(db_session, workspace_id)
    assert second[0] is not None
    assert second[0].startswith("v1:")
    # Fernet is non-deterministic, so a fresh token proves the update re-encrypted rather
    # than carrying the previous ciphertext across.
    assert second != first

    read_back = await repo.get(workspace_id)
    assert read_back is not None
    assert read_back.api_key == _API_KEY
    assert read_back.token == _TOKEN


@pytest.mark.asyncio
async def test_absent_credentials_stay_absent_and_never_reach_the_cipher(
    db_session: AsyncSession,
) -> None:
    """There is no secret to protect, so the cipher must not be consulted at all."""
    workspace_id = await _workspace_id(db_session, "NoCredential")
    spy = _RecordingCipher()

    await _repo(db_session, spy).upsert(WorkspaceTrelloConfig(workspace_id=workspace_id))

    assert await _stored_values(db_session, workspace_id) == (None, None)
    assert spy.calls == []


def test_the_columns_hold_the_ciphertext_of_the_longest_credential_we_accept() -> None:
    """The accepted length and the stored length are compared, because neither looks wrong alone.

    The request schema caps a credential at 500 characters and what gets stored is the
    *ciphertext*, which Fernet makes about 1.4 times longer. The two numbers are asserted
    against each other instead of each being trusted, and both are read from the code that
    declares them rather than written out here.
    """
    accepted = TrelloConfigRequest.model_fields["api_key"].metadata[0].max_length
    cipher = FernetCipher(_MASTER_KEY)

    for name in ("api_key", "token"):
        column_type = WorkspaceTrelloConfigModel.__table__.c[name].type
        assert isinstance(column_type, String)
        stored_width = getattr(column_type, "length", None)
        assert isinstance(accepted, int) and isinstance(stored_width, int)
        longest = cipher.encrypt("x" * accepted)

        assert len(longest) <= stored_width, (
            f"a {accepted}-character credential stores as {len(longest)} characters, "
            f"which does not fit the declared {stored_width} of '{name}'"
        )


@pytest.mark.asyncio
async def test_a_keyless_cipher_refuses_to_read_ciphertext_instead_of_returning_nothing(
    db_session: AsyncSession,
) -> None:
    """A stored credential that cannot be opened must fail loudly, not read as absent.

    ``None`` is the honest answer for a workspace with no credential, so returning it for a
    value that *has* one would be indistinguishable from that. The repository is where those
    two become confusable, so this is where it is pinned.
    """
    workspace_id = await _workspace_id(db_session, "Unopenable")
    db_session.add(
        WorkspaceTrelloConfigModel(
            workspace_id=workspace_id,
            api_key=FernetCipher(_MASTER_KEY).encrypt(_API_KEY),
            token=FernetCipher(_MASTER_KEY).encrypt(_TOKEN),
            updated_at=WorkspaceTrelloConfig(workspace_id=workspace_id).updated_at,
        )
    )
    await db_session.commit()

    with pytest.raises(CredentialUndecryptable):
        await _repo(db_session, FernetCipher(None)).get(workspace_id)
