"""Tests for the in-process authenticated-user TTL cache.

The cache backs ``get_current_user`` so repeated requests from the same
user skip the ``find_by_id`` round-trip. These tests pin the behaviour
that other commits (P1.2) rely on:

- entry expires after the TTL (no stale users served for > 30s)
- ``invalidate_user`` removes an entry early (used by PATCH /me/onboarding)
- ``_reset_user_cache`` drops everything (used by the autouse test fixture)
"""

from __future__ import annotations

from unittest.mock import patch

from storico.domain.entities.user import User
from storico.infrastructure.cache import user_cache


def _fake_user(uid: str) -> User:
    return User(name=f"user-{uid}", email=f"{uid}@test.example")


def test_get_cached_user_returns_none_on_miss() -> None:
    """Missing key -> None (cache miss -> caller falls back to repo)."""
    user_cache._reset_user_cache()
    assert user_cache.get_cached_user("does-not-exist") is None


def test_set_then_get_returns_the_cached_user() -> None:
    """Setting a user makes it retrievable immediately."""
    user_cache._reset_user_cache()
    user = _fake_user("u1")
    user_cache.set_cached_user("u1", user)
    assert user_cache.get_cached_user("u1") is user


def test_get_after_invalidate_returns_none() -> None:
    """invalidate_user drops the entry — matches PATCH /me/onboarding flow."""
    user_cache._reset_user_cache()
    user = _fake_user("u2")
    user_cache.set_cached_user("u2", user)
    user_cache.invalidate_user("u2")
    assert user_cache.get_cached_user("u2") is None


def test_invalidate_user_is_idempotent_when_key_absent() -> None:
    """invalidate_user must not raise when the key is not present."""
    user_cache._reset_user_cache()
    user_cache.invalidate_user("never-set")  # must not raise


def test_reset_drops_all_entries() -> None:
    """_reset_user_cache clears everything (matches autouse fixture)."""
    user_cache.set_cached_user("a", _fake_user("a"))
    user_cache.set_cached_user("b", _fake_user("b"))
    user_cache._reset_user_cache()
    assert user_cache.get_cached_user("a") is None
    assert user_cache.get_cached_user("b") is None


def test_entry_expires_after_ttl() -> None:
    """Once the TTL elapses, the entry is gone (and removed lazily)."""
    user_cache._reset_user_cache()
    user = _fake_user("u3")
    user_cache.set_cached_user("u3", user)

    # Fast-forward past the TTL without sleeping — patch monotonic so the
    # cache thinks 31 s have passed on the next read.
    with patch.object(user_cache.time, "monotonic", return_value=10**9 + 31):
        assert user_cache.get_cached_user("u3") is None
    # Entry was removed lazily on read.
    with patch.object(user_cache.time, "monotonic", return_value=10**9 + 31):
        assert user_cache.get_cached_user("u3") is None


def test_expired_entry_then_fresh_set_is_served() -> None:
    """After expiry, a fresh set re-populates the cache."""
    user_cache._reset_user_cache()
    user_cache.set_cached_user("u4", _fake_user("u4"))
    with patch.object(user_cache.time, "monotonic", return_value=10**9 + 31):
        assert user_cache.get_cached_user("u4") is None
    fresh = _fake_user("u4v2")
    user_cache.set_cached_user("u4", fresh)
    assert user_cache.get_cached_user("u4") is fresh


def test_cache_survives_within_ttl_window() -> None:
    """A read inside the TTL window still returns the cached user."""
    user_cache._reset_user_cache()
    user = _fake_user("u5")
    # The clock is frozen for the write *and* the read. Patching only the read
    # made the assertion depend on the machine's uptime: the stored timestamp is
    # whatever the real monotonic() returned, so on a freshly booted CI runner
    # (uptime well under 260s) a read at t=290 looked more than one TTL old and
    # the entry expired. Sibling tests read at 10**9 + 31, which is above any real
    # uptime and therefore immune; this one was not.
    with patch.object(user_cache.time, "monotonic", return_value=10**6):
        user_cache.set_cached_user("u5", user)
    with patch.object(user_cache.time, "monotonic", return_value=10**6 + 29):  # < 30s
        assert user_cache.get_cached_user("u5") is user
