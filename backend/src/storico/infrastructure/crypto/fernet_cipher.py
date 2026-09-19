"""Fernet-based credential cipher."""

from __future__ import annotations

from cryptography.fernet import Fernet, InvalidToken

from storico.domain.entities.exceptions import (
    CredentialUndecryptable,
    EncryptionKeyMissing,
)
from storico.domain.ports import CipherPort

# Marks a stored value as this cipher's ciphertext.
#
# It is a *version* marker rather than an opaque format detail, and it earns that name two
# ways. The read path needs to tell an encrypted value from a legacy plaintext one, and the
# only place that can be known is the value itself — the column is shared by rows written
# before and after encryption existed. And a future key rotation needs somewhere to say
# which generation produced a token. Both questions are answered by the prefix, so neither
# has to be answered by guessing.
#
# Public because revision 0024 has to recognize an already-encrypted row to stay idempotent,
# and re-spelling the marker there would let the two drift apart.
PREFIX = "v1:"


class FernetCipher(CipherPort):
    """Encrypts credentials with a Fernet master key.

    A ``None`` master key is a valid construction and a deliberate one: "not configured" is
    a state the process must be able to *hold* so that the failure surfaces where a secret
    would otherwise be written, with an error the operator can act on. Refusing to build the
    cipher at all would turn a configuration gap into an import-time crash instead.
    """

    def __init__(self, master_key: str | None) -> None:
        # Built once, eagerly: a malformed key is a configuration error, and it must be
        # reported at construction rather than on the first credential that happens to be
        # written — or, worse, read. The raw key is not retained; only the keyed primitive is.
        if master_key is None:
            self._fernet: Fernet | None = None
            return

        try:
            self._fernet = Fernet(master_key.encode("utf-8"))
        except ValueError as e:
            # Re-raised without the offending value: a key must not reach a traceback, a log
            # line or a test failure message. The setting name is what the operator needs.
            raise ValueError(
                "STORICO_ENCRYPTION_KEY is not a valid Fernet key "
                "(expected 32 url-safe base64-encoded bytes)"
            ) from e

    def encrypt(self, plaintext: str) -> str:
        """Return ``v1:``-prefixed ciphertext for ``plaintext``.

        Fernet is non-deterministic, so two calls with the same plaintext produce different
        tokens. Nothing may depend on the stored bytes being stable for a given input — the
        migration and the repository both rely on that being false, which is why the prefix
        rather than a ciphertext comparison is what identifies an already-encrypted value.
        """
        if self._fernet is None:
            raise EncryptionKeyMissing()
        token = self._fernet.encrypt(plaintext.encode("utf-8"))
        return PREFIX + token.decode("ascii")

    def decrypt(self, stored: str) -> str:
        """Return the plaintext for ``stored``.

        Values without the ``v1:`` prefix are returned unchanged: they are legacy plaintext
        written before encryption existed, and rejecting them here would make every such row
        unreadable rather than transparently readable. The cipher owns that decision because
        the cipher owns the format.
        """
        if not stored.startswith(PREFIX):
            return stored

        if self._fernet is None:
            # The value is marked as ours, so there is no plaintext to fall back to: the key
            # that could recover it is the one that is missing.
            raise CredentialUndecryptable()

        token = stored[len(PREFIX) :]
        try:
            return self._fernet.decrypt(token.encode("utf-8")).decode("utf-8")
        except InvalidToken as e:
            # Wrong key, truncated value or tampered ciphertext — indistinguishable by
            # design, and reported as one condition so the message cannot narrow it down.
            raise CredentialUndecryptable() from e
