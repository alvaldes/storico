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
from storico.domain.entities import CredentialUndecryptable
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


class TestJudgeModelRoundTrip:
    """``judge_model`` rides the same entity/column plumbing as every other field (D7).

    The judge's model name is a model name, not a credential: it must never reach the
    cipher, and an upsert whose entity carries no judge model must store ``NULL`` —
    the repository writes the whole row from the entity it is handed, so clearing is
    expressed by leaving the field ``None`` on the entity.
    """

    @pytest.mark.asyncio
    async def test_a_configured_judge_model_round_trips_and_never_reaches_the_cipher(
        self, db_session: AsyncSession
    ) -> None:
        workspace_id = await _workspace_id(db_session, "JudgeConfigured")
        spy = _RecordingCipher()

        await _repo(db_session, spy).upsert(
            WorkspaceLLMConfig(
                workspace_id=workspace_id,
                provider="ollama",
                model="llama3.2",
                judge_model="qwen2.5-judge",
            )
        )

        config = await _repo(db_session).get(workspace_id)
        assert config is not None
        assert config.judge_model == "qwen2.5-judge"
        # A model name is not a secret: the cipher was not consulted for it.
        assert spy.calls == []

    @pytest.mark.asyncio
    async def test_an_absent_judge_model_stays_null(self, db_session: AsyncSession) -> None:
        workspace_id = await _workspace_id(db_session, "JudgeAbsent")

        await _repo(db_session).upsert(
            WorkspaceLLMConfig(workspace_id=workspace_id, provider="ollama")
        )

        config = await _repo(db_session).get(workspace_id)
        assert config is not None
        assert config.judge_model is None

    @pytest.mark.asyncio
    async def test_a_judge_model_cleared_on_the_entity_is_cleared_in_the_column(
        self, db_session: AsyncSession
    ) -> None:
        workspace_id = await _workspace_id(db_session, "JudgeCleared")
        repo = _repo(db_session)
        await repo.upsert(
            WorkspaceLLMConfig(
                workspace_id=workspace_id,
                provider="ollama",
                judge_model="qwen2.5-judge",
            )
        )

        await repo.upsert(
            WorkspaceLLMConfig(workspace_id=workspace_id, provider="ollama", judge_model=None)
        )

        stmt = select(WorkspaceLLMConfigModel.judge_model).where(
            WorkspaceLLMConfigModel.workspace_id == workspace_id
        )
        assert (await db_session.execute(stmt)).scalar_one() is None


