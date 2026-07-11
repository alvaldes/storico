"""Tests for the health check endpoint."""

import pytest


def test_can_import():
    """Verify the app factory is importable."""
    from storico.api.app import create_app  # noqa: F811

    app = create_app()
    assert app.title == "Storico API"


@pytest.mark.asyncio
async def test_health_endpoint(async_client):
    """GET /api/v1/health returns 200 with expected JSON structure.

    The endpoint probes external services (PostgreSQL, Ollama, Qdrant)
    so individual service statuses may be 'ok' or 'error' depending on
    the test environment. The overall status reflects the aggregate.
    """
    response = await async_client.get("/api/v1/health")
    assert response.status_code == 200

    data = response.json()
    assert data["version"] == "0.1.0"
    assert data["status"] in ("ok", "degraded")
    assert "timestamp" in data
    assert "services" in data

    # Every expected service must be present.
    for svc in ("database", "ollama", "qdrant"):
        assert svc in data["services"]
        assert data["services"][svc]["status"] in ("ok", "error")
        assert "latency_ms" in data["services"][svc]
