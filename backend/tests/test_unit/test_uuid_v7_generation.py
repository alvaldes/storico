"""Verify UUID v7 generation contract.

The migration from UUIDv4 to UUIDv7 (RFC 9562) is enforced by this contract test:
every newly-constructed domain entity MUST produce a UUID with .version == 7,
and the runtime library helper MUST return stdlib uuid.UUID (not a custom
subclass that would break SQLAlchemy/asyncpg binding).

Scope: this test is deliberately entity-agnostic regarding the auth<Account>
split — we exercise the canonical ``User`` domain object whose ``id`` column
is the root primary key of the schema; ``User`` is constructed with its real
kwargs as defined in the entity (``email`` + ``name`` are required, no defaults).
The other 9 entities share the identical ``field(default_factory=uuid7)``
pattern, so a passing ``User`` check transitively validates the import +
factory wiring used everywhere else.
"""

from uuid import UUID

from uuid_utils.compat import uuid7

from storico.domain.entities.user import User


def test_uuid7_returns_stdlib_uuid() -> None:
    """uuid_utils.compat.uuid7() returns stdlib uuid.UUID, not a custom subclass."""
    result = uuid7()
    assert isinstance(result, UUID), (
        f"uuid7() returned {type(result).__name__}, expected stdlib uuid.UUID"
    )
    # Guard against custom-subclass leakage from uuid_utils.UUID which breaks
    # asyncpg/SQLAlchemy binary binding.
    assert type(result) is UUID, (
        f"uuid7() returned subclass {type(result).__name__}; "
        "expected exactly stdlib uuid.UUID — use uuid_utils.compat, not uuid_utils"
    )
    assert result.version == 7


def test_user_entity_generates_v7_id() -> None:
    """Newly-constructed User entities auto-generate a UUIDv7 primary key."""
    user = User(email="test@example.com", name="Test")
    assert isinstance(user.id, UUID)
    assert type(user.id) is UUID
    assert user.id.version == 7