class TestJudgeConnectionRoundTrip:
    """The judge's own connection fields (D9/S10) ride the same plumbing.

    ``judge_provider`` and ``judge_base_url`` are plain values; ``judge_api_key`` is a
    credential and must be encrypted on the way in and decrypted on the way out by the
    repository and nobody else.
    """

    @pytest.mark.asyncio
    async def test_the_three_fields_round_trip_with_the_credential_encrypted(
        self, db_session: AsyncSession
    ) -> None:
        workspace_id = await _workspace_id(db_session, "JudgeConnection")

        await _repo(db_session).upsert(
            WorkspaceLLMConfig(
                workspace_id=workspace_id,
                provider="openai",
                model="gpt-4o-mini",
                judge_model="claude-judge",
                judge_provider="anthropic",
                judge_api_key=_PLAINTEXT,
                judge_base_url="https://gateway.internal/v1",
            )
        )

        # The raw column holds ciphertext, not the credential.
        stmt = select(WorkspaceLLMConfigModel.judge_api_key).where(
            WorkspaceLLMConfigModel.workspace_id == workspace_id
        )
        stored = (await db_session.execute(stmt)).scalar_one()
        assert stored is not None
        assert stored.startswith("v1:")
        assert _PLAINTEXT not in stored

        config = await _repo(db_session).get(workspace_id)
        assert config is not None
        assert config.judge_model == "claude-judge"
        assert config.judge_provider == "anthropic"
        assert config.judge_api_key == _PLAINTEXT
        assert config.judge_base_url == "https://gateway.internal/v1"

    @pytest.mark.asyncio
    async def test_an_absent_judge_connection_stays_null_and_never_reaches_the_cipher(
        self, db_session: AsyncSession
    ) -> None:
        workspace_id = await _workspace_id(db_session, "JudgeConnectionAbsent")
        spy = _RecordingCipher()

        await _repo(db_session, spy).upsert(
            WorkspaceLLMConfig(workspace_id=workspace_id, provider="ollama", model="llama3.2")
        )

        config = await _repo(db_session, spy).get(workspace_id)
        assert config is not None
        assert config.judge_provider is None
        assert config.judge_api_key is None
        assert config.judge_base_url is None
        assert spy.calls == []

    @pytest.mark.asyncio
    async def test_a_judge_credential_cleared_on_the_entity_is_cleared_in_the_column(
        self, db_session: AsyncSession
    ) -> None:
        workspace_id = await _workspace_id(db_session, "JudgeConnectionCleared")
        repo = _repo(db_session)
        await repo.upsert(
            WorkspaceLLMConfig(
                workspace_id=workspace_id,
                provider="openai",
                judge_provider="openai",
                judge_api_key=_PLAINTEXT,
                judge_base_url="https://gateway.internal/v1",
            )
        )

        await repo.upsert(
            WorkspaceLLMConfig(
                workspace_id=workspace_id,
                provider="openai",
                judge_provider=None,
                judge_api_key=None,
                judge_base_url=None,
            )
        )

        stmt = select(
            WorkspaceLLMConfigModel.judge_provider,
            WorkspaceLLMConfigModel.judge_api_key,
            WorkspaceLLMConfigModel.judge_base_url,
        ).where(WorkspaceLLMConfigModel.workspace_id == workspace_id)
        row = (await db_session.execute(stmt)).one()
        assert row.judge_provider is None
        assert row.judge_api_key is None
        assert row.judge_base_url is None

    def test_the_judge_credential_column_holds_the_ciphertext_of_the_longest_credential_we_accept(
        self,
    ) -> None:
        """``judge_api_key`` is the same kind of column as ``api_key``, so the same
        arithmetic binds it: the request caps the plaintext, the column stores the
        ciphertext, and the two numbers are asserted against each other.
        """
        accepted = LLMConfigRequest.model_fields["judge_api_key"].metadata[0].max_length
        column_type = WorkspaceLLMConfigModel.__table__.c.judge_api_key.type

        assert isinstance(column_type, String)
        stored_width = getattr(column_type, "length", None)
        assert isinstance(accepted, int) and isinstance(stored_width, int)
        longest = FernetCipher(_MASTER_KEY).encrypt("x" * accepted)

        assert len(longest) <= stored_width, (
            f"a {accepted}-character credential stores as {len(longest)} characters, "
            f"which does not fit the declared {stored_width}"
        )


@pytest.mark.asyncio
async def test_a_keyless_cipher_refuses_to_read_ciphertext_instead_of_returning_nothing(
    db_session: AsyncSession,
) -> None:
    """A stored credential that cannot be opened must fail loudly, not read as absent.

    ``None`` is the honest answer for a workspace with no credential, so returning it for a
    value that *has* one would be indistinguishable from that — and the consequence is worse
    than a missing key: the readiness rule would tell the admin to configure a credential that
    is already configured, while the real problem is the master key on the server.

    The repository is where those two become confusable, so this is where it is pinned. A
    version of this repository that swallowed the cipher's error into ``None`` passes every
    other test in this file.
    """
    workspace_id = await _workspace_id(db_session, "Unopenable")
    db_session.add(
        WorkspaceLLMConfigModel(
            workspace_id=workspace_id,
            provider="openai",
            api_key=FernetCipher(_MASTER_KEY).encrypt(_PLAINTEXT),
            updated_at=WorkspaceLLMConfig(workspace_id=workspace_id).updated_at,
        )
    )
    await db_session.commit()

    with pytest.raises(CredentialUndecryptable):
        await _repo(db_session, FernetCipher(None)).get(workspace_id)
