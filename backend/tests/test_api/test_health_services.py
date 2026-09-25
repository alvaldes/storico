"""Tests for ``GET /api/v1/health/services`` — the unauthenticated diagnostics route.

The route has no authentication, which is the whole reason these tests exist: whatever it
publishes is published to anyone who asks. It used to answer with the failed driver's own message
(``str(e)``), and a driver's message can name an internal host, a port, a database or a credential.
Nothing consumed that field at the time — the frontend did not call this route then — so the detail
was cost without a reader, while the risk was anonymous. The frontend's `/status` page reads this
route now (it shows a row per service), which makes the spelled-out reason more load-bearing, not
less.

The exceptions below carry a marker that looks the way a real one does, so the assertions have
something to catch rather than testing an absence of nothing.
"""

from __future__ import annotations

import importlib.metadata
import json
import logging
from collections.abc import Iterator
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
import sqlalchemy as sa
from sqlalchemy import insert
from sqlalchemy.ext.asyncio import create_async_engine

from storico.api.routes import health
from storico.config.settings import Settings
from storico.infrastructure.database import schema_status
from storico.infrastructure.vector import embedding_model_for, get_embedding_port

# Shaped like the real thing: a connection string with a credential in it.
_DATABASE_FAILURE = "connection failed: postgresql://storico:sup3r-s3cret@internal-db:5432/storico"
_OLLAMA_FAILURE = "ConnectError: http://internal-ollama:11434/api/tags refused"
_QDRANT_FAILURE = "ConnectError: http://internal-qdrant:6333/health refused"


