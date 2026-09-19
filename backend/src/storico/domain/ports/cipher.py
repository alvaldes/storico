"""CipherPort — the contract for protecting stored credentials."""

from __future__ import annotations

from abc import ABC, abstractmethod


class CipherPort(ABC):
    """Protects credential values on their way to and from storage.

    The port carries no format, no key material and no error vocabulary of its own: a
    caller hands over plaintext and gets back the value to store, or hands over a stored
    value and gets back plaintext. Deciding what "stored" looks like is the adapter's
    business, and so is recognizing the storage format.
    """

    @abstractmethod
    def encrypt(self, plaintext: str) -> str:
        """Return the value to store for ``plaintext``.

        Raises a subclass of ``CipherError`` when no key is available: the caller has
        nothing safe to store in that case, and returning the plaintext anyway is the
        failure this port exists to make impossible.
        """
        ...

    @abstractmethod
    def decrypt(self, stored: str) -> str:
        """Return the plaintext for ``stored``.

        A value the adapter does not recognize as its own ciphertext is returned
        unchanged. That is the legacy path — rows written before encryption existed hold
        plaintext, and the repository reads every row through this method — and it is
        deliberately the adapter's call rather than the caller's, because the adapter is
        the only layer that owns the storage format.

        Raises a subclass of ``CipherError`` when the value *is* recognized as
        ciphertext but cannot be recovered.
        """
        ...
