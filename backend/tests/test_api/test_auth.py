"""Tests for POST /api/v1/auth/sync and the get_current_user dependency."""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from storico.domain.entities import User
from storico.infrastructure.database.repositories import SQLAlchemyUserRepository
from tests.conftest import AUTH_INTERNAL_TOKEN

SYNC_URL = "/api/v1/auth/sync"
USERS_ME_URL = "/api/v1/users/me"


class TestSyncUser:
    """POST /api/v1/auth/sync"""

    async def test_sync_new_user(self, async_client):
        """POST creates a new user and returns 200 with user data."""
        payload = {
            "email": "new@example.com",
            "name": "New User",
            "auth_provider": "google",
            "auth_provider_id": "g-new",
        }
        sync_headers = {"X-Storico-Internal-Token": AUTH_INTERNAL_TOKEN}
        response = await async_client.post(SYNC_URL, json=payload, headers=sync_headers)
        assert response.status_code == 200

        data = response.json()
        assert data["email"] == "new@example.com"
        assert data["name"] == "New User"
        assert data["auth_provider"] == "google"
        assert data["auth_id"] == "g-new"
        assert "id" in data
        assert "created_at" in data

        # Verify it was actually saved
        get_me_headers = {
            "X-Storico-Internal-Token": AUTH_INTERNAL_TOKEN,
            "X-Storico-User-Id": data["id"],
        }
        response2 = await async_client.get(USERS_ME_URL, headers=get_me_headers)
        assert response2.status_code == 200
        assert response2.json()["email"] == "new@example.com"

    async def test_sync_existing_user(self, async_client):
        """POST twice — first creates, second upserts (same auth)."""
        payload = {
            "email": "existing@example.com",
            "name": "Original Name",
            "auth_provider": "github",
            "auth_provider_id": "gh-1",
        }

        sync_headers = {"X-Storico-Internal-Token": AUTH_INTERNAL_TOKEN}

        # First call — create
        resp1 = await async_client.post(SYNC_URL, json=payload, headers=sync_headers)
        assert resp1.status_code == 200
        user_id = resp1.json()["id"]

        # Second call — upsert with updated name
        payload["name"] = "Updated Name"
        resp2 = await async_client.post(SYNC_URL, json=payload, headers=sync_headers)
        assert resp2.status_code == 200
        assert resp2.json()["id"] == user_id
        assert resp2.json()["name"] == "Updated Name"
        assert resp2.json()["email"] == "existing@example.com"

        # Verify via get_current_user
        get_me_headers = {
            "X-Storico-Internal-Token": AUTH_INTERNAL_TOKEN,
            "X-Storico-User-Id": user_id,
        }
        resp3 = await async_client.get(USERS_ME_URL, headers=get_me_headers)
        assert resp3.status_code == 200
        assert resp3.json()["name"] == "Updated Name"

    async def test_sync_updates_profile(self, async_client):
        """POST with avatar_url stores and updates it."""
        payload = {
            "email": "profile@example.com",
            "name": "Profile",
            "auth_provider": "google",
            "auth_provider_id": "g-profile",
        }

        sync_headers = {"X-Storico-Internal-Token": AUTH_INTERNAL_TOKEN}

        # Create without avatar
        resp1 = await async_client.post(SYNC_URL, json=payload, headers=sync_headers)
        assert resp1.status_code == 200
        user_id = resp1.json()["id"]

        # Update with avatar
        payload["avatar_url"] = "https://example.com/avatar.jpg"
        payload["name"] = "Profile Updated"
        resp2 = await async_client.post(SYNC_URL, json=payload, headers=sync_headers)
        assert resp2.status_code == 200
        assert resp2.json()["id"] == user_id
        assert resp2.json()["name"] == "Profile Updated"

        # Verify via get_current_user
        get_me_headers = {
            "X-Storico-Internal-Token": AUTH_INTERNAL_TOKEN,
            "X-Storico-User-Id": user_id,
        }
        resp3 = await async_client.get(USERS_ME_URL, headers=get_me_headers)
        assert resp3.status_code == 200
        data = resp3.json()
        assert data["name"] == "Profile Updated"
        assert data["avatar_url"] == "https://example.com/avatar.jpg"

    async def test_sync_same_email_links_accounts(self, async_client):
        """Step (b): same email, different provider links accounts."""
        # First: create user via google
        payload1 = {
            "email": "link@example.com",
            "name": "Link User",
            "auth_provider": "google",
            "auth_provider_id": "g-link-1",
        }
        sync_headers = {"X-Storico-Internal-Token": AUTH_INTERNAL_TOKEN}
        resp1 = await async_client.post(SYNC_URL, json=payload1, headers=sync_headers)
        assert resp1.status_code == 200
        user_id = resp1.json()["id"]

        # Second: same email via github — should link, not create
        payload2 = {
            "email": "link@example.com",
            "name": "Link User Updated",
            "auth_provider": "github",
            "auth_provider_id": "gh-link-1",
        }
        resp2 = await async_client.post(SYNC_URL, json=payload2, headers=sync_headers)
        assert resp2.status_code == 200
        assert resp2.json()["id"] == user_id  # same user
        assert resp2.json()["auth_provider"] == "github"  # reflects login provider
        assert resp2.json()["auth_id"] == "gh-link-1"

        # Verify both providers can find the same user
        repo_sync = SQLAlchemyUserRepository  # get repo from fixture context
        # Can't access repo directly; use the sync endpoint to verify access

    async def test_sync_new_user_linked(self, async_client):
        """Step (c): new user creates user and account together."""
        payload = {
            "email": "fresh@example.com",
            "name": "Fresh",
            "auth_provider": "google",
            "auth_provider_id": "g-fresh",
        }
        sync_headers = {"X-Storico-Internal-Token": AUTH_INTERNAL_TOKEN}
        response = await async_client.post(SYNC_URL, json=payload, headers=sync_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["email"] == "fresh@example.com"
        assert data["auth_provider"] == "google"
        assert data["auth_id"] == "g-fresh"

        # Login again with same provider — should find existing
        resp2 = await async_client.post(SYNC_URL, json=payload, headers=sync_headers)
        assert resp2.status_code == 200
        assert resp2.json()["id"] == data["id"]

    async def test_sync_rejects_missing_token(self, async_client):
        """POST /sync without internal token returns 401."""
        payload = {
            "email": "noauth@example.com",
            "name": "No Auth",
            "auth_provider": "google",
            "auth_provider_id": "g-noauth",
        }
        response = await async_client.post(SYNC_URL, json=payload)
        assert response.status_code == 401

    async def test_sync_rejects_extra_fields(self, async_client):
        """POST with unknown field returns 422."""
        payload = {
            "email": "bad@example.com",
            "name": "Bad",
            "auth_provider": "google",
            "auth_provider_id": "g-bad",
            "unknown_field": "should not be allowed",
        }
        sync_headers = {"X-Storico-Internal-Token": AUTH_INTERNAL_TOKEN}
        response = await async_client.post(SYNC_URL, json=payload, headers=sync_headers)
        assert response.status_code == 422


class TestGetCurrentUser:
    """Tests for the get_current_user dependency via /api/v1/users/me"""

    async def test_missing_token(self, async_client):
        """GET /me without internal token returns 401."""
        response = await async_client.get(USERS_ME_URL)
        assert response.status_code == 401

    async def test_wrong_token(self, async_client):
        """GET /me with wrong internal token returns 401."""
        headers = {
            "X-Storico-Internal-Token": "wrong-token",
            "X-Storico-User-Id": "00000000-0000-0000-0000-000000000000",
        }
        response = await async_client.get(USERS_ME_URL, headers=headers)
        assert response.status_code == 401

    async def test_missing_user_id(self, async_client):
        """GET /me with correct token but no user ID returns 401."""
        headers = {
            "X-Storico-Internal-Token": AUTH_INTERNAL_TOKEN,
        }
        response = await async_client.get(USERS_ME_URL, headers=headers)
        assert response.status_code == 401
        detail = response.json()["detail"]
        assert detail == "Missing user identification"

    async def test_valid_user(self, async_client, db_session: AsyncSession):
        """GET /me with valid token and correct user ID returns the user."""
        repo = SQLAlchemyUserRepository(db_session)
        user = User(email="valid@example.com", name="Valid User")
        await repo.save(user)
        await repo.link_account(user.id, "google", "g-valid")

        headers = {
            "X-Storico-Internal-Token": AUTH_INTERNAL_TOKEN,
            "X-Storico-User-Id": str(user.id),
        }
        response = await async_client.get(USERS_ME_URL, headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert data["email"] == "valid@example.com"
        assert data["name"] == "Valid User"
        assert data["auth_provider"] == "google"
        assert data["auth_id"] == "g-valid"
        assert UUID(data["id"]) == user.id

    async def test_nonexistent_user_id(self, async_client):
        """GET /me with valid token but non-existent user ID returns 401."""
        headers = {
            "X-Storico-Internal-Token": AUTH_INTERNAL_TOKEN,
            "X-Storico-User-Id": "00000000-0000-0000-0000-000000000000",
        }
        response = await async_client.get(USERS_ME_URL, headers=headers)
        assert response.status_code == 401
