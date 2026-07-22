"""Tests for the health check endpoint.

The main /api/v1/health endpoint only checks the database (required).
Full service diagnostics are at /api/v1/health/services.
"""

import pytest


def test_can_import():
    """Verify the app factory is importable."""
    from storico.api.app import create_app  # noqa: F811

    app = create_app()
    assert app.title == "Storico API"


@pytest.mark.asyncio
async def test_health_endpoint(async_client):
    """GET /api/v1/health returns 200 with database check only."""
    response = await async_client.get("/api/v1/health")
    assert response.status_code == 200

    data = response.json()
    assert data["version"] == "0.1.0"
    assert data["status"] in ("ok", "degraded")
    assert "timestamp" in data

    # Database is the only required service in the main health check.
    assert "database" in data
    assert data["database"]["status"] in ("ok", "error")
    assert "latency_ms" in data["database"]

    # Ollama and Qdrant are NOT in the main endpoint.
    assert "services" not in data


@pytest.mark.asyncio
async def test_health_services_endpoint(async_client):
    """GET /api/v1/health/services returns all configured services."""
    response = await async_client.get("/api/v1/health/services")
    assert response.status_code == 200

    data = response.json()
    assert data["version"] == "0.1.0"
    assert data["status"] in ("ok", "degraded")
    assert "services" in data

    for svc in ("database", "ollama", "qdrant"):
        assert svc in data["services"]
        assert data["services"][svc]["status"] in ("ok", "error")
        assert "latency_ms" in data["services"][svc]
