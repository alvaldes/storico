"""error_code coverage for the workspace CRUD routes (WU3b).

Two sites in ``api/routes/workspaces.py`` carry codes as of the error-envelope
feature: a colliding slug on ``PUT /{id}`` and the immutable owner role on
``PUT /{id}/members/{user_id}``. Neither path had any prior coverage, so these
tests are new rather than assertions added to existing prose checks.

Route-level tests over the real app (httpx over ASGITransport, in-memory
SQLite): no Docker, no external services.
"""

import pytest

from tests._helpers import create_workspace

pytestmark = pytest.mark.unit


async def test_workspace_slug_collision_carries_its_code(
    authed_client, authed_user, db_session, seed_workspace
):
    """PUT with another workspace's slug returns 409 with ``WORKSPACE_SLUG_TAKEN``.

    The prose keeps the colliding slug inside it (interpolation stays in
    ``detail``), so the assertion below also pins that the slug survives.
    """
    first = await seed_workspace(stories=0)

    # A workspace the caller owns, created directly with a known slug: the
    # collision target. ``seed_workspace`` would work too, but reading its slug
    # back would need a repository round-trip; here the slug is chosen, not
    # discovered.
    await create_workspace(
        db_session, name="Collision Workspace", slug="taken-slug", owner_id=authed_user.id
    )

    response = await authed_client.put(
        f"/api/v1/workspaces/{first.workspace_id}",
        json={"slug": "taken-slug"},
    )
    body = response.json()

    assert response.status_code == 409
    assert body["error_code"] == "WORKSPACE_SLUG_TAKEN"
    assert "taken-slug" in body["detail"]


async def test_owner_role_change_is_rejected_with_its_code(
    authed_client, authed_user, db_session, seed_workspace
):
    """PUT on the owner's own membership returns 400 with ``OWNER_ROLE_IMMUTABLE``.

    ``seed_workspace`` makes ``authed_user`` both owner and ADMIN member, so the
    request passes ``require_admin`` and reaches the owner check — the exact
    path the guard exists for.
    """
    seeded = await seed_workspace(stories=0)

    response = await authed_client.put(
        f"/api/v1/workspaces/{seeded.workspace_id}/members/{authed_user.id}",
        json={"role": "member"},
    )
    body = response.json()

    assert response.status_code == 400
    assert body["error_code"] == "OWNER_ROLE_IMMUTABLE"
    assert body["detail"] == (
        "The workspace owner's role cannot be changed. Transfer ownership first."
    )
