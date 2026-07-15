"""Integration tests for the User API endpoints."""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from storico.domain.entities import User
from storico.infrastructure.database.repositories import SQLAlchemyUserRepository
from storico.infrastructure.database.repositories.workspace_repository import (
    SQLAlchemyWorkspaceRepository,
)
from tests.conftest import AUTH_INTERNAL_TOKEN


USER_ME_URL = "/api/v1/users/me"
ONBOARDING_URL = "/api/v1/users/me/onboarding"


class TestGetUserMe:
    """GET /api/v1/users/me"""

    async def test_get_user_me_unauthorized(self, async_client):
        """GET /me without auth headers returns 401."""
        response = await async_client.get(USER_ME_URL)
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

        response = await async_client.get(USER_ME_URL)
        assert response.status_code == 401

    async def test_get_user_me_missing_user_id(
        self, async_client, db_session: AsyncSession
    ):
        """GET /me without X-Storico-User-Id returns 401."""
        async_client.headers["X-Storico-Internal-Token"] = AUTH_INTERNAL_TOKEN

        response = await async_client.get(USER_ME_URL)
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

        response = await async_client.get(USER_ME_URL)
        assert response.status_code == 200

        data = response.json()
        assert data["email"] == "alice@example.com"
        assert data["name"] == "Alice"
        assert data["auth_provider"] == "google"
        assert data["auth_id"] == "google-123"
        assert data["avatar_url"] is None
        assert data["is_first_login"] is False
        assert UUID(data["id"]) == user.id
        assert "created_at" in data


class TestCompleteOnboarding:
    """PATCH /api/v1/users/me/onboarding"""

    async def test_complete_onboarding_sets_flag_false(
        self, async_client, db_session: AsyncSession
    ):
        """PATCH /me/onboarding sets is_first_login=False."""
        repo = SQLAlchemyUserRepository(db_session)
        user = User(email="onboard@example.com", name="Onboard User")
        await repo.save(user)
        await repo.link_account(user.id, "google", "g-onboard")

        async_client.headers["X-Storico-Internal-Token"] = AUTH_INTERNAL_TOKEN
        async_client.headers["X-Storico-User-Id"] = str(user.id)

        response = await async_client.patch(ONBOARDING_URL, json={})
        assert response.status_code == 200
        assert response.json() == {"success": True}

        # Verify via GET /me
        resp = await async_client.get(USER_ME_URL)
        assert resp.json()["is_first_login"] is False

    async def test_complete_onboarding_with_workspace_rename(
        self, async_client, db_session: AsyncSession
    ):
        """PATCH /me/onboarding with workspace_name renames the workspace."""
        from storico.application.workspaces.create_workspace import CreateWorkspaceUseCase
        from storico.infrastructure.database.repositories.workspace_member_repository import (
            SQLAlchemyWorkspaceMemberRepository,
        )

        repo = SQLAlchemyUserRepository(db_session)
        ws_repo = SQLAlchemyWorkspaceRepository(db_session)
        member_repo = SQLAlchemyWorkspaceMemberRepository(db_session)

        user = User(email="rename@example.com", name="Rename User")
        await repo.save(user)
        await repo.link_account(user.id, "google", "g-rename")

        use_case = CreateWorkspaceUseCase(ws_repo=ws_repo, member_repo=member_repo)
        await use_case.execute(name=f"{user.name}'s Workspace", user_id=user.id)

        async_client.headers["X-Storico-Internal-Token"] = AUTH_INTERNAL_TOKEN
        async_client.headers["X-Storico-User-Id"] = str(user.id)

        response = await async_client.patch(
            ONBOARDING_URL, json={"workspace_name": "My Team"}
        )
        assert response.status_code == 200
        assert response.json() == {"success": True}

        # Verify workspace renamed
        workspaces = await ws_repo.list_by_user(user.id)
        assert len(workspaces) == 1
        assert workspaces[0].name == "My Team"

    async def test_complete_onboarding_idempotent(
        self, async_client, db_session: AsyncSession
    ):
        """PATCH /me/onboarding returns 200 on second call — idempotent."""
        repo = SQLAlchemyUserRepository(db_session)
        user = User(email="idempotent@example.com", name="Idempotent User")
        await repo.save(user)
        await repo.link_account(user.id, "google", "g-idempotent")

        async_client.headers["X-Storico-Internal-Token"] = AUTH_INTERNAL_TOKEN
        async_client.headers["X-Storico-User-Id"] = str(user.id)

        # First call
        resp1 = await async_client.patch(ONBOARDING_URL, json={})
        assert resp1.status_code == 200

        # Second call — idempotent
        resp2 = await async_client.patch(ONBOARDING_URL, json={})
        assert resp2.status_code == 200

        # is_first_login remains false
        resp = await async_client.get(USER_ME_URL)
        assert resp.json()["is_first_login"] is False

    async def test_complete_onboarding_unauthorized(self, async_client):
        """PATCH /me/onboarding without auth returns 401."""
        response = await async_client.patch(ONBOARDING_URL, json={})
        assert response.status_code == 401
