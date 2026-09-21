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

import importlib.metadata
import logging
from collections.abc import Iterator

import httpx
import pytest
import sqlalchemy as sa
from sqlalchemy import insert
from sqlalchemy.ext.asyncio import create_async_engine

from storico.api.routes import health
from storico.infrastructure.database import schema_status

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
    assert {name: probe["status"] for name, probe in body["services"].items()} == {
        "database": "error",
        # The schema probe needs the same engine, so it learns nothing for the same reason. It
        # reports `unknown`, which is the point: it is not `ok` when it cannot tell.
        "schema": "unknown",
        "ollama": "error",
        "qdrant": "error",
    }

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
    assert set(body) == {"status", "version", "timestamp", "database", "schema"}
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


# ---------------------------------------------------------------------------------------------
# Schema drift
#
# The probe is the reason these routes were touched at all: on 2026-09-20 production ran code at
# head 0024 against a schema at 0021 for a day, and /api/v1/health answered 200 the whole time.
# The tests below drive a real ``alembic_version`` table through the route — the SQL the probe runs
# is exercised rather than mocked — and hold the route to publishing a status while keeping both
# revisions out of an unauthenticated body.
# ---------------------------------------------------------------------------------------------


def _strings_in(value: object) -> Iterator[str]:
    """Every string anywhere in a decoded JSON body."""
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from _strings_in(item)
    elif isinstance(value, list):
        for item in value:
            yield from _strings_in(item)


def _alembic_version_table() -> sa.Table:
    """Alembic's single-row bookkeeping table, declared rather than hand-written in SQL."""
    return sa.Table(
        "alembic_version",
        sa.MetaData(),
        sa.Column("version_num", sa.String(32), nullable=False),
    )


async def _get_at_revision(
    monkeypatch: pytest.MonkeyPatch,
    client: httpx.AsyncClient,
    path: str,
    revision: str | None,
) -> httpx.Response:
    """GET ``path`` while ``health.get_engine`` answers from a database at ``revision``.

    ``None`` is a database with no ``alembic_version`` at all — nobody has migrated it.
    """
    engine = create_async_engine("sqlite+aiosqlite://")
    if revision is not None:
        table = _alembic_version_table()
        async with engine.begin() as conn:
            await conn.run_sync(table.metadata.create_all)
            if revision:
                await conn.execute(insert(table).values(version_num=revision))

    monkeypatch.setattr(health, "get_engine", lambda: engine)
    try:
        return await client.get(path)
    finally:
        await engine.dispose()


@pytest.fixture(autouse=True)
def _cold_expected_head_cache() -> Iterator[None]:
    """Each test starts and ends with the expected head uncached, so module state stays local."""
    schema_status.clear_expected_head_cache()
    yield
    schema_status.clear_expected_head_cache()


