"""Health check endpoint with per-service probes.

Design decisions:
  - The global /api/v1/health endpoint checks ONLY the database, which is
    required for the app to function. It also reports whether the schema is at
    the code's Alembic head, which is not a dependency of the process but is a
    dependency of being useful: that mismatch stayed invisible until 56
    extractions failed with a missing column.
  - Ollama and Qdrant are optional, per-workspace services (users configure
    them in workspace settings, saved to DB). They are NOT checked at the
    global health level. Use /api/v1/health/services for full diagnostics.
  - /api/v1/health is liveness and stays 200 through schema drift;
    /api/v1/health/ready is readiness and answers 503 unless the database
    answers AND the schema matches. See the readiness route for why.
  - None of these routes is authenticated, so each one publishes a status and
    never a revision. The revisions go to the log.
"""

import asyncio
import importlib.metadata
import logging
import time
from datetime import UTC, datetime

import httpx
from fastapi import APIRouter, Response
from sqlalchemy import literal, select

from storico.config.settings import Settings
from storico.infrastructure.database.base import get_engine
from storico.infrastructure.database.schema_status import probe_schema_status
from storico.infrastructure.vector import embedding_model_for, get_embedding_port

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["health"])

SERVICE_TIMEOUT = 3.0  # seconds per service check
DB_TIMEOUT = 3.0  # seconds for database health check


async def _check_database() -> dict:
    """Check PostgreSQL connectivity with a SELECT 1."""
    start = datetime.now(UTC)
    try:
        engine = get_engine()
        async with asyncio.timeout(DB_TIMEOUT):
            async with engine.connect() as conn:
                # Core rather than a raw "SELECT 1": the same probe, without a hand-written SQL
                # string in a route that takes no input from the caller.
                await conn.execute(select(literal(1)))
        elapsed = (datetime.now(UTC) - start).total_seconds() * 1000
        return {"status": "ok", "latency_ms": round(elapsed, 1)}
    except TimeoutError:
        elapsed = (datetime.now(UTC) - start).total_seconds() * 1000
        logger.warning("Database health check timed out after %.0fs", DB_TIMEOUT)
        return {"status": "error", "latency_ms": round(elapsed, 1), "error": "connection timed out"}
    except Exception as e:
        elapsed = (datetime.now(UTC) - start).total_seconds() * 1000
        logger.warning("Database health check failed: %s", e)
        # The reason is spelled here rather than taken from the exception. This route is
        # unauthenticated, so whatever it publishes is published to anyone: a driver's message can
        # name an internal host, a port, a database or a credential, and none of that is part of the
        # answer to "is this service up". The exception is logged just above, which is where an
        # operator can read it. The timeout branch above already made this choice; this branch now
        # makes it too.
        return {"status": "error", "latency_ms": round(elapsed, 1), "error": "connection failed"}


def _package_version() -> str:
    """The installed distribution's version, or ``"unknown"``.

    Read rather than hardcoded: the literal ``"0.1.0"`` this field used to carry had been wrong
    since the package reached ``0.3.0``. The lookup goes to installed metadata, so it is allowed
    to fail — a health endpoint that raises is worse than one that admits it does not know.
    """
    try:
        return importlib.metadata.version("storico-backend")
    except Exception:
        logger.warning("Could not read the installed package version", exc_info=True)
        return "unknown"


async def _check_schema() -> dict:
    """Compare the code's Alembic head with the revision the database carries.

    Shaped like ``_check_database``: a status and a latency. There is no ``error`` field because
    ``unknown`` already is the failure, and there is nothing else an unauthenticated caller may
    learn. Both revisions go to the log below, which is where the diagnosis belongs.
    """
    start = datetime.now(UTC)
    status = "unknown"
    try:
        engine = get_engine()
        async with asyncio.timeout(DB_TIMEOUT):
            result = await probe_schema_status(engine)
        status = result.status
        if status != "ok":
            logger.warning(
                "Schema status is %s: the code expects revision %s, the database holds %s",
                status,
                result.expected_revision,
                result.actual_revision,
            )
    except TimeoutError:
        logger.warning("Schema health check timed out after %.0fs", DB_TIMEOUT)
    except Exception as e:
        logger.warning("Schema health check failed: %s", e)

    elapsed = (datetime.now(UTC) - start).total_seconds() * 1000
    return {"status": status, "latency_ms": round(elapsed, 1)}


