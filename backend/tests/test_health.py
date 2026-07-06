"""Tests for the health check endpoint."""

import pytest


def test_can_import():
    """Verify the app factory is importable."""
    from storico.api.app import create_app  # noqa: F811

    app = create_app()
    assert app.title == "Storico API"


@pytest.mark.asyncio
async def test_health_endpoint(async_client):
    """GET /api/v1/health returns 200 with expected JSON structure."""
    response = await async_client.get("/api/v1/health")
    assert response.status_code == 200

    data = response.json()
    assert data["status"] == "ok"
    assert data["version"] == "0.1.0"
