"""Health check endpoint with per-service probes."""

import asyncio
import logging
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter
from sqlalchemy import text

from storico.config.settings import Settings
from storico.infrastructure.database.base import get_engine

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["health"])

SERVICE_TIMEOUT = 5.0  # seconds per service check


async def _check_database() -> dict:
    """Check PostgreSQL connectivity with a SELECT 1."""
    start = datetime.now(timezone.utc)
    try:
        engine = get_engine()
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        elapsed = (datetime.now(timezone.utc) - start).total_seconds() * 1000
        return {"status": "ok", "latency_ms": round(elapsed, 1)}
    except Exception as e:
        elapsed = (datetime.now(timezone.utc) - start).total_seconds() * 1000
        logger.warning("Database health check failed: %s", e)
        return {"status": "error", "latency_ms": round(elapsed, 1), "error": str(e)}


async def _check_ollama() -> dict:
    """Check Ollama connectivity via /api/tags."""
    settings = Settings.load()
    start = datetime.now(timezone.utc)
    try:
        async with httpx.AsyncClient(timeout=SERVICE_TIMEOUT) as client:
            resp = await client.get(f"{settings.ollama_host}/api/tags")
            resp.raise_for_status()
            data = resp.json()
        elapsed = (datetime.now(timezone.utc) - start).total_seconds() * 1000
        model_count = len(data.get("models", []))
        return {
            "status": "ok",
            "latency_ms": round(elapsed, 1),
            "model_count": model_count,
        }
    except Exception as e:
        elapsed = (datetime.now(timezone.utc) - start).total_seconds() * 1000
        logger.warning("Ollama health check failed: %s", e)
        return {"status": "error", "latency_ms": round(elapsed, 1), "error": str(e)}


async def _check_qdrant() -> dict:
    """Check Qdrant connectivity via its /health endpoint."""
    settings = Settings.load()
    start = datetime.now(timezone.utc)
    try:
        async with httpx.AsyncClient(timeout=SERVICE_TIMEOUT) as client:
            resp = await client.get(f"{settings.qdrant_url}/health")
            resp.raise_for_status()
        elapsed = (datetime.now(timezone.utc) - start).total_seconds() * 1000
        return {"status": "ok", "latency_ms": round(elapsed, 1)}
    except Exception as e:
        elapsed = (datetime.now(timezone.utc) - start).total_seconds() * 1000
        logger.warning("Qdrant health check failed: %s", e)
        return {"status": "error", "latency_ms": round(elapsed, 1), "error": str(e)}


@router.get("/health")
async def health():
    """Return API health status with per-service probes."""
    results = await asyncio.gather(
        _check_database(),
        _check_ollama(),
        _check_qdrant(),
        return_exceptions=True,
    )

    services: dict[str, dict] = {}
    for key, result in zip(["database", "ollama", "qdrant"], results):
        if isinstance(result, BaseException):
            services[key] = _exception_result(result)
        else:
            services[key] = result  # pyright: ignore[reportAssignmentType]

    all_ok = all(s.get("status") == "ok" for s in services.values())

    return {
        "status": "ok" if all_ok else "degraded",
        "version": "0.1.0",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "services": services,
    }


def _exception_result(exc: BaseException) -> dict:
    return {"status": "error", "latency_ms": None, "error": str(exc)}
