"""Tests for ``GET /api/v1/health/services`` — the unauthenticated diagnostics route.

The route has no authentication, which is the whole reason these tests exist: whatever it
publishes is published to anyone who asks. It used to answer with the failed driver's own message
(``str(e)``), and a driver's message can name an internal host, a port, a database or a credential.
Nothing consumed that field — the frontend never called this route — so the detail was cost without
a reader, while the risk was anonymous.

The exceptions below carry a marker that looks the way a real one does, so the assertions have
something to catch rather than testing an absence of nothing.
"""

from __future__ import annotations

import logging

import httpx
import pytest
from sqlalchemy.ext.asyncio import create_async_engine

from storico.api.routes import health

# Shaped like the real thing: a connection string with a credential in it.
_DATABASE_FAILURE = "connection failed: postgresql://storico:sup3r-s3cret@internal-db:5432/storico"
_OLLAMA_FAILURE = "ConnectError: http://internal-ollama:11434/api/tags refused"
_QDRANT_FAILURE = "ConnectError: http://internal-qdrant:6333/health refused"


@pytest.fixture
def failing_services(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make all three probes fail with a message that names something private."""

    def raise_database(*_args, **_kwargs):
        raise RuntimeError(_DATABASE_FAILURE)

    class RefusingClient:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        async def __aenter__(self) -> RefusingClient:
            return self

        async def __aexit__(self, *_exc) -> None:
            return None

        async def get(self, url: str, *_args, **_kwargs) -> httpx.Response:
            if "tags" in url:
                raise httpx.ConnectError(_OLLAMA_FAILURE)
            raise httpx.ConnectError(_QDRANT_FAILURE)

    monkeypatch.setattr(health, "get_engine", raise_database)
    monkeypatch.setattr(health.httpx, "AsyncClient", RefusingClient)


@pytest.mark.asyncio
async def test_a_failing_service_is_reported_without_publishing_the_reason(
    async_client, failing_services, caplog: pytest.LogCaptureFixture
) -> None:
    """The caller learns the service is down. The reason goes to the log."""
    caplog.set_level(logging.WARNING, logger="storico.api.routes.health")

    response = await async_client.get("/api/v1/health/services")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "degraded"
    assert {service["status"] for service in body["services"].values()} == {"error"}

    # The shape of the answer is kept: a caller can still tell which service failed and roughly how.
    assert body["services"]["database"]["error"] == "connection failed"
    assert body["services"]["ollama"]["error"] == "not reachable"
    assert body["services"]["qdrant"]["error"] == "not reachable"
    assert all("latency_ms" in service for service in body["services"].values())

    # And the private detail is nowhere in it — not the credential, not the internal hostnames,
    # not the driver's text.
    published = response.text
    for leak in ("sup3r-s3cret", "internal-db", "internal-ollama", "internal-qdrant"):
        assert leak not in published, f"{leak} reached an unauthenticated caller"
    assert body["services"]["database"]["error"] != _DATABASE_FAILURE

    # The operator still gets all of it: relocating the detail is the fix, discarding it is not.
    assert _DATABASE_FAILURE in caplog.text
    assert "internal-ollama" in caplog.text
    assert "internal-qdrant" in caplog.text


@pytest.mark.asyncio
async def test_the_global_health_route_is_unaffected(async_client) -> None:
    """The required-services route reports a level, and it never carried exception text.

    Deliberately silent on *whether* the database is reachable. An earlier version of this test
    asserted `status == "ok"`, which is a property of the deployment rather than of the route — it
    passed on a machine with a database and failed in CI, where there is none. What the route owes a
    caller is the shape, and a spelled reason instead of the driver's message when a probe fails.
    """
    response = await async_client.get("/api/v1/health")

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"status", "version", "timestamp", "database"}
    assert body["status"] in {"ok", "degraded"}
    if body["database"]["status"] == "error":
        # One of the two reasons the probe spells, never the exception's own text.
        assert body["database"]["error"] in {"connection failed", "connection timed out"}


@pytest.mark.asyncio
async def test_the_database_probe_reports_ok_when_the_query_works(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Covers the probe's own query, with an engine this test controls.

    This is what the route-level assertion above cannot do without depending on the environment: it
    proves the probe executes and reports `ok`, which is what covers the query it runs.
    """
    engine = create_async_engine("sqlite+aiosqlite://")
    monkeypatch.setattr(health, "get_engine", lambda: engine)

    try:
        result = await health._check_database()
    finally:
        await engine.dispose()

    assert result["status"] == "ok"
    assert "error" not in result
