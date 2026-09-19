"""Tests for the Fernet credential cipher.

The cipher is the only layer that knows what a stored credential looks like, so these tests
pin the format contract that the repository, revision 0024 and a future key rotation all read:
the ``v1:`` marker identifies ciphertext, a value without it is legacy plaintext, and a
missing key refuses to write rather than silently degrading to plaintext.
"""

from __future__ import annotations

import pytest
from cryptography.fernet import Fernet

from storico.domain.entities.exceptions import (
    CredentialUndecryptable,
    EncryptionKeyMissing,
)
from storico.infrastructure.crypto import FernetCipher

_PLAINTEXT = "sk-live-0123456789abcdef"


def _key() -> str:
    """A fresh valid Fernet key per call, so no two tests share key material."""
    return Fernet.generate_key().decode("ascii")


def test_a_round_trip_returns_the_original_plaintext() -> None:
    """The only property the repository actually depends on."""
    cipher = FernetCipher(_key())

    assert cipher.decrypt(cipher.encrypt(_PLAINTEXT)) == _PLAINTEXT


def test_a_value_without_the_prefix_comes_back_unchanged() -> None:
    """A row written before encryption existed holds plaintext, and stays readable."""
    cipher = FernetCipher(_key())

    assert cipher.decrypt(_PLAINTEXT) == _PLAINTEXT


def test_ciphertext_hides_the_plaintext_behind_the_prefix() -> None:
    """The prefix is what later tells ciphertext from legacy plaintext, so it must be there."""
    cipher = FernetCipher(_key())

    stored = cipher.encrypt(_PLAINTEXT)

    assert stored.startswith("v1:")
    assert _PLAINTEXT not in stored


def test_without_a_key_writing_is_refused_and_legacy_reads_still_work() -> None:
    """Absent key: refuse to encrypt, refuse to fake a decryption, keep reading plaintext."""
    cipher = FernetCipher(None)

    with pytest.raises(EncryptionKeyMissing):
        cipher.encrypt(_PLAINTEXT)

    with pytest.raises(CredentialUndecryptable):
        cipher.decrypt("v1:whatever-was-stored")

    assert cipher.decrypt(_PLAINTEXT) == _PLAINTEXT


def test_another_key_cannot_decrypt_and_no_secret_reaches_the_message() -> None:
    """A credential and a key must not survive into an exception message."""
    stored = FernetCipher(_key()).encrypt(_PLAINTEXT)
    other_key = _key()

    with pytest.raises(CredentialUndecryptable) as caught:
        FernetCipher(other_key).decrypt(stored)

    message = str(caught.value)
    assert _PLAINTEXT not in message
    assert other_key not in message
    assert stored not in message


def test_a_corrupted_ciphertext_under_a_valid_key_is_undecryptable() -> None:
    """Truncation and tampering are reported as one condition, not as an unhandled crash."""
    cipher = FernetCipher(_key())

    with pytest.raises(CredentialUndecryptable):
        cipher.decrypt(cipher.encrypt(_PLAINTEXT)[:-4])


def test_a_malformed_key_fails_at_construction() -> None:
    """A bad key is a configuration error, and it must surface before the first credential."""
    malformed = "definitely-not-a-fernet-key"

    with pytest.raises(ValueError) as caught:
        FernetCipher(malformed)

    message = str(caught.value)
    assert "STORICO_ENCRYPTION_KEY" in message
    assert malformed not in message


def test_two_encryptions_of_the_same_plaintext_differ() -> None:
    """Fernet is non-deterministic — which is why the prefix, not the bytes, marks ciphertext.

    The migration's idempotency depends on this being false for any comparison of stored
    values, so it is pinned here rather than assumed.
    """
    cipher = FernetCipher(_key())

    assert cipher.encrypt(_PLAINTEXT) != cipher.encrypt(_PLAINTEXT)