async def _check_ollama() -> dict:
    """Check Ollama connectivity via /api/tags."""
    settings = Settings.load()
    start = datetime.now(UTC)
    try:
        async with httpx.AsyncClient(timeout=SERVICE_TIMEOUT) as client:
            resp = await client.get(f"{settings.ollama_host}/api/tags")
            resp.raise_for_status()
            data = resp.json()
        elapsed = (datetime.now(UTC) - start).total_seconds() * 1000
        model_count = len(data.get("models", []))
        return {
            "status": "ok",
            "latency_ms": round(elapsed, 1),
            "model_count": model_count,
        }
    except Exception as e:
        elapsed = (datetime.now(UTC) - start).total_seconds() * 1000
        logger.warning("Ollama health check failed: %s", e)
        # Spelled, not taken from the exception: this route is unauthenticated. See `_check_database`.
        return {"status": "error", "latency_ms": round(elapsed, 1), "error": "not reachable"}


async def _check_qdrant() -> dict:
    """Check Qdrant connectivity via its /healthz endpoint.

    /health was wrong twice against Qdrant Cloud: auth is evaluated before routing, so
    the keyless request this probe used to send got a 403 on a perfectly healthy
    cluster — and even with a key, /health is a 404 there because that route does not
    exist. /healthz is the liveness route Qdrant serves everywhere, and the key goes in
    the ``api-key`` header Qdrant expects.
    """
    settings = Settings.load()
    start = datetime.now(UTC)
    try:
        # Qdrant's documented auth header. Only sent when configured, so a keyless
        # self-hosted deployment never sends an empty credential.
        headers = {"api-key": settings.qdrant_api_key} if settings.qdrant_api_key else {}
        async with httpx.AsyncClient(timeout=SERVICE_TIMEOUT) as client:
            resp = await client.get(f"{settings.qdrant_url}/healthz", headers=headers)
            resp.raise_for_status()
        elapsed = (datetime.now(UTC) - start).total_seconds() * 1000
        return {"status": "ok", "latency_ms": round(elapsed, 1)}
    except Exception as e:
        elapsed = (datetime.now(UTC) - start).total_seconds() * 1000
        logger.warning("Qdrant health check failed: %s", e)
        # Spelled, not taken from the exception: this route is unauthenticated, and the
        # failure text can now sit one step closer to the api key. See `_check_database`.
        return {"status": "error", "latency_ms": round(elapsed, 1), "error": "not reachable"}


_EMBEDDINGS_CACHE_TTL_SECONDS = 60.0
# (monotonic timestamp of the last probe, its result) — module level so the TTL spans
# requests within this process. The probe performs a real, billable provider call, so
# the cache is what keeps this public route from being used to amplify cost.
_embeddings_probe_cache: tuple[float, dict] | None = None


def _probe_clock() -> float:
    """Monotonic clock for the embeddings probe cache — module level so tests can patch it."""
    return time.monotonic()


