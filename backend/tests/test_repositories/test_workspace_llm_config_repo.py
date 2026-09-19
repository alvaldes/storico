"""Tests for the credential-encrypting workspace LLM config repository.

The repository is the choke point: it is the only code that turns a domain credential into a
stored value and back again. These tests read the raw column *around* the repository, because
a test that reads the value back through the repository's own read path would pass even if
nothing were ever encrypted.
"""

from __future__ import annotations

from uuid import UUID

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import String, select
from sqlalchemy.ext.asyncio import AsyncSession

from storico.api.schemas.workspace_llm_config import LLMConfigRequest
from storico.domain.entities.workspace_llm_config import WorkspaceLLMConfig
from storico.domain.ports import CipherPort
from storico.infrastructure.crypto import FernetCipher
from storico.infrastructure.database.models import WorkspaceLLMConfigModel
from storico.infrastructure.database.repositories import (
    SQLAlchemyWorkspaceLLMConfigRepository,
)
from tests._helpers import create_workspace

_PLAINTEXT = "sk-live-0123456789abcdef"
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
) -> SQLAlchemyWorkspaceLLMConfigRepository:
    """The repository as the app wires it: a session plus a cipher."""
    return SQLAlchemyWorkspaceLLMConfigRepository(session, cipher or FernetCipher(_MASTER_KEY))


async def _stored_value(session: AsyncSession, workspace_id: UUID) -> str | None:
    """The raw ``api_key`` column, read without going through the repository."""
    stmt = select(WorkspaceLLMConfigModel.api_key).where(
        WorkspaceLLMConfigModel.workspace_id == workspace_id
    )
    return (await session.execute(stmt)).scalar_one()


async def _workspace_id(session: AsyncSession, name: str) -> UUID:
    workspace = await create_workspace(session, name=name)
    return workspace.id


@pytest.mark.asyncio
async def test_upsert_stores_ciphertext_that_does_not_contain_the_plaintext(
    db_session: AsyncSession,
) -> None:
    """The security assertion: the column holds ciphertext, not the credential."""
    workspace_id = await _workspace_id(db_session, "Encrypted")

    await _repo(db_session).upsert(
        WorkspaceLLMConfig(
            workspace_id=workspace_id,
            provider="openai",
            model="gpt-4o-mini",
            api_key=_PLAINTEXT,
        )
    )

    stored = await _stored_value(db_session, workspace_id)
    assert stored is not None
    assert stored.startswith("v1:")
    assert _PLAINTEXT not in stored


@pytest.mark.asyncio
async def test_a_pre_encryption_row_reads_back_as_its_own_plaintext(
    db_session: AsyncSession,
) -> None:
    """The legacy path: a row written before this change is served, not rejected."""
    workspace_id = await _workspace_id(db_session, "Legacy")
    db_session.add(
        WorkspaceLLMConfigModel(
            workspace_id=workspace_id,
            provider="openai",
            api_key=_PLAINTEXT,
            updated_at=WorkspaceLLMConfig(workspace_id=workspace_id).updated_at,
        )
    )
    await db_session.commit()

    config = await _repo(db_session).get(workspace_id)

    assert config is not None
    assert config.api_key == _PLAINTEXT


@pytest.mark.asyncio
async def test_upserting_an_existing_row_re_encrypts_and_still_reads_back(
    db_session: AsyncSession,
) -> None:
    """The update branch encrypts too — not only the insert branch."""
    workspace_id = await _workspace_id(db_session, "Updated")
    repo = _repo(db_session)
    config = WorkspaceLLMConfig(
        workspace_id=workspace_id,
        provider="openai",
        api_key=_PLAINTEXT,
    )
    await repo.upsert(config)
    first = await _stored_value(db_session, workspace_id)

    await repo.upsert(config)

    second = await _stored_value(db_session, workspace_id)
    assert second is not None
    assert second.startswith("v1:")
    # Fernet is non-deterministic, so a fresh token proves the update re-encrypted rather
    # than carrying the previous ciphertext across.
    assert second != first

    read_back = await repo.get(workspace_id)
    assert read_back is not None
    assert read_back.api_key == _PLAINTEXT


@pytest.mark.asyncio
async def test_a_none_credential_stays_none_and_never_reaches_the_cipher(
    db_session: AsyncSession,
) -> None:
    """There is no secret to protect, so the cipher must not be consulted at all."""
    workspace_id = await _workspace_id(db_session, "NoCredential")
    spy = _RecordingCipher()

    await _repo(db_session, spy).upsert(
        WorkspaceLLMConfig(
            workspace_id=workspace_id,
            provider="ollama",
            model="llama3.2",
            api_key=None,
        )
    )

    assert await _stored_value(db_session, workspace_id) is None
    assert spy.calls == []


def test_the_column_holds_the_ciphertext_of_the_longest_credential_we_accept() -> None:
    """The accepted length and the stored length are compared, because neither looks wrong alone.

    The request schema caps a credential at 500 characters and the column was originally sized for
    a credential — but what gets stored is the *ciphertext*, and Fernet's output is about 1.4 times
    longer. A schema that accepts 500 and a column that holds 500 pass every check on SQLite, which
    does not enforce a VARCHAR length, and fail on the first Postgres write. So the two numbers are
    asserted against each other instead of each being trusted, and both are read from the code that
    declares them rather than written out here.
    """
    accepted = LLMConfigRequest.model_fields["api_key"].metadata[0].max_length
    column_type = WorkspaceLLMConfigModel.__table__.c.api_key.type

    # Asserted rather than assumed: `length` belongs to the string types, and a column that stopped
    # being one would make this test read its width out of nothing.
    assert isinstance(column_type, String)
    stored_width = getattr(column_type, "length", None)
    assert isinstance(accepted, int) and isinstance(stored_width, int)
    longest = FernetCipher(_MASTER_KEY).encrypt("x" * accepted)

    assert len(longest) <= stored_width, (
        f"a {accepted}-character credential stores as {len(longest)} characters, "
        f"which does not fit the declared {stored_width}"
    )