@pytest.fixture
def failing_services(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make all probes fail with a message that names something private.

    The embeddings probe is pinned to ``not configured`` (a raised ``ValueError``) so the
    route-level status assertions stay deterministic: without this, the probe would depend
    on whatever embedding provider the developer's environment has configured.
    """

    def raise_database(*_args, **_kwargs):
        raise RuntimeError(_DATABASE_FAILURE)

    def raise_not_configured(*_args, **_kwargs):
        raise ValueError("no embedding provider is configured in this test")

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
    monkeypatch.setattr(health, "get_embedding_port", raise_not_configured)


@pytest.fixture
def probe_outcomes(monkeypatch: pytest.MonkeyPatch):
    """Patch the five probes with spelled, deterministic results.

    The route-level classification must not depend on the deployment it runs on: a real
    database would make "the required probes are ok" a property of the machine rather
    than of the route — the mistake an earlier version of
    ``test_the_global_health_route_is_unaffected`` made and CI caught. The probes
    themselves are covered by their own tests below; here only the classification
    matters, so each probe is replaced by a result shaped like the real one, with the
    same spelled reasons the probes publish.
    """

    spelled_errors = {
        "database": "connection failed",
        "ollama": "not reachable",
        "qdrant": "not reachable",
        "embeddings": "not reachable",
    }

    def _install(failing: set[str]) -> None:
        def result(name: str) -> dict:
            if name not in failing:
                return {"status": "ok", "latency_ms": 0.1}
            if name == "schema":
                # The schema probe never spells "error": its failure is `unknown` (or
                # `drift`), which already is not-ok. Shaped like the real probe.
                return {"status": "unknown", "latency_ms": 0.1}
            return {"status": "error", "latency_ms": 0.1, "error": spelled_errors[name]}

        for name in ("database", "schema", "ollama", "qdrant", "embeddings"):

            async def fake_probe(_name: str = name) -> dict:
                return result(_name)

            monkeypatch.setattr(health, f"_check_{name}", fake_probe)

    return _install


@pytest.fixture(autouse=True)
def _cold_embeddings_probe_cache() -> Iterator[None]:
    """Each test starts and ends with the embeddings probe cache empty.

    The probe caches its result for 60 seconds at module level to protect the billable
    provider; without this fixture one test's result would leak into the next.
    """
    health._embeddings_probe_cache = None
    yield
    health._embeddings_probe_cache = None


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
        "embeddings": "error",
    }

    # The shape of the answer is kept: a caller can still tell which service failed and roughly how.
    assert body["services"]["database"]["error"] == "connection failed"
    assert body["services"]["ollama"]["error"] == "not reachable"
    assert body["services"]["qdrant"]["error"] == "not reachable"
    assert body["services"]["embeddings"]["error"] == "not configured"
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
# The required/optional classification
#
# The route folds five probes into one top-level `status`, and until now an optional
# integration counted the same as a required dependency: production runs no Ollama on
# purpose, so it answered `status: degraded` forever while everything that matters was
# ok — a permanent false alarm for anyone alerting on `status != ok` (finding F2). The
# tests below pin the new contract: `scope` on every probe, `status` computed from the
# required probes only, and a classification that covers the published probes exactly.
# ---------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_an_optional_probe_failing_does_not_degrade_the_status(
    async_client, probe_outcomes
) -> None:
    """The regression this change exists for, asserted on the payload itself.

    Every required probe ok and every optional probe failing must still answer
    `status: ok`: ollama, qdrant and embeddings are integrations a workspace may never
    use, and their failure degrades a feature, not the deployment. This is exactly the
    shape production answers with today, which read as a permanent "degraded".
    """
    probe_outcomes({"ollama", "qdrant", "embeddings"})

    response = await async_client.get("/api/v1/health/services")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    # The failures are still published, per probe: the route reports them, it just no
    # longer lets them paint the whole deployment.
    assert body["services"]["ollama"]["status"] == "error"
    assert body["services"]["qdrant"]["status"] == "error"
    assert body["services"]["embeddings"]["status"] == "error"
    assert body["services"]["database"]["status"] == "ok"
    assert body["services"]["schema"]["status"] == "ok"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "failing",
    [
        pytest.param({"database"}, id="database"),
        pytest.param({"schema"}, id="schema"),
    ],
)
async def test_a_required_probe_failing_degrades_the_status(
    async_client, probe_outcomes, failing: set[str]
) -> None:
    """`degraded` keeps its meaning: a required probe is not ok.

    The two required probes are pinned separately because they fail differently — the
    database spells `error`, the schema spells `unknown` — and both must degrade the
    top-level status.
    """
    probe_outcomes(failing)

    response = await async_client.get("/api/v1/health/services")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "degraded"
    # The optional probes are healthy here, so `degraded` can only come from the
    # required one that is failing.
    assert body["services"]["ollama"]["status"] == "ok"
    assert body["services"]["qdrant"]["status"] == "ok"
    assert body["services"]["embeddings"]["status"] == "ok"


@pytest.mark.asyncio
async def test_every_probe_declares_its_scope(async_client, probe_outcomes) -> None:
    """The payload is self-describing: each probe carries its own classification.

    The explicit mapping below is the contract a consumer reads; the membership check
    afterwards ties it to the backend constants, so the published scope and the tuple
    that drives the top-level status cannot drift apart.
    """
    probe_outcomes(set())

    response = await async_client.get("/api/v1/health/services")

    body = response.json()
    assert {name: probe["scope"] for name, probe in body["services"].items()} == {
        "database": "required",
        "schema": "required",
        "ollama": "optional",
        "qdrant": "optional",
        "embeddings": "optional",
    }
    for name, probe in body["services"].items():
        if name in health.REQUIRED_PROBES:
            assert probe["scope"] == "required"
        else:
            assert probe["scope"] == "optional"


@pytest.mark.asyncio
async def test_the_classification_covers_the_published_probes_exactly(
    async_client, probe_outcomes
) -> None:
    """A future probe that lands in neither tuple would silently read as optional.

    The union of the two tuples must equal the probes the route actually publishes, and
    the tuples must not overlap: otherwise the next probe added to `services` gets no
    classification, and its failure either degrades the deployment unannounced or is
    silently forgiven.
    """
    probe_outcomes(set())

    response = await async_client.get("/api/v1/health/services")

    published = set(response.json()["services"])
    required = set(health.REQUIRED_PROBES)
    optional = set(health.OPTIONAL_PROBES)
    assert required | optional == published
    assert not required & optional


@pytest.mark.asyncio
async def test_the_liveness_and_readiness_routes_publish_no_scope(
    async_client, probe_outcomes
) -> None:
    """`scope` belongs on the diagnostics probes, not on the top-level sections.

    `/health` and `/health/ready` publish `database` and `schema` at the top level,
    where everything they carry is required by construction: a `scope` there would say
    nothing and would only widen a contract two other consumers already read.
    """
    probe_outcomes(set())

    for path in ("/api/v1/health", "/api/v1/health/ready"):
        body = (await async_client.get(path)).json()
        assert "scope" not in body["database"], f"{path} grew a scope on database"
        assert "scope" not in body["schema"], f"{path} grew a scope on schema"


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


# ---------------------------------------------------------------------------------------------
# The Qdrant and embeddings probes
#
# The Qdrant probe used to request ``/health`` without the api-key header. Measured against
# Qdrant Cloud: auth is evaluated before routing, so the keyless request got a 403 on a
# perfectly healthy cluster — and even with a key, ``/health`` is a 404 there. ``/healthz`` is
# the liveness route that exists everywhere. The embeddings probe is new; it performs a real,
# billable call against the configured provider on an unauthenticated route, so its result is
# cached in-process for 60 seconds.
# ---------------------------------------------------------------------------------------------


def _fake_settings(**values: object) -> type:
    """A ``Settings`` stand-in whose ``load()`` returns the given namespace.

    Seeded from a **real** ``Settings`` (with ``_env_file=None`` so the repository's
    ``.env`` cannot leak in) and then overridden, so field names and defaults are real.

    The earlier version defined only the attributes the probes read, which let a test
    write a combination production can never produce — ``embedding_provider="google"``
    beside ``embedding_model="gemini-embedding-001"`` — and then assert a model the probe
    would never report. ``STORICO_EMBEDDING_MODEL`` is the *Ollama* model; the cloud
    providers read their own field. Seeding from the real class is what makes that fake
    unwritable.
    """
    resolved = Settings(_env_file=None).model_dump()
    resolved.update(values)

    class _Settings:
        @staticmethod
        def load() -> SimpleNamespace:
            return SimpleNamespace(**resolved)

    return _Settings


class _RecordingClient:
    """httpx.AsyncClient stand-in that records the URL and headers it was given."""

    captured: dict = {}

    def __init__(self, *_args, **_kwargs) -> None:
        pass

    async def __aenter__(self) -> _RecordingClient:
        return self

    async def __aexit__(self, *_exc) -> None:
        return None

    async def get(self, url: str, *, headers: dict | None = None, **_kwargs) -> httpx.Response:
        _RecordingClient.captured = {"url": url, "headers": headers}
        response = MagicMock()
        response.raise_for_status = lambda: None
        return response


def _fake_embedding_port(vector: list[float] | Exception, dimensions: int = 768) -> MagicMock:
    """An EmbeddingPort stand-in with a fixed ``embed`` result and dimensions."""
    port = MagicMock()
    port.dimensions = dimensions
    port.embed = (
        AsyncMock(return_value=vector)
        if not isinstance(vector, Exception)
        else AsyncMock(side_effect=vector)
    )
    return port


@pytest.mark.asyncio
async def test_the_qdrant_probe_requests_healthz_and_sends_the_api_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The probe asks ``/healthz`` and authenticates with the ``api-key`` header.

    Pins both halves of the fix: the route Qdrant Cloud actually serves, and the header
    Qdrant expects — without which auth is evaluated before routing and a healthy cluster
    answers 403.
    """
    monkeypatch.setattr(health.httpx, "AsyncClient", _RecordingClient)
    monkeypatch.setattr(
        health,
        "Settings",
        _fake_settings(qdrant_url="http://qdrant:6333", qdrant_api_key="s3cret-key"),
    )

    result = await health._check_qdrant()

    assert result["status"] == "ok"
    assert _RecordingClient.captured["url"].endswith("/healthz")
    assert _RecordingClient.captured["headers"] == {"api-key": "s3cret-key"}


@pytest.mark.asyncio
async def test_the_qdrant_probe_sends_no_api_key_header_when_none_is_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A keyless deployment must not send an empty ``api-key`` header."""
    monkeypatch.setattr(health.httpx, "AsyncClient", _RecordingClient)
    monkeypatch.setattr(
        health,
        "Settings",
        _fake_settings(qdrant_url="http://localhost:6333", qdrant_api_key=None),
    )

    result = await health._check_qdrant()

    assert result["status"] == "ok"
    assert _RecordingClient.captured["url"].endswith("/healthz")
    assert _RecordingClient.captured["headers"] == {}


@pytest.mark.asyncio
async def test_the_qdrant_probe_error_keeps_the_key_and_url_out_of_the_body(
    async_client, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When the probe fails, neither the api key nor the URL reaches the caller.

    The probe now authenticates, which means the failure body is one step closer to the
    credential than it used to be — so the route's no-leak rule is pinned with the key
    itself planted in the settings.
    """

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
            raise httpx.ConnectError(f"ConnectError: {url} refused")

    monkeypatch.setattr(health, "get_engine", raise_database)
    monkeypatch.setattr(health.httpx, "AsyncClient", RefusingClient)
    monkeypatch.setattr(
        health,
        "Settings",
        _fake_settings(qdrant_url="http://internal-qdrant:6333", qdrant_api_key="sup3r-s3cret"),
    )
    monkeypatch.setattr(health, "get_embedding_port", lambda _s: _fake_embedding_port([]))

    response = await async_client.get("/api/v1/health/services")

    assert response.status_code == 200
    assert response.json()["services"]["qdrant"]["error"] == "not reachable"
    assert "sup3r-s3cret" not in response.text
    assert "internal-qdrant" not in response.text


@pytest.mark.asyncio
async def test_the_embeddings_probe_reports_provider_model_dimensions_and_length(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A working probe reports who was asked, what for, and what came back."""
    port = _fake_embedding_port([0.1] * 768, dimensions=768)
    monkeypatch.setattr(
        health,
        "Settings",
        _fake_settings(embedding_provider="google", google_embedding_model="gemini-embedding-001"),
    )
    monkeypatch.setattr(health, "get_embedding_port", lambda _settings: port)

    result = await health._check_embeddings()

    assert result["status"] == "ok"
    assert result["provider"] == "google"
    assert result["model"] == "gemini-embedding-001"
    assert result["dimensions"] == 768
    assert result["vector_length"] == 768
    assert "latency_ms" in result


def _adapter_model(port: object) -> object:
    """The model an embedding adapter will actually call with, across the three shapes.

    ``OllamaEmbeddingAdapter`` wraps its model inside ``EmbeddingService``; the cloud
    adapters hold it directly. Read defensively rather than by reaching into one shape.
    """
    direct = getattr(port, "_model", None)
    if direct is not None:
        return direct
    return getattr(getattr(port, "_service", None), "_model", None)


@pytest.mark.parametrize(
    ("provider", "expected_model"),
    [
        # Ollama is the one provider whose model comes from the generic field, so the
        # deliberately-wrong value is the *correct* answer here and proves the other two
        # do not read it.
        ("ollama", "not-the-real-model"),
        ("google", "gemini-embedding-001"),
        ("openai", "text-embedding-3-small"),
    ],
)
def test_the_reported_model_is_the_one_the_adapter_actually_uses(
    provider: str, expected_model: str
) -> None:
    """The probe must name the model the port was built with, for every provider.

    ``STORICO_EMBEDDING_MODEL`` is the *Ollama* model only: the cloud providers read
    ``google_embedding_model`` and ``openai_embedding_model``. Reporting the generic field
    named ``nomic-embed-text`` for a Google or OpenAI deployment — a diagnostics field that
    lied about the deployment it describes, which is the defect this probe exists to
    remove. Deliberately set to a value no provider but Ollama reads, so a report that
    falls back to it is caught instead of accidentally right.

    Real settings and real adapters, no fakes: this is the pin that a fake could not give,
    because a fake is free to describe a configuration production cannot produce.
    """
    settings = Settings(
        _env_file=None,
        embedding_provider=provider,
        embedding_model="not-the-real-model",
        google_embedding_model="gemini-embedding-001",
        openai_embedding_model="text-embedding-3-small",
        google_api_key="test-key",
        openai_api_key="test-key",
    )

    assert embedding_model_for(settings) == expected_model
    assert _adapter_model(get_embedding_port(settings)) == expected_model


@pytest.mark.asyncio
async def test_a_google_probe_reports_the_google_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """End to end through the route helper, with the fields production actually sets.

    The provider-specific field is the only one set, which is how a real Google deployment
    looks. The earlier test set the generic ``embedding_model`` and therefore asserted a
    model the probe would never report.
    """
    port = _fake_embedding_port([0.1] * 768, dimensions=768)
    monkeypatch.setattr(
        health,
        "Settings",
        _fake_settings(embedding_provider="google", google_embedding_model="gemini-embedding-001"),
    )
    monkeypatch.setattr(health, "get_embedding_port", lambda _settings: port)

    result = await health._check_embeddings()

    assert result["status"] == "ok"
    assert result["model"] == "gemini-embedding-001"


@pytest.mark.asyncio
async def test_the_embeddings_probe_reports_an_empty_vector_as_not_reachable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An empty vector is the embedding service's degraded answer — spelled, not raised."""
    port = _fake_embedding_port([])
    monkeypatch.setattr(
        health,
        "Settings",
        _fake_settings(embedding_provider="ollama", embedding_model="nomic-embed-text"),
    )
    monkeypatch.setattr(health, "get_embedding_port", lambda _settings: port)

    result = await health._check_embeddings()

    assert result["status"] == "error"
    assert result["error"] == "not reachable"
    assert "latency_ms" in result


@pytest.mark.asyncio
async def test_the_embeddings_probe_never_raises_and_never_publishes_the_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An unexpected provider failure degrades to a spelled reason, never a 500.

    The marker below is shaped like real exception text (it names a private host); if the
    route ever forwards ``str(e)``, this test catches it.
    """
    port = _fake_embedding_port(RuntimeError("ollama at internal-host:11434 exploded"))
    monkeypatch.setattr(
        health,
        "Settings",
        _fake_settings(embedding_provider="ollama", embedding_model="nomic-embed-text"),
    )
    monkeypatch.setattr(health, "get_embedding_port", lambda _settings: port)

    result = await health._check_embeddings()

    assert result["status"] == "error"
    assert result["error"] == "not reachable"
    assert "internal-host" not in json.dumps(result)


@pytest.mark.asyncio
async def test_the_embeddings_probe_is_cached_within_the_ttl(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Two calls inside the TTL cost one embed; the TTL expiry forces a fresh probe.

    The probe is a real, billable provider call behind an unauthenticated route, so the
    cache is the cost guard. The clock is a module-level function the test patches —
    never ``sleep``.
    """
    clock = {"now": 1000.0}
    monkeypatch.setattr(health, "_probe_clock", lambda: clock["now"])
    port = _fake_embedding_port([0.1, 0.2, 0.3], dimensions=3)
    monkeypatch.setattr(
        health,
        "Settings",
        _fake_settings(embedding_provider="google", google_embedding_model="gemini-embedding-001"),
    )
    monkeypatch.setattr(health, "get_embedding_port", lambda _settings: port)

    first = await health._check_embeddings()
    second = await health._check_embeddings()

    assert first["status"] == "ok"
    # Whole-dict equality is the cache assertion: the cached dict comes back verbatim,
    # ``latency_ms`` included, which a fresh probe could not reproduce.
    assert second == first
    assert port.embed.await_count == 1

    # Past the 60s TTL the cache must be honoured as expired, not served forever.
    clock["now"] += 61.0
    third = await health._check_embeddings()

    # Not ``third == first``: a fresh probe measures ``latency_ms`` again with the real
    # clock, so the dicts differ on that field by construction and comparing them whole is
    # a race, not a test. The stable fields are compared; the call count proves the probe.
    assert port.embed.await_count == 2
    assert {key: third[key] for key in third if key != "latency_ms"} == {
        key: first[key] for key in first if key != "latency_ms"
    }


@pytest.mark.asyncio
async def test_no_api_key_material_leaks_into_the_services_body(
    async_client, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A configured cloud key must never appear anywhere in the diagnostics body.

    The embeddings probe authenticates with a real key, so this walks the whole decoded
    body — the key is planted in settings and even in the exception text, and must still
    not surface.
    """

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
            raise httpx.ConnectError(f"ConnectError: {url} refused")

    port = _fake_embedding_port(httpx.ConnectError("auth failed for key sup3r-s3cret"))
    monkeypatch.setattr(health, "get_engine", raise_database)
    monkeypatch.setattr(health.httpx, "AsyncClient", RefusingClient)
    monkeypatch.setattr(
        health,
        "Settings",
        _fake_settings(
            qdrant_url="http://qdrant:6333",
            qdrant_api_key="s3cret-key",
            ollama_host="http://ollama:11434",
            embedding_provider="google",
            google_embedding_model="gemini-embedding-001",
        ),
    )
    monkeypatch.setattr(health, "get_embedding_port", lambda _settings: port)

    response = await async_client.get("/api/v1/health/services")

    assert response.status_code == 200
    published = list(_strings_in(response.json()))
    for secret in ("sup3r-s3cret", "s3cret-key"):
        assert secret not in published
        assert secret not in response.text
