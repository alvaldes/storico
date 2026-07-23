"""Tests for POST /api/v1/auth/sync and the get_current_user dependency."""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from storico.domain.entities import User
from storico.infrastructure.database.repositories import SQLAlchemyUserRepository
from tests.conftest import make_jwt_headers

SYNC_URL = "/api/v1/auth/sync"
USERS_ME_URL = "/api/v1/users/me"


class TestSyncUser:
    """POST /api/v1/auth/sync

    The sync endpoint is intentionally unauthenticated — it is called
    server-side only by the Auth.js JWT callback in the Astro proxy.
    """

    async def test_sync_new_user(self, async_client, db_session: AsyncSession):
        """POST creates a new user and returns 200 with user data."""
        payload = {
            "email": "new@example.com",
            "name": "New User",
            "auth_provider": "google",
            "auth_provider_id": "g-new",
        }
        response = await async_client.post(SYNC_URL, json=payload)
        assert response.status_code == 200

        data = response.json()
        assert data["email"] == "new@example.com"
        assert data["name"] == "New User"
        assert data["auth_provider"] == "google"
        assert data["auth_id"] == "g-new"
        assert "id" in data
        assert "created_at" in data
        assert data["is_first_login"] is True  # step (c) — new user

        # Verify via /me with JWT
        headers = make_jwt_headers(data["id"])
        response2 = await async_client.get(USERS_ME_URL, headers=headers)
        assert response2.status_code == 200
        assert response2.json()["user"]["email"] == "new@example.com"

    async def test_sync_existing_user(self, async_client):
        """POST twice — first creates, second upserts (same auth)."""
        payload = {
            "email": "existing@example.com",
            "name": "Original Name",
            "auth_provider": "github",
            "auth_provider_id": "gh-1",
        }

        # First call — create
        resp1 = await async_client.post(SYNC_URL, json=payload)
        assert resp1.status_code == 200
        user_id = resp1.json()["id"]

        # Second call — upsert with updated name
        payload["name"] = "Updated Name"
        resp2 = await async_client.post(SYNC_URL, json=payload)
        assert resp2.status_code == 200
        assert resp2.json()["id"] == user_id
        assert resp2.json()["name"] == "Updated Name"
        assert resp2.json()["email"] == "existing@example.com"
        # is_first_login stays True — only onboarding endpoint flips it
        assert resp2.json()["is_first_login"] is True

        # Verify via /me with JWT
        headers = make_jwt_headers(user_id)
        resp3 = await async_client.get(USERS_ME_URL, headers=headers)
        assert resp3.status_code == 200
        assert resp3.json()["user"]["name"] == "Updated Name"

    async def test_sync_updates_profile(self, async_client):
        """POST with avatar_url stores and updates it."""
        payload = {
            "email": "profile@example.com",
            "name": "Profile",
            "auth_provider": "google",
            "auth_provider_id": "g-profile",
        }

        # Create without avatar
        resp1 = await async_client.post(SYNC_URL, json=payload)
        assert resp1.status_code == 200
        user_id = resp1.json()["id"]

        # Update with avatar
        payload["avatar_url"] = "https://example.com/avatar.jpg"
        payload["name"] = "Profile Updated"
        resp2 = await async_client.post(SYNC_URL, json=payload)
        assert resp2.status_code == 200
        assert resp2.json()["id"] == user_id
        assert resp2.json()["name"] == "Profile Updated"

        # Verify via /me with JWT
        headers = make_jwt_headers(user_id)
        resp3 = await async_client.get(USERS_ME_URL, headers=headers)
        assert resp3.status_code == 200
        data = resp3.json()
        assert data["user"]["name"] == "Profile Updated"
        assert data["user"]["avatar_url"] == "https://example.com/avatar.jpg"

    async def test_sync_same_email_links_accounts(self, async_client):
        """Step (b): same email, different provider links accounts."""
        # First: create user via google
        payload1 = {
            "email": "link@example.com",
            "name": "Link User",
            "auth_provider": "google",
            "auth_provider_id": "g-link-1",
        }
        resp1 = await async_client.post(SYNC_URL, json=payload1)
        assert resp1.status_code == 200
        user_id = resp1.json()["id"]

        # Second: same email via github — should link, not create
        payload2 = {
            "email": "link@example.com",
            "name": "Link User Updated",
            "auth_provider": "github",
            "auth_provider_id": "gh-link-1",
        }
        resp2 = await async_client.post(SYNC_URL, json=payload2)
        assert resp2.status_code == 200
        assert resp2.json()["id"] == user_id  # same user
        assert resp2.json()["auth_provider"] == "github"  # reflects login provider
        assert resp2.json()["auth_id"] == "gh-link-1"
        # is_first_login stays True — only onboarding endpoint flips it
        assert resp2.json()["is_first_login"] is True

    async def test_sync_new_user_linked(self, async_client):
        """Step (c): new user creates user and account together."""
        payload = {
            "email": "fresh@example.com",
            "name": "Fresh",
            "auth_provider": "google",
            "auth_provider_id": "g-fresh",
        }
        response = await async_client.post(SYNC_URL, json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["email"] == "fresh@example.com"
        assert data["auth_provider"] == "google"
        assert data["auth_id"] == "g-fresh"

        # Login again with same provider — should find existing
        resp2 = await async_client.post(SYNC_URL, json=payload)
        assert resp2.status_code == 200
        assert resp2.json()["id"] == data["id"]

    async def test_sync_rejects_extra_fields(self, async_client):
        """POST with unknown field returns 422."""
        payload = {
            "email": "bad@example.com",
            "name": "Bad",
            "auth_provider": "google",
            "auth_provider_id": "g-bad",
            "unknown_field": "should not be allowed",
        }
        response = await async_client.post(SYNC_URL, json=payload)
        assert response.status_code == 422


class TestGetCurrentUser:
    """Tests for the get_current_user dependency via /api/v1/users/me"""

    async def test_missing_token(self, async_client):
        """GET /me without JWT returns 401."""
        response = await async_client.get(USERS_ME_URL)
        assert response.status_code == 401

    async def test_wrong_token(self, async_client):
        """GET /me with wrong JWT returns 401."""
        headers = {"Authorization": "Bearer wrong-token"}
        response = await async_client.get(USERS_ME_URL, headers=headers)
        assert response.status_code == 401

    async def test_valid_user(self, async_client, db_session: AsyncSession):
        """GET /me with valid JWT returns the user."""
        repo = SQLAlchemyUserRepository(db_session)
        user = User(email="valid@example.com", name="Valid User")
        await repo.save(user)
        await repo.link_account(user.id, "google", "g-valid")

        headers = make_jwt_headers(str(user.id))
        response = await async_client.get(USERS_ME_URL, headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert data["user"]["email"] == "valid@example.com"
        assert data["user"]["name"] == "Valid User"
        assert data["user"]["auth_provider"] == "google"
        assert data["user"]["auth_id"] == "g-valid"
        assert UUID(data["user"]["id"]) == user.id

    async def test_nonexistent_user_id(self, async_client):
        """GET /me with valid JWT but non-existent user ID returns 401."""
        fake_id = "00000000-0000-0000-0000-000000000000"
        headers = make_jwt_headers(fake_id)
        response = await async_client.get(USERS_ME_URL, headers=headers)
        assert response.status_code == 401
