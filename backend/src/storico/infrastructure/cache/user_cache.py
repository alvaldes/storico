"""In-process per-user cache for the authenticated user.

Used by ``get_current_user`` to skip the ``find_by_id`` round-trip when
the same user has authenticated recently. The cache is process-local:
it is NOT shared between worker processes, so two uvicorn workers each
keep their own cache — which is fine because the cache is purely a
perf layer; correctness always falls back to the database.

Keyed by ``user_id`` (UUID string from the JWT ``sub`` claim). Entries
live for ``_TTL_SECONDS`` (30s) — a balance between saving the
round-trip on repeated requests and not serving stale data for too
long.

Why a hand-rolled dict instead of ``cachetools.TTLCache``?
``cachetools`` is not a project dependency (see backend/pyproject.toml)
and the plan says no new deps without need. A 30-line TTL dict that
shares the same surface (get/set/invalidate/reset) is enough here.
"""

from __future__ import annotations

import time
from threading import Lock
from typing import TYPE_CHECKING
from uuid import UUID

if TYPE_CHECKING:
    from storico.domain.entities.user import User

_TTL_SECONDS: float = 30.0
_CACHE: dict[str, tuple[float, User]] = {}
_LOCK = Lock()


def get_cached_user(user_id: UUID | str) -> User | None:
    """Return the user cached for ``user_id`` if it is still fresh.

    Returns ``None`` if the entry does not exist or has expired. An
    expired entry is removed lazily on read so the cache does not grow
    unbounded by stale keys.
    """
    key = str(user_id)
    with _LOCK:
        entry = _CACHE.get(key)
        if entry is None:
            return None
        ts, user = entry
        if (time.monotonic() - ts) > _TTL_SECONDS:
            _CACHE.pop(key, None)
            return None
        return user


def set_cached_user(user_id: UUID | str, user: User) -> None:
    """Store ``user`` keyed by ``user_id`` with a fresh TTL timestamp."""
    key = str(user_id)
    with _LOCK:
        _CACHE[key] = (time.monotonic(), user)


def invalidate_user(user_id: UUID | str) -> None:
    """Remove the cached user for ``user_id``, if present.

    Idempotent — does not raise if the key is absent. Must be called by
    endpoints that mutate the authenticated user (e.g. PATCH /users/me/
    onboarding) so subsequent ``get_current_user`` calls re-read from
    the DB instead of returning a stale snapshot.
    """
    key = str(user_id)
    with _LOCK:
        _CACHE.pop(key, None)


def _reset_user_cache() -> None:
    """Wipe the whole cache — for tests only.

    Production code should prefer ``invalidate_user`` for a single user.
    Tests call this in an ``autouse`` fixture to prevent cross-test
    pollution: many tests authenticate as the same ``authed_user`` and
    a cached entry from one test must not satisfy another's intent.
    """
    with _LOCK:
        _CACHE.clear()
