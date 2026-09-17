"""Integration tests for workspace prompt config — FR-CONFIG-1..5.

Covers the few-shot retrieval configuration columns exposed through
``/api/v1/workspaces/{workspace_id}/settings/prompts``.
"""

from __future__ import annotations

import jwt as pyjwt
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from storico.config.settings import Settings
from storico.domain.entities.user import User
from storico.domain.entities.workspace_member import WorkspaceRole
from storico.infrastructure.database.repositories import SQLAlchemyUserRepository


def _auth_headers(user_id: str) -> dict:
    """Generate JWT auth headers."""
    secret = Settings.load().auth_jwt_secret
    token = pyjwt.encode({"sub": user_id}, secret, algorithm="HS256")
    return {"Authorization": f"Bearer {token}"}


async def _create_user(db_session: AsyncSession, email: str = "config@test.com") -> User:
    """Create a user in the test database."""
    repo = SQLAlchemyUserRepository(db_session)
    user = User(email=email, name="Config Test")
    saved = await repo.save(user)
    await repo.link_account(saved.id, "google", f"g-{email}")
    return saved


@pytest.mark.integration
class TestWorkspacePromptConfig:
    """Workspace prompt config read/write with admin-only authorization."""

    @pytest.mark.asyncio
    async def test_read_defaults_with_no_row(
        self, async_client, db_session, seed_workspace
    ) -> None:
        """S-CONFIG-1: no prompt row → enabled true, limit 3, threshold 0.85."""
        user = await _create_user(db_session)
        ws_id = (await seed_workspace(user=user, stories=0)).workspace_id

        response = await async_client.get(
            f"/api/v1/workspaces/{ws_id}/settings/prompts",
            headers=_auth_headers(str(user.id)),
        )
        assert response.status_code == 200
        data = response.json()
        assert data["few_shot_enabled"] is True
        assert data["few_shot_limit"] == 3
        assert data["few_shot_threshold"] == 0.85

    @pytest.mark.asyncio
    async def test_update_config_is_persisted(
        self, async_client, db_session, seed_workspace
    ) -> None:
        """S-CONFIG-2: PUT {enabled:false, limit:5, threshold:0.9} then GET returns them."""
        user = await _create_user(db_session)
        ws_id = (await seed_workspace(user=user, stories=0)).workspace_id

        put_resp = await async_client.put(
            f"/api/v1/workspaces/{ws_id}/settings/prompts",
            json={"few_shot_enabled": False, "few_shot_limit": 5, "few_shot_threshold": 0.9},
            headers=_auth_headers(str(user.id)),
        )
        assert put_resp.status_code == 200
        body = put_resp.json()
        assert body["few_shot_enabled"] is False
        assert body["few_shot_limit"] == 5
        assert body["few_shot_threshold"] == 0.9

        get_resp = await async_client.get(
            f"/api/v1/workspaces/{ws_id}/settings/prompts",
            headers=_auth_headers(str(user.id)),
        )
        assert get_resp.status_code == 200
        data = get_resp.json()
        assert data["few_shot_enabled"] is False
        assert data["few_shot_limit"] == 5
        assert data["few_shot_threshold"] == 0.9

    @pytest.mark.asyncio
    async def test_validation_rejects_out_of_range(
        self, async_client, db_session, seed_workspace
    ) -> None:
        """S-CONFIG-3: limit=0 and threshold=1.5 fail with 422 and persist nothing."""
        user = await _create_user(db_session)
        ws_id = (await seed_workspace(user=user, stories=0)).workspace_id

        limit_resp = await async_client.put(
            f"/api/v1/workspaces/{ws_id}/settings/prompts",
            json={"few_shot_limit": 0},
            headers=_auth_headers(str(user.id)),
        )
        assert limit_resp.status_code == 422

        threshold_resp = await async_client.put(
            f"/api/v1/workspaces/{ws_id}/settings/prompts",
            json={"few_shot_threshold": 1.5},
            headers=_auth_headers(str(user.id)),
        )
        assert threshold_resp.status_code == 422

        # A later GET still shows the defaults (nothing was persisted).
        get_resp = await async_client.get(
            f"/api/v1/workspaces/{ws_id}/settings/prompts",
            headers=_auth_headers(str(user.id)),
        )
        assert get_resp.status_code == 200
        data = get_resp.json()
        assert data["few_shot_limit"] == 3
        assert data["few_shot_threshold"] == 0.85

    @pytest.mark.asyncio
    async def test_authorization_non_admin_403(
        self, async_client, db_session, seed_workspace
    ) -> None:
        """S-CONFIG-4: a non-admin member cannot update the config."""
        user = await _create_user(db_session)
        ws_id = (await seed_workspace(user=user, stories=0, role=WorkspaceRole.MEMBER)).workspace_id

        response = await async_client.put(
            f"/api/v1/workspaces/{ws_id}/settings/prompts",
            json={"few_shot_enabled": False},
            headers=_auth_headers(str(user.id)),
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_legacy_few_shot_examples_rejected_422(
        self, async_client, db_session, seed_workspace
    ) -> None:
        """S-CONFIG-5: posting the legacy few_shot_examples field is rejected."""
        user = await _create_user(db_session)
        ws_id = (await seed_workspace(user=user, stories=0)).workspace_id

        response = await async_client.put(
            f"/api/v1/workspaces/{ws_id}/settings/prompts",
            json={
                "few_shot_examples": [
                    {
                        "user_story": "As a user, I want login",
                        "tasks": "1. summary: T\ndescription: D",
                    }
                ]
            },
            headers=_auth_headers(str(user.id)),
        )
        assert response.status_code == 422
