"""Integration tests for the User API endpoints."""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from storico.domain.entities import User
from storico.infrastructure.database.repositories import SQLAlchemyUserRepository
from tests.conftest import AUTH_INTERNAL_TOKEN


class TestGetUserMe:
    """GET /api/v1/users/me"""

    async def test_get_user_me_unauthorized(self, async_client):
        """GET /me without auth headers returns 401."""
        response = await async_client.get("/api/v1/users/me")
        assert response.status_code == 401

    async def test_get_user_me_wrong_token(
        self, async_client, db_session: AsyncSession
    ):
        """GET /me with wrong internal token returns 401."""
        repo = SQLAlchemyUserRepository(db_session)
        user = User(
            email="alice@example.com",
            name="Alice",
        )
        await repo.save(user)
        await repo.link_account(user.id, "google", "google-123")

        async_client.headers["X-Storico-Internal-Token"] = "wrong-token"
        async_client.headers["X-Storico-User-Id"] = str(user.id)

        response = await async_client.get("/api/v1/users/me")
        assert response.status_code == 401

    async def test_get_user_me_missing_user_id(
        self, async_client, db_session: AsyncSession
    ):
        """GET /me without X-Storico-User-Id returns 401."""
        async_client.headers["X-Storico-Internal-Token"] = AUTH_INTERNAL_TOKEN

        response = await async_client.get("/api/v1/users/me")
        assert response.status_code == 401

    async def test_get_user_me_valid(
        self, async_client, db_session: AsyncSession
    ):
        """GET /me with valid auth returns the authenticated user's profile."""
        repo = SQLAlchemyUserRepository(db_session)
        user = User(
            email="alice@example.com",
            name="Alice",
        )
        await repo.save(user)
        await repo.link_account(user.id, "google", "google-123")

        async_client.headers["X-Storico-Internal-Token"] = AUTH_INTERNAL_TOKEN
        async_client.headers["X-Storico-User-Id"] = str(user.id)

        response = await async_client.get("/api/v1/users/me")
        assert response.status_code == 200

        data = response.json()
        assert data["email"] == "alice@example.com"
        assert data["name"] == "Alice"
        assert data["auth_provider"] == "google"
        assert data["auth_id"] == "google-123"
        assert data["avatar_url"] is None
        assert UUID(data["id"]) == user.id
        assert "created_at" in data