async def _check_embeddings() -> dict:
    """Probe the configured embedding provider by embedding one short fixed string.

    The probe performs a real, billable third-party call for cloud providers, and this
    route is unauthenticated — without a guard, anyone could drive up cost by polling
    this endpoint. The result is therefore cached in-process for
    ``_EMBEDDINGS_CACHE_TTL_SECONDS`` (60s), so repeated requests within the TTL reuse
    one provider call.

    ``provider`` and ``model`` come from settings, ``dimensions`` from the port, and
    ``vector_length`` is the length of the vector actually returned. Failures degrade to
    a spelled reason (never the exception text, see `_check_database`) and never raise:
    an unknown provider must not turn a diagnostics route into a 500.
    """
    global _embeddings_probe_cache
    now = _probe_clock()
    if (
        _embeddings_probe_cache is not None
        and now - _embeddings_probe_cache[0] < _EMBEDDINGS_CACHE_TTL_SECONDS
    ):
        return dict(_embeddings_probe_cache[1])

    settings = Settings.load()
    start = datetime.now(UTC)
    try:
        port = get_embedding_port(settings)
        vector = await port.embed("storico health probe")
        elapsed = (datetime.now(UTC) - start).total_seconds() * 1000
        if not vector:
            # The embedding service degrades its own failures to ``[]``, so an empty
            # vector means the provider could not be reached.
            result = {"status": "error", "latency_ms": round(elapsed, 1), "error": "not reachable"}
        else:
            result = {
                "status": "ok",
                "latency_ms": round(elapsed, 1),
                "provider": settings.embedding_provider,
                # Not ``settings.embedding_model``: that field is the Ollama model, and
                # reading it here named ``nomic-embed-text`` for a Google or OpenAI
                # deployment while the adapter called something else entirely.
                "model": embedding_model_for(settings),
                "dimensions": port.dimensions,
                "vector_length": len(vector),
            }
    except ValueError as e:
        # get_embedding_port spells this itself: unknown provider, or a cloud provider
        # selected without its API key.
        elapsed = (datetime.now(UTC) - start).total_seconds() * 1000
        logger.warning("Embeddings health check failed: %s", e)
        result = {"status": "error", "latency_ms": round(elapsed, 1), "error": "not configured"}
    except Exception as e:
        elapsed = (datetime.now(UTC) - start).total_seconds() * 1000
        logger.warning("Embeddings health check failed: %s", e)
        # Spelled, not taken from the exception: this route is unauthenticated. See `_check_database`.
        result = {"status": "error", "latency_ms": round(elapsed, 1), "error": "not reachable"}

    _embeddings_probe_cache = (now, result)
    return dict(result)


@router.get("/health")
async def health():
    """Return API health status.

    Only checks the database — the single required dependency. Ollama and Qdrant are optional
    per-workspace services and are not checked at the global health level.

    The schema is reported next to the database but does not change ``status`` or the HTTP code:
    this is a liveness probe, and a schema behind the code is a reason not to send traffic, not a
    reason to kill and restart a container that is running.
    """
    db_result = await _check_database()
    schema_result = await _check_schema()

    overall = "ok" if db_result.get("status") == "ok" else "degraded"

    return {
        "status": overall,
        "version": _package_version(),
        "timestamp": datetime.now(UTC).isoformat(),
        "database": db_result,
        "schema": schema_result,
    }


@router.get("/health/services")
async def health_services():
    """Full diagnostics — checks all configured services.

    This is a debugging endpoint only. Use /api/v1/health for standard
    health checks (required services only). ``schema`` is reported here too: this
    is the route that answers "what state is this deployment in".
    """
    db_result = await _check_database()
    schema_result = await _check_schema()
    ollama_result = await _check_ollama()
    qdrant_result = await _check_qdrant()
    embeddings_result = await _check_embeddings()

    all_ok = all(
        probe.get("status") == "ok"
        for probe in [db_result, schema_result, ollama_result, qdrant_result, embeddings_result]
    )

    return {
        "status": "ok" if all_ok else "degraded",
        "version": _package_version(),
        "timestamp": datetime.now(UTC).isoformat(),
        "services": {
            "database": db_result,
            "schema": schema_result,
            "ollama": ollama_result,
            "qdrant": qdrant_result,
            "embeddings": embeddings_result,
        },
    }


@router.get("/health/ready")
async def health_ready(response: Response):
    """Readiness: 200 only when the database answers and the schema is at the code's head.

    Liveness and readiness answer different questions, which is why this is a second route rather
    than a stricter ``/health``. A container whose schema is behind should not take traffic, but
    restarting it would not migrate anything — so ``/health`` keeps answering 200 and this route
    answers 503 until an operator applies the pending revision.

    The status code is the whole interface: ``curl -sf`` under ``set -e`` fails a deploy without
    parsing JSON on the VM. The body is the same document either way, so a reader never has to
    branch on the code to read it.

    Like its siblings this route takes no authentication, and it publishes no revision.
    """
    db_result = await _check_database()
    schema_result = await _check_schema()

    ready = db_result.get("status") == "ok" and schema_result.get("status") == "ok"
    response.status_code = 200 if ready else 503

    return {
        "status": "ok" if ready else "degraded",
        "version": _package_version(),
        "timestamp": datetime.now(UTC).isoformat(),
        "database": db_result,
        "schema": schema_result,
    }
