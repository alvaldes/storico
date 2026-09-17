"""Integration tests for the User API endpoints."""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from storico.domain.entities import User
from storico.infrastructure.database.repositories import SQLAlchemyUserRepository
from storico.infrastructure.database.repositories.workspace_repository import (
    SQLAlchemyWorkspaceRepository,
)

USER_ME_URL = "/api/v1/users/me"
ONBOARDING_URL = "/api/v1/users/me/onboarding"


class TestGetUserMe:
    """GET /api/v1/users/me"""

    async def test_get_user_me_unauthorized(self, async_client):
        """GET /me without auth headers returns 401."""
        response = await async_client.get(USER_ME_URL)
        assert response.status_code == 401

    async def test_get_user_me_wrong_token(self, async_client, db_session: AsyncSession):
        """GET /me with wrong JWT token returns 401."""
        repo = SQLAlchemyUserRepository(db_session)
        user = User(
            email="alice@example.com",
            name="Alice",
        )
        await repo.save(user)
        await repo.link_account(user.id, "google", "google-123")

        async_client.headers["Authorization"] = "Bearer wrong-token"

        response = await async_client.get(USER_ME_URL)
        assert response.status_code == 401

    async def test_get_user_me_missing_user_id(self, async_client, db_session: AsyncSession):
        """GET /me without any auth headers returns 401."""
        response = await async_client.get(USER_ME_URL)
        assert response.status_code == 401

    async def test_get_user_me_valid(self, authed_client, authed_user: User):
        """GET /me with valid JWT returns the authenticated user's profile."""
        response = await authed_client.get(USER_ME_URL)
        assert response.status_code == 200

        data = response.json()
        user_data = data["user"]
        assert user_data["name"] == "Authed Test"
        assert UUID(user_data["id"]) == authed_user.id
        assert "created_at" in user_data


class TestCompleteOnboarding:
    """PATCH /api/v1/users/me/onboarding"""

    async def test_complete_onboarding_sets_flag_false(
        self, authed_client, authed_user: User, db_session: AsyncSession
    ):
        """PATCH /me/onboarding sets is_first_login=False."""
        response = await authed_client.patch(ONBOARDING_URL, json={})
        assert response.status_code == 200
        assert response.json() == {"success": True}

        # Verify via GET /me
        resp = await authed_client.get(USER_ME_URL)
        assert resp.json()["user"]["is_first_login"] is False

    async def test_complete_onboarding_with_workspace_rename(
        self, authed_client, authed_user: User, db_session: AsyncSession
    ):
        """PATCH /me/onboarding with workspace_name renames the workspace."""
        from storico.application.workspaces.create_workspace import CreateWorkspaceUseCase
        from storico.infrastructure.database.repositories.workspace_member_repository import (
            SQLAlchemyWorkspaceMemberRepository,
        )
        from storico.infrastructure.database.repositories.workspace_prompt_repository import (
            SQLAlchemyWorkspacePromptRepository,
        )

        ws_repo = SQLAlchemyWorkspaceRepository(db_session)
        member_repo = SQLAlchemyWorkspaceMemberRepository(db_session)
        prompt_repo = SQLAlchemyWorkspacePromptRepository(db_session)

        use_case = CreateWorkspaceUseCase(
            ws_repo=ws_repo, member_repo=member_repo, prompt_repo=prompt_repo
        )
        await use_case.execute(name=f"{authed_user.name}'s Workspace", user_id=authed_user.id)

        response = await authed_client.patch(ONBOARDING_URL, json={"workspace_name": "My Team"})
        assert response.status_code == 200
        assert response.json() == {"success": True}

        # Verify workspace renamed
        workspaces = await ws_repo.list_by_user(authed_user.id)
        assert len(workspaces) == 1
        assert workspaces[0].name == "My Team"

    async def test_complete_onboarding_idempotent(self, authed_client):
        """PATCH /me/onboarding returns 200 on second call — idempotent."""
        # First call
        resp1 = await authed_client.patch(ONBOARDING_URL, json={})
        assert resp1.status_code == 200

        # Second call — idempotent
        resp2 = await authed_client.patch(ONBOARDING_URL, json={})
        assert resp2.status_code == 200

        # is_first_login remains false
        resp = await authed_client.get(USER_ME_URL)
        assert resp.json()["user"]["is_first_login"] is False

    async def test_complete_onboarding_unauthorized(self, async_client):
        """PATCH /me/onboarding without auth returns 401."""
        response = await async_client.patch(ONBOARDING_URL, json={})
        assert response.status_code == 401
