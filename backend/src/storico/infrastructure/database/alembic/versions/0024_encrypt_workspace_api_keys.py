"""encrypt stored workspace LLM API keys

``workspace_llm_configs.api_key`` was added by revision 0011 and has been stored as
plaintext ever since. This revision encrypts the values already in that column; it is the
data half of the change that makes ``docs/security.md`` honest, and the code half is the
repository, which now encrypts on write and decrypts on read.

**Run this after the release that encrypts and decrypts is deployed.** The new code reads a
value carrying the ``v1:`` prefix as ciphertext and a value without it as legacy plaintext,
so it serves both halves of the migration. The previous release has no such tolerance: it
would hand the ciphertext to a provider as if it were an API key. Revision 0022 asks for the
same order; revision 0023 asks for the opposite. Each is right for its own change — a column
the new code already selects must exist first, while values the new code already understands
can only be rewritten once that code is live.

``NULL`` is left alone: there is no secret to protect, and inventing one would be a lie. An
empty string is left alone for the same reason — it is the other spelling of "no credential",
which the read path already treats as absent — and so nothing is spent encrypting it. A value
that already carries the ``v1:`` prefix is skipped, so a partially applied or re-run migration
cannot double-encrypt.

With no master key configured this raises rather than doing nothing. A migration that reports
success while leaving credentials in plaintext is the exact failure this revision exists to
remove.

Revision ID: 0024
Revises: 0023
Create Date: 2026-09-19
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.orm import Session

from storico.config.settings import Settings
from storico.infrastructure.crypto.fernet_cipher import PREFIX, FernetCipher

# revision identifiers, used by Alembic.
revision: str = "0024"
down_revision: str | None = "0023"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# The width the column needs once its contents are ciphertext.
#
# Spelled here rather than imported from the model, for the same reason 0022 spells its removed key:
# a migration has to keep working against the schema as it was when the revision was written, after
# the model has moved on. 500 characters of plaintext measure 763 encrypted (Fernet's base64 output
# plus the version prefix), so a column sized for the credential is not sized for its ciphertext.
_API_KEY_LENGTH = 1000


def _credentials() -> sa.TableClause:
    """The column this revision rewrites, addressed without the ORM model.

    A migration has to keep working against the schema as it was when the revision was
    written, and that schema is this frozen definition — the model has since moved on.
    """
    return sa.table(
        "workspace_llm_configs",
        sa.column("id", sa.Uuid()),
        sa.column("api_key", sa.String(500)),
    )


def _cipher() -> FernetCipher:
    """Build the cipher from the configured master key.

    Raises:
        RuntimeError: when no master key is configured. Refusing is the point of the check:
            the alternative is a migration that reports success and leaves every credential
            readable.
    """
    settings = Settings.load()
    if not settings.encryption_key:
        raise RuntimeError(
            "STORICO_ENCRYPTION_KEY is not set, so stored workspace LLM credentials cannot "
            "be encrypted. Set it to a Fernet key and run this migration again; already "
            "encrypted rows are skipped, so re-running is safe."
        )
    return FernetCipher(settings.encryption_key)


def upgrade() -> None:
    """Make room for the ciphertext, then replace every stored plaintext credential with it.

    The widening is first and is not incidental. The column was sized for a credential, not for a
    credential's ciphertext, and Fernet's output is about 1.4 times longer: a 500-character key
    stores as 763. Encrypting into the old width would raise on Postgres for any credential past
    303 characters — measured, not estimated — and SQLite, which does not enforce a VARCHAR length,
    would accept the overflow silently and leave it to be discovered on the next Postgres write.
    """
    with op.batch_alter_table("workspace_llm_configs") as batch:
        batch.alter_column(
            "api_key",
            existing_type=sa.String(500),
            type_=sa.String(_API_KEY_LENGTH),
            existing_nullable=True,
        )

    cipher = _cipher()
    table = _credentials()

    with Session(op.get_bind()) as session:
        rows = session.execute(
            sa.select(table.c.id, table.c.api_key).where(table.c.api_key.is_not(None))
        ).fetchall()

        for row_id, api_key in rows:
            # ``NULL`` is filtered out by the query; ``''`` is filtered here. Neither holds a
            # secret, so neither is rewritten.
            if not api_key or api_key.startswith(PREFIX):
                continue
            session.execute(
                sa.update(table).where(table.c.id == row_id).values(api_key=cipher.encrypt(api_key))
            )

        session.commit()


def downgrade() -> None:
    """Return every stored credential to **plaintext**.

    Spelled out because it is the point: this restores the unprotected state. Rows the
    upgrade encrypted become readable to anyone with database access again, which is exactly
    what a release predating encryption needs, and what makes running this a security
    decision rather than a mechanical one.

    A value without the prefix is already plaintext, and ``NULL`` holds nothing; both are left
    alone. Decrypting needs the same master key the upgrade used, so with none configured this
    refuses outright instead of writing back a value nobody asked for.

    **The column stays wide.** Narrowing it back to what the previous release declared would risk
    truncating a credential — the old model declared 500 and a restored plaintext of 500 fits, but
    a value written into the database by anything other than this application need not respect
    that. A column wider than the model declares is harmless to every reader; a truncated secret is
    not.
    """
    cipher = _cipher()
    table = _credentials()

    with Session(op.get_bind()) as session:
        rows = session.execute(
            sa.select(table.c.id, table.c.api_key).where(table.c.api_key.is_not(None))
        ).fetchall()

        for row_id, api_key in rows:
            if not api_key or not api_key.startswith(PREFIX):
                continue
            session.execute(
                sa.update(table).where(table.c.id == row_id).values(api_key=cipher.decrypt(api_key))
            )

        session.commit()
