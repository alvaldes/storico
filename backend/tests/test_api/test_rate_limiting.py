"""Tests for the in-application rate limiter (``api/rate_limit.py``).

The limiter is keyed by the verified JWT subject, falling back to the client
address; the health routes are exempt because the deploy's own readiness gate
polls ``/health/ready`` (``deploy-backend.yml``, the ``curl -sf`` poll loop).
These tests build apps with tight limits so the trip points are a handful of
requests — the suite itself runs under the raised limits set in
``tests/conftest.py`` and must never trip its own limiter.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator, Iterator
from uuid import uuid4

import jwt as pyjwt
import pytest
import pytest_asyncio
import sqlalchemy as sa
from httpx import ASGITransport, AsyncClient
from sqlalchemy import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from starlette.requests import Request

from storico.api.app import create_app
from storico.api.rate_limit import rate_limit_key
from storico.config.settings import Settings, _reset_settings_cache
from storico.infrastructure.database import schema_status
from storico.infrastructure.database.session import get_session
from tests.conftest import make_jwt_headers

# A wrong-secret that satisfies HMAC's minimum key length so PyJWT does not
# warn — the point of the forged tokens is a signature that does not verify.
_WRONG_SECRET = "wrong-secret-that-is-long-enough-for-hs256"


def _request_with(
    headers: dict[str, str], client: tuple[str, int] = ("203.0.113.9", 5555)
) -> Request:
    """A bare Request over a scope carrying exactly what the key function reads."""
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "headers": [(name.lower().encode(), value.encode()) for name, value in headers.items()],
        "query_string": b"",
        "client": client,
    }
    return Request(scope)


# Tight limits: a handful of requests must be enough to trip each tier, so the
# tests prove the tier table, not the production numbers.
TIGHT_LIMITS = {
    "STORICO_RATE_LIMIT_READS_PER_MINUTE": "3",
    "STORICO_RATE_LIMIT_WRITES_PER_MINUTE": "60",
    "STORICO_RATE_LIMIT_EXTRACTION_PER_MINUTE": "2",
    "STORICO_RATE_LIMIT_IMPORT_PER_MINUTE": "5",
    "STORICO_RATE_LIMIT_PROBES_PER_MINUTE": "10",
}


@pytest.fixture
def tight_app() -> Iterator[object]:
    """Build an app with tight limits, restoring the suite-wide env afterwards.

    The suite-wide limits live in ``os.environ`` (set by ``tests/conftest.py``);
    this fixture overrides them for one app build and restores them before the
    settings cache is rebuilt, so no other test ever sees the tight numbers.
    """
    saved = {name: os.environ.get(name) for name in TIGHT_LIMITS}
    os.environ.update(TIGHT_LIMITS)
    _reset_settings_cache()
    try:
        yield create_app()
    finally:
        for name, value in saved.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value
        _reset_settings_cache()


@pytest_asyncio.fixture
async def tight_client(tight_app, test_engine) -> AsyncIterator[AsyncClient]:
    """Client against the tight-limit app, with the same SQLite override the
    suite's ``async_client`` uses, so authenticated requests run end to end."""
    factory = async_sessionmaker(bind=test_engine, class_=AsyncSession, expire_on_commit=False)

    async def override_get_session():
        async with factory() as session:
            yield session

    tight_app.dependency_overrides[get_session] = override_get_session
    transport = ASGITransport(app=tight_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    tight_app.dependency_overrides.clear()


# ---------------------------------------------------------------------------------------------
# The limit trips, and the body is the canonical envelope
# ---------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_read_limit_trips_with_canonical_envelope(tight_client: AsyncClient) -> None:
    """The 4th of 4 requests against a 3/min read bucket answers 429 with the
    canonical ``detail`` + ``error_code`` envelope, not slowapi's default body."""
    codes = []
    for _ in range(4):
        response = await tight_client.get("/api/v1/users/me")
        codes.append(response.status_code)

    assert codes[:3] == [401, 401, 401], "pre-limit requests pass the limiter through"
    assert codes[3] == 429

    body = (await tight_client.get("/api/v1/users/me")).json()
    assert set(body) == {"detail", "error_code"}
    assert body["error_code"] == "RATE_LIMIT_EXCEEDED"
    assert isinstance(body["detail"], str) and body["detail"]


# ---------------------------------------------------------------------------------------------
# Health is exempt — mandatory, not prudence
# ---------------------------------------------------------------------------------------------


def _alembic_version_table() -> sa.Table:
    """Alembic's single-row bookkeeping table (same declaration the drift tests use)."""
    return sa.Table(
        "alembic_version",
        sa.MetaData(),
        sa.Column("version_num", sa.String(32), nullable=False),
    )


@pytest.fixture(autouse=True)
def _cold_expected_head_cache() -> Iterator[None]:
    """Keep the expected-head cache local to each test, as the drift tests do."""
    schema_status.clear_expected_head_cache()
    yield
    schema_status.clear_expected_head_cache()


@pytest.mark.asyncio
async def test_health_endpoints_are_exempt(
    tight_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Hammering all three health routes far past the read limit still answers 200.

    ``/health/ready`` needs a database whose revision equals the code's head to
    answer 200 at all, so this test gives it one — a real SQLite engine with a
    real ``alembic_version`` row, the same shape the drift tests drive.
    """
    engine = create_async_engine("sqlite+aiosqlite://")
    table = _alembic_version_table()
    async with engine.begin() as conn:
        await conn.run_sync(table.metadata.create_all)
        await conn.execute(insert(table).values(version_num=schema_status.get_expected_head()))

    from storico.api.routes import health

    monkeypatch.setattr(health, "get_engine", lambda: engine)
    try:
        for _ in range(10):
            assert (await tight_client.get("/api/v1/health")).status_code == 200
            assert (await tight_client.get("/api/v1/health/ready")).status_code == 200
        for _ in range(3):
            assert (await tight_client.get("/api/v1/health/services")).status_code == 200
    finally:
        await engine.dispose()


# ---------------------------------------------------------------------------------------------
# Anti-bypass: invalid tokens must not mint fresh buckets
# ---------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_invalid_tokens_share_one_address_bucket(tight_client: AsyncClient) -> None:
    """Many requests with different *invalid* tokens from one address exhaust the
    single address bucket — a token that does not verify cannot mint a new one."""
    codes = []
    for _ in range(6):
        forged = pyjwt.encode({"sub": str(uuid4())}, _WRONG_SECRET, algorithm="HS256")
        response = await tight_client.get(
            "/api/v1/users/me", headers={"Authorization": f"Bearer {forged}"}
        )
        codes.append(response.status_code)

    assert codes[0] == 401, "the first forged request passes the limiter, fails auth"
    assert codes[3:] == [429, 429, 429], "the shared address bucket trips"


@pytest.mark.asyncio
async def test_verified_token_has_its_own_bucket_after_address_exhaustion(
    tight_client: AsyncClient, authed_user
) -> None:
    """A valid token keys its own bucket: after the address bucket is spent, an
    authenticated request still succeeds."""
    for _ in range(5):
        forged = pyjwt.encode({"sub": str(uuid4())}, _WRONG_SECRET, algorithm="HS256")
        await tight_client.get("/api/v1/users/me", headers={"Authorization": f"Bearer {forged}"})

    response = await tight_client.get(
        "/api/v1/users/me", headers=make_jwt_headers(str(authed_user.id))
    )
    assert response.status_code == 200


# ---------------------------------------------------------------------------------------------
# A stricter tier, end to end
# ---------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_extraction_tier_trips_before_the_read_limit(
    tight_client: AsyncClient, authed_user, seed_workspace
) -> None:
    """With extraction at 2/min and reads at 3/min, the extraction bucket is the
    one that trips: a 3rd request answers 429 even though the read tier allows 3.

    The first two requests reach the route and answer 400 (the seeded workspace
    has no LLM config), which also proves the limiter counts the attempts it
    lets through rather than only the failures.
    """
    seeded = await seed_workspace()
    url = f"/api/v1/workspaces/{seeded.workspace_id}/extract/"
    codes = []
    for _ in range(3):
        response = await tight_client.post(
            url,
            headers=make_jwt_headers(str(authed_user.id)),
            json={"user_story_id": str(seeded.story_id)},
        )
        codes.append(response.status_code)

    assert codes[:2] == [400, 400]
    assert codes[2] == 429
    assert (
        await tight_client.post(
            url,
            headers=make_jwt_headers(str(authed_user.id)),
            json={"user_story_id": str(seeded.story_id)},
        )
    ).json()["error_code"] == "RATE_LIMIT_EXCEEDED"


# ---------------------------------------------------------------------------------------------
# The key function: verified subject, else address
# ---------------------------------------------------------------------------------------------


def test_verified_token_keys_by_subject() -> None:
    token = pyjwt.encode({"sub": "user-123"}, Settings.load().auth_jwt_secret, algorithm="HS256")
    key = rate_limit_key(_request_with({"Authorization": f"Bearer {token}"}))
    assert key == "user:user-123"


def test_unverifiable_tokens_key_by_address() -> None:
    """Garbage, wrong-secret, expired, subject-less and non-Bearer requests all
    share the address bucket — none of them mints a per-identity bucket."""
    secret = Settings.load().auth_jwt_secret
    expired = pyjwt.encode({"sub": "user-123", "exp": 1_000_000_000}, secret, algorithm="HS256")
    wrong_secret = pyjwt.encode({"sub": "user-123"}, _WRONG_SECRET, algorithm="HS256")
    subjectless = pyjwt.encode({"role": "member"}, secret, algorithm="HS256")
    headers_list = [
        {"Authorization": "Bearer not-a-jwt"},
        {"Authorization": f"Bearer {wrong_secret}"},
        {"Authorization": f"Bearer {expired}"},
        {"Authorization": f"Bearer {subjectless}"},
        {"Authorization": "Basic dXNlcjpwYXNz"},
        {},
    ]
    for headers in headers_list:
        assert rate_limit_key(_request_with(headers)) == "ip:203.0.113.9", headers


def test_address_without_client_falls_back_to_unknown() -> None:
    request = _request_with({})
    request.scope.pop("client")
    assert rate_limit_key(request) == "ip:unknown"


# ---------------------------------------------------------------------------------------------
# The suite must not trip its own limiter
# ---------------------------------------------------------------------------------------------


def test_suite_settings_raise_the_limits() -> None:
    """The conftest env raise is what keeps 1305 tests from tripping the read
    bucket; assert it so the guard cannot silently rot."""
    settings = Settings.load()
    assert settings.rate_limit_reads_per_minute == 1_000_000
    assert settings.rate_limit_writes_per_minute == 1_000_000
    assert settings.rate_limit_extraction_per_minute == 1_000_000
    assert settings.rate_limit_import_per_minute == 1_000_000
    assert settings.rate_limit_probes_per_minute == 1_000_000
