"""Health check endpoint with per-service probes.

Design decisions:
  - The global /api/v1/health endpoint checks ONLY the database, which is
    required for the app to function.
  - Ollama and Qdrant are optional, per-workspace services (users configure
    them in workspace settings, saved to DB). They are NOT checked at the
    global health level. Use /api/v1/health/services for full diagnostics.
"""

import asyncio
import logging
from datetime import UTC, datetime

import httpx
from fastapi import APIRouter
from sqlalchemy import literal, select

from storico.config.settings import Settings
from storico.infrastructure.database.base import get_engine

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
    """Check Qdrant connectivity via its /health endpoint."""
    settings = Settings.load()
    start = datetime.now(UTC)
    try:
        async with httpx.AsyncClient(timeout=SERVICE_TIMEOUT) as client:
            resp = await client.get(f"{settings.qdrant_url}/health")
            resp.raise_for_status()
        elapsed = (datetime.now(UTC) - start).total_seconds() * 1000
        return {"status": "ok", "latency_ms": round(elapsed, 1)}
    except Exception as e:
        elapsed = (datetime.now(UTC) - start).total_seconds() * 1000
        logger.warning("Qdrant health check failed: %s", e)
        # Spelled, not taken from the exception: this route is unauthenticated. See `_check_database`.
        return {"status": "error", "latency_ms": round(elapsed, 1), "error": "not reachable"}


@router.get("/health")
async def health():
    """Return API health status.

    Only checks the database — the single required dependency.
    Ollama and Qdrant are optional per-workspace services and are not
    checked at the global health level.
    """
    db_result = await _check_database()

    overall = "ok" if db_result.get("status") == "ok" else "degraded"

    return {
        "status": overall,
        "version": "0.1.0",
        "timestamp": datetime.now(UTC).isoformat(),
        "database": db_result,
    }


@router.get("/health/services")
async def health_services():
    """Full diagnostics — checks all configured services.

    This is a debugging endpoint only. Use /api/v1/health for standard
    health checks (required services only).
    """
    db_result = await _check_database()
    ollama_result = await _check_ollama()
    qdrant_result = await _check_qdrant()

    all_ok = all(r.get("status") == "ok" for r in [db_result, ollama_result, qdrant_result])

    return {
        "status": "ok" if all_ok else "degraded",
        "version": "0.1.0",
        "timestamp": datetime.now(UTC).isoformat(),
        "services": {
            "database": db_result,
            "ollama": ollama_result,
            "qdrant": qdrant_result,
        },
    }