@pytest.mark.asyncio
async def test_health_reports_drift_and_keeps_the_revisions_out_of_the_body(
    async_client, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Drift is visible, liveness is not affected, and no revision reaches the caller."""
    expected = schema_status.get_expected_head()
    assert expected is not None
    drifted = "00000000drift"

    response = await _get_at_revision(monkeypatch, async_client, "/api/v1/health", drifted)

    assert response.status_code == 200, "drift must not turn a liveness probe red"
    body = response.json()
    assert body["schema"]["status"] == "drift"

    # Compared as values rather than as substrings: a timestamp can contain "0000" by accident,
    # and an assertion that trips on that would be noise rather than evidence.
    published = list(_strings_in(body))
    assert drifted not in published
    assert expected not in published
    assert set(body["schema"]) == {"status", "latency_ms"}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "path",
    [
        pytest.param("/api/v1/health", id="liveness"),
        pytest.param("/api/v1/health/ready", id="readiness"),
        pytest.param("/api/v1/health/services", id="diagnostics"),
    ],
)
async def test_no_route_publishes_a_revision(
    async_client, monkeypatch: pytest.MonkeyPatch, path: str
) -> None:
    """The guarantee is per route, not per file, because each one is unauthenticated on its own.

    This exists because a mutation found the hole: the liveness route was covered by the test
    above and the other two were not, so a revision added **only** to the readiness body left the
    whole suite green while the route's own docstring promised it publishes no revision.

    ``_strings_in`` walks the whole document, so this catches a revision nested anywhere in the
    body — under ``services``, under ``database`` or under ``schema`` — rather than only a
    top-level key.
    """
    head = schema_status.get_expected_head()
    assert head is not None
    drifted = "00000000drift"

    response = await _get_at_revision(monkeypatch, async_client, path, drifted)

    published = list(_strings_in(response.json()))
    assert drifted not in published, f"{path} published the database revision"
    assert head not in published, f"{path} published the code's expected revision"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "revision",
    [pytest.param(None, id="table-absent"), pytest.param("", id="table-empty")],
)
async def test_a_schema_that_cannot_be_read_is_unknown_and_never_ok(
    async_client, monkeypatch: pytest.MonkeyPatch, revision: str | None
) -> None:
    """Fail closed: a database nobody has migrated must not read as healthy."""
    response = await _get_at_revision(monkeypatch, async_client, "/api/v1/health", revision)

    body = response.json()
    assert body["schema"]["status"] == "unknown", "an unreadable schema was reported as ok"
    assert body["schema"]["status"] != "ok"


@pytest.mark.asyncio
async def test_readiness_follows_the_schema(async_client, monkeypatch: pytest.MonkeyPatch) -> None:
    """200 only when the code and the schema agree; 503 for drift and for unknown alike.

    Every request here is unauthenticated — the deploy gate runs on the VM with no credentials to
    offer, exactly like its siblings.
    """
    head = schema_status.get_expected_head()
    assert head is not None

    ready = await _get_at_revision(monkeypatch, async_client, "/api/v1/health/ready", head)
    drifted = await _get_at_revision(monkeypatch, async_client, "/api/v1/health/ready", "0001")
    unknown = await _get_at_revision(monkeypatch, async_client, "/api/v1/health/ready", None)

    assert ready.status_code == 200
    assert drifted.status_code == 503
    assert unknown.status_code == 503


@pytest.mark.asyncio
async def test_readiness_answers_the_same_body_whatever_the_status_code(
    async_client, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The deploy gate reads the code; a reader still gets one document, in both cases."""
    head = schema_status.get_expected_head()
    assert head is not None

    ready = await _get_at_revision(monkeypatch, async_client, "/api/v1/health/ready", head)
    not_ready = await _get_at_revision(monkeypatch, async_client, "/api/v1/health/ready", "0001")

    assert ready.status_code == 200 and not_ready.status_code == 503
    assert set(ready.json()) == set(not_ready.json())
    for section in ("database", "schema"):
        assert set(ready.json()[section]) == set(not_ready.json()[section])
    assert ready.json()["status"] == "ok"
    assert not_ready.json()["status"] == "degraded"


@pytest.mark.asyncio
async def test_the_diagnostic_route_reports_the_schema_too(
    async_client, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``/health/services`` is where a full picture is assembled; the schema belongs in it."""
    response = await _get_at_revision(monkeypatch, async_client, "/api/v1/health/services", "0001")

    body = response.json()
    assert body["services"]["schema"]["status"] == "drift"
    assert body["status"] == "degraded"


@pytest.mark.asyncio
async def test_the_revisions_reach_the_log(
    async_client, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """The detail is moved, not discarded: an operator reads both revisions here."""
    caplog.set_level(logging.WARNING, logger="storico.api.routes.health")
    head = schema_status.get_expected_head()
    assert head is not None

    await _get_at_revision(monkeypatch, async_client, "/api/v1/health", "0001")

    assert head in caplog.text
    assert "0001" in caplog.text


# ---------------------------------------------------------------------------------------------
# The version field
# ---------------------------------------------------------------------------------------------


def _installed_version() -> str:
    """The distribution's own version, or a skip when this environment has no install."""
    try:
        return importlib.metadata.version("storico-backend")
    except importlib.metadata.PackageNotFoundError:
        pytest.skip("storico-backend is not installed in this environment")


@pytest.mark.asyncio
async def test_health_reports_the_package_version(
    async_client, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``0.1.0`` was a literal that had been wrong since the package reached 0.3.0."""
    response = await _get_at_revision(monkeypatch, async_client, "/api/v1/health", None)

    version = response.json()["version"]
    assert version == _installed_version()
    assert version != "0.1.0"


@pytest.mark.asyncio
async def test_an_unreadable_package_version_does_not_break_health(
    async_client, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A health endpoint must never raise, so a missing distribution is a value."""

    def missing(*_args, **_kwargs):
        raise importlib.metadata.PackageNotFoundError("storico-backend")

    monkeypatch.setattr(importlib.metadata, "version", missing)

    response = await _get_at_revision(monkeypatch, async_client, "/api/v1/health", None)

    assert response.status_code == 200
    assert response.json()["version"] == "unknown"
