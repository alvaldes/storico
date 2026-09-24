"""Integration tests for the workspace custom provider registry API.

Covers ``/api/v1/workspaces/{workspace_id}/settings/providers``: the
workspace-scoped registry that keeps one workspace's provider names out of
another's, its admin-only surface, the name rules, and the rename that has to
follow the workspace's own provider selection.
"""

from __future__ import annotations

from datetime import UTC, datetime

import jwt as pyjwt
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from storico.config.settings import Settings
from storico.domain.entities.user import User
from storico.domain.entities.workspace_member import WorkspaceRole
from storico.infrastructure.database.models import CustomProviderModel
from storico.infrastructure.database.repositories import SQLAlchemyUserRepository


def _auth_headers(user_id: str) -> dict:
    """Generate JWT auth headers."""
    secret = Settings.load().auth_jwt_secret
    token = pyjwt.encode({"sub": user_id}, secret, algorithm="HS256")
    return {"Authorization": f"Bearer {token}"}


async def _create_user(db_session: AsyncSession, email: str = "providers@test.com") -> User:
    """Create a user in the test database."""
    repo = SQLAlchemyUserRepository(db_session)
    user = User(email=email, name="Providers Test")
    saved = await repo.save(user)
    await repo.link_account(saved.id, "google", f"g-{email}")
    return saved


def _providers_url(workspace_id) -> str:
    return f"/api/v1/workspaces/{workspace_id}/settings/providers"


def _llm_url(workspace_id) -> str:
    return f"/api/v1/workspaces/{workspace_id}/settings/llm"


async def _seed(seed_workspace, user: User, role: WorkspaceRole = WorkspaceRole.ADMIN):
    """Seed an accessible workspace for ``user`` with the given role."""
    return await seed_workspace(user=user, stories=0, role=role)


async def _seed_legacy_row(
    db_session: AsyncSession, workspace_id, name: str
) -> CustomProviderModel:
    """Insert the row migration 0021 would have backfilled, bypassing the name rule.

    The API cannot create this row: the name is reserved now. The migration could,
    because it compares against the built-in names by exact match — so a stored
    ``Ollama`` became a row named ``Ollama``.
    """
    now = datetime.now(UTC)
    row = CustomProviderModel(workspace_id=workspace_id, name=name, created_at=now, updated_at=now)
    db_session.add(row)
    await db_session.commit()
    await db_session.refresh(row)
    return row


@pytest.mark.integration
class TestCustomProviderRegistry:
    """Workspace-scoped provider registration with admin-only authorization."""

    @pytest.mark.asyncio
    async def test_list_is_empty_for_a_fresh_workspace(
        self, async_client, db_session, seed_workspace
    ) -> None:
        """A workspace that registered nothing lists nothing."""
        user = await _create_user(db_session)
        ws_id = (await _seed(seed_workspace, user)).workspace_id

        response = await async_client.get(
            _providers_url(ws_id), headers=_auth_headers(str(user.id))
        )

        assert response.status_code == 200
        assert response.json() == []

    @pytest.mark.asyncio
    async def test_create_then_list_returns_the_row(
        self, async_client, db_session, seed_workspace
    ) -> None:
        """A created provider is returned in full and reads back from the list."""
        user = await _create_user(db_session)
        ws_id = (await _seed(seed_workspace, user)).workspace_id

        created = await async_client.post(
            _providers_url(ws_id),
            json={"name": "deepseek"},
            headers=_auth_headers(str(user.id)),
        )
        assert created.status_code == 201
        body = created.json()
        assert body["name"] == "deepseek"
        assert body["workspace_id"] == str(ws_id)
        assert body["id"]
        assert body["created_at"] and body["updated_at"]

        listed = await async_client.get(_providers_url(ws_id), headers=_auth_headers(str(user.id)))
        assert listed.status_code == 200
        assert [p["name"] for p in listed.json()] == ["deepseek"]

    @pytest.mark.asyncio
    async def test_padding_is_trimmed_and_casing_is_kept(
        self, async_client, db_session, seed_workspace
    ) -> None:
        """The stored name is what the user typed, minus the surrounding padding."""
        user = await _create_user(db_session)
        ws_id = (await _seed(seed_workspace, user)).workspace_id

        created = await async_client.post(
            _providers_url(ws_id),
            json={"name": "  Groq  "},
            headers=_auth_headers(str(user.id)),
        )

        assert created.status_code == 201
        assert created.json()["name"] == "Groq"

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "name", ["Groq", "has space", "Ünïcode", "-leading", "UPPER!", "My Gateway v2"]
    )
    async def test_free_form_names_are_stored_verbatim(
        self, async_client, db_session, seed_workspace, name: str
    ) -> None:
        """Only emptiness and the 50-character cap constrain the name.

        Routing does not need a slug: ``_build_llm_port`` sends every name outside
        the four built-ins to the OpenAI-compatible adapter.
        """
        user = await _create_user(db_session)
        ws_id = (await _seed(seed_workspace, user)).workspace_id

        created = await async_client.post(
            _providers_url(ws_id),
            json={"name": name},
            headers=_auth_headers(str(user.id)),
        )

        assert created.status_code == 201
        assert created.json()["name"] == name

    @pytest.mark.asyncio
    async def test_the_50_character_cap_measures_the_stored_name(
        self, async_client, db_session, seed_workspace
    ) -> None:
        """Padding around a 50-character name is trimmed before it is measured.

        The cap has to live in the validator, not in a raw ``max_length`` on the
        field, or this padded name would be refused for being 54 characters long
        while the name that gets stored is exactly at the limit.
        """
        user = await _create_user(db_session)
        ws_id = (await _seed(seed_workspace, user)).workspace_id
        name = "a" * 50

        created = await async_client.post(
            _providers_url(ws_id),
            json={"name": f"  {name}  "},
            headers=_auth_headers(str(user.id)),
        )

        assert created.status_code == 201
        assert created.json()["name"] == name

    @pytest.mark.asyncio
    async def test_names_that_differ_only_in_case_both_exist(
        self, async_client, db_session, seed_workspace
    ) -> None:
        """Identity is case-sensitive: ``Groq`` and ``groq`` are two providers.

        The user's approved rule. The DB constraint is ``UNIQUE (workspace_id,
        name)``, so this needs no migration and no lower-cased comparison.
        """
        user = await _create_user(db_session)
        ws_id = (await _seed(seed_workspace, user)).workspace_id
        headers = _auth_headers(str(user.id))

        first = await async_client.post(
            _providers_url(ws_id), json={"name": "Groq"}, headers=headers
        )
        second = await async_client.post(
            _providers_url(ws_id), json={"name": "groq"}, headers=headers
        )
        listed = await async_client.get(_providers_url(ws_id), headers=headers)

        assert first.status_code == 201
        assert second.status_code == 201
        assert [p["name"] for p in listed.json()] == ["Groq", "groq"]

    @pytest.mark.asyncio
    async def test_create_requires_admin(self, async_client, db_session, seed_workspace) -> None:
        """A member cannot register a provider."""
        user = await _create_user(db_session)
        ws_id = (await _seed(seed_workspace, user, role=WorkspaceRole.MEMBER)).workspace_id

        response = await async_client.post(
            _providers_url(ws_id),
            json={"name": "deepseek"},
            headers=_auth_headers(str(user.id)),
        )

        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_list_requires_admin(self, async_client, db_session, seed_workspace) -> None:
        """A member cannot enumerate the registry."""
        user = await _create_user(db_session)
        ws_id = (await _seed(seed_workspace, user, role=WorkspaceRole.MEMBER)).workspace_id

        response = await async_client.get(
            _providers_url(ws_id), headers=_auth_headers(str(user.id))
        )

        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_duplicate_name_conflicts(self, async_client, db_session, seed_workspace) -> None:
        """A workspace cannot register the same name twice."""
        user = await _create_user(db_session)
        ws_id = (await _seed(seed_workspace, user)).workspace_id
        headers = _auth_headers(str(user.id))
        await async_client.post(_providers_url(ws_id), json={"name": "groq"}, headers=headers)

        second = await async_client.post(
            _providers_url(ws_id), json={"name": "groq"}, headers=headers
        )

        assert second.status_code == 409

    @pytest.mark.asyncio
    async def test_the_same_name_is_allowed_in_two_workspaces(
        self, async_client, db_session, seed_workspace
    ) -> None:
        """Registry rows are per workspace, so a shared vendor name is not a conflict."""
        user = await _create_user(db_session)
        headers = _auth_headers(str(user.id))
        first = (await _seed(seed_workspace, user)).workspace_id
        second = (await _seed(seed_workspace, user)).workspace_id

        first_response = await async_client.post(
            _providers_url(first), json={"name": "groq"}, headers=headers
        )
        second_response = await async_client.post(
            _providers_url(second), json={"name": "groq"}, headers=headers
        )

        assert first_response.status_code == 201
        assert second_response.status_code == 201

    @pytest.mark.asyncio
    async def test_registry_is_not_shared_between_workspaces(
        self, async_client, db_session, seed_workspace
    ) -> None:
        """A row registered in one workspace never appears in another's list."""
        user = await _create_user(db_session)
        headers = _auth_headers(str(user.id))
        first = (await _seed(seed_workspace, user)).workspace_id
        second = (await _seed(seed_workspace, user)).workspace_id
        await async_client.post(_providers_url(first), json={"name": "groq"}, headers=headers)

        listed = await async_client.get(_providers_url(second), headers=headers)

        assert listed.status_code == 200
        assert listed.json() == []

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "name",
        ["ollama", "openai", "anthropic", "gemini", "OLLAMA", "OpenAI", "Gemini"],
    )
    async def test_known_provider_names_are_rejected(
        self, async_client, db_session, seed_workspace, name: str
    ) -> None:
        """A first-class provider has its own branch, so it is not a custom entry.

        Casing does not open a side door: a custom provider named ``OpenAI`` would
        sit beside the built-in entry in the select while routing somewhere else.
        """
        user = await _create_user(db_session)
        ws_id = (await _seed(seed_workspace, user)).workspace_id

        response = await async_client.post(
            _providers_url(ws_id),
            json={"name": name},
            headers=_auth_headers(str(user.id)),
        )

        assert response.status_code == 409

    @pytest.mark.asyncio
    async def test_the_select_s_control_value_is_rejected(
        self, async_client, db_session, seed_workspace
    ) -> None:
        """``__add_custom_provider__`` is a control, not a provider name.

        It travels through the select's value, so a provider registered under it
        would occupy the "Add custom provider…" slot and be unselectable. The old
        slug pattern kept it out by forbidding a leading underscore; that accident
        is gone, so the guard is explicit.
        """
        user = await _create_user(db_session)
        ws_id = (await _seed(seed_workspace, user)).workspace_id

        response = await async_client.post(
            _providers_url(ws_id),
            json={"name": "__add_custom_provider__"},
            headers=_auth_headers(str(user.id)),
        )

        assert response.status_code == 409

    @pytest.mark.asyncio
    @pytest.mark.parametrize("name", ["", "   ", "a" * 51])
    async def test_invalid_names_are_rejected(
        self, async_client, db_session, seed_workspace, name: str
    ) -> None:
        """An empty name and one over the cap are refused before the database."""
        user = await _create_user(db_session)
        ws_id = (await _seed(seed_workspace, user)).workspace_id

        response = await async_client.post(
            _providers_url(ws_id),
            json={"name": name},
            headers=_auth_headers(str(user.id)),
        )

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_renaming_a_legacy_reserved_row_to_itself_is_a_no_op(
        self, async_client, db_session, seed_workspace
    ) -> None:
        """A row registered before the case-insensitive guard can submit its own name.

        Migration 0021 backfilled one row per config whose provider was not one of
        the four names, by exact match: a stored ``Ollama`` became a row named
        ``Ollama``. Refusing that row's unchanged submit would break the admin's only
        rename affordance for it, so the no-op is answered before the reservation.
        """
        user = await _create_user(db_session)
        ws_id = (await _seed(seed_workspace, user)).workspace_id
        headers = _auth_headers(str(user.id))
        legacy = await _seed_legacy_row(db_session, ws_id, "Ollama")

        renamed = await async_client.patch(
            f"{_providers_url(ws_id)}/{legacy.id}",
            json={"name": "Ollama"},
            headers=headers,
        )

        assert renamed.status_code == 200
        assert renamed.json()["name"] == "Ollama"

    @pytest.mark.asyncio
    async def test_a_legacy_reserved_row_can_still_be_renamed_away_and_not_into(
        self, async_client, db_session, seed_workspace
    ) -> None:
        """The reservation still binds a row that carries a reserved name."""
        user = await _create_user(db_session)
        ws_id = (await _seed(seed_workspace, user)).workspace_id
        headers = _auth_headers(str(user.id))
        legacy = await _seed_legacy_row(db_session, ws_id, "Ollama")

        into_reserved = await async_client.patch(
            f"{_providers_url(ws_id)}/{legacy.id}",
            json={"name": "ollama"},
            headers=headers,
        )
        away = await async_client.patch(
            f"{_providers_url(ws_id)}/{legacy.id}",
            json={"name": "Ollama remote"},
            headers=headers,
        )

        assert into_reserved.status_code == 409
        assert away.status_code == 200
        assert away.json()["name"] == "Ollama remote"

    @pytest.mark.asyncio
    async def test_rename_returns_the_new_name(
        self, async_client, db_session, seed_workspace
    ) -> None:
        """A rename changes the row in place and reads back from the list."""
        user = await _create_user(db_session)
        ws_id = (await _seed(seed_workspace, user)).workspace_id
        headers = _auth_headers(str(user.id))
        created = await async_client.post(
            _providers_url(ws_id), json={"name": "grok"}, headers=headers
        )

        renamed = await async_client.patch(
            f"{_providers_url(ws_id)}/{created.json()['id']}",
            json={"name": "groq"},
            headers=headers,
        )

        assert renamed.status_code == 200
        assert renamed.json()["id"] == created.json()["id"]
        assert renamed.json()["name"] == "groq"
        listed = await async_client.get(_providers_url(ws_id), headers=headers)
        assert [p["name"] for p in listed.json()] == ["groq"]

    @pytest.mark.asyncio
    async def test_rename_to_the_same_name_is_a_no_op(
        self, async_client, db_session, seed_workspace
    ) -> None:
        """Resubmitting the unchanged name must not read as a duplicate."""
        user = await _create_user(db_session)
        ws_id = (await _seed(seed_workspace, user)).workspace_id
        headers = _auth_headers(str(user.id))
        created = await async_client.post(
            _providers_url(ws_id), json={"name": "groq"}, headers=headers
        )

        renamed = await async_client.patch(
            f"{_providers_url(ws_id)}/{created.json()['id']}",
            json={"name": "groq"},
            headers=headers,
        )

        assert renamed.status_code == 200
        assert renamed.json()["name"] == "groq"

    @pytest.mark.asyncio
    async def test_rename_onto_a_sibling_name_conflicts(
        self, async_client, db_session, seed_workspace
    ) -> None:
        """Two rows in one workspace cannot end up with the same name."""
        user = await _create_user(db_session)
        ws_id = (await _seed(seed_workspace, user)).workspace_id
        headers = _auth_headers(str(user.id))
        await async_client.post(_providers_url(ws_id), json={"name": "groq"}, headers=headers)
        second = await async_client.post(
            _providers_url(ws_id), json={"name": "deepseek"}, headers=headers
        )

        renamed = await async_client.patch(
            f"{_providers_url(ws_id)}/{second.json()['id']}",
            json={"name": "groq"},
            headers=headers,
        )

        assert renamed.status_code == 409

    @pytest.mark.asyncio
    @pytest.mark.parametrize("target", ["gemini", "Gemini"])
    async def test_rename_rejects_a_known_provider_name(
        self, async_client, db_session, seed_workspace, target: str
    ) -> None:
        """A rename cannot smuggle in a first-class provider name, in any casing."""
        user = await _create_user(db_session)
        ws_id = (await _seed(seed_workspace, user)).workspace_id
        headers = _auth_headers(str(user.id))
        created = await async_client.post(
            _providers_url(ws_id), json={"name": "groq"}, headers=headers
        )

        renamed = await async_client.patch(
            f"{_providers_url(ws_id)}/{created.json()['id']}",
            json={"name": target},
            headers=headers,
        )

        assert renamed.status_code == 409

    @pytest.mark.asyncio
    async def test_rename_of_an_unknown_id_is_not_found(
        self, async_client, db_session, seed_workspace
    ) -> None:
        """An id that matches no row reports not found."""
        from uuid import uuid4

        user = await _create_user(db_session)
        ws_id = (await _seed(seed_workspace, user)).workspace_id

        renamed = await async_client.patch(
            f"{_providers_url(ws_id)}/{uuid4()}",
            json={"name": "groq"},
            headers=_auth_headers(str(user.id)),
        )

        assert renamed.status_code == 404

    @pytest.mark.asyncio
    @pytest.mark.parametrize("name", ["Gemini", "ollama", "__add_custom_provider__"])
    async def test_an_absent_row_outranks_a_reserved_target_name(
        self, async_client, db_session, seed_workspace, name: str
    ) -> None:
        """A reserved target name is judged only once the row is known to exist.

        The reservation answers "what may a name be registered as", which is not a
        question about a row that does not exist. The repository's contract reads
        ``404`` as "that row does not exist", and ``403`` as "you are not an admin
        for this workspace, or the row exists but is not reachable from the
        workspace in the path" — containment is reported, not collapsed into
        absence. This pins which side of that split the rename path is on.
        """
        from uuid import uuid4

        user = await _create_user(db_session)
        ws_id = (await _seed(seed_workspace, user)).workspace_id

        renamed = await async_client.patch(
            f"{_providers_url(ws_id)}/{uuid4()}",
            json={"name": name},
            headers=_auth_headers(str(user.id)),
        )

        assert renamed.status_code == 404

    @pytest.mark.asyncio
    async def test_rename_reports_a_foreign_provider_as_forbidden(
        self, async_client, db_session, seed_workspace
    ) -> None:
        """A provider id from another workspace is reported as contained, not absent.

        The path declares the workspace, so the row's existence and its
        reachability from that workspace are different facts: the foreign row
        exists, so the rename answers 403 — the same rule ``projects.py`` and
        ``extraction.py`` follow. The anti-probing rationale this path once
        relied on (reporting the foreign id as 404 so it could not be probed for
        existence) was retired on purpose (issue #5, 2026-09-24).
        """
        user = await _create_user(db_session)
        headers = _auth_headers(str(user.id))
        first = (await _seed(seed_workspace, user)).workspace_id
        second = (await _seed(seed_workspace, user)).workspace_id
        foreign = await async_client.post(
            _providers_url(second), json={"name": "groq"}, headers=headers
        )

        renamed = await async_client.patch(
            f"{_providers_url(first)}/{foreign.json()['id']}",
            json={"name": "deepseek"},
            headers=headers,
        )

        assert renamed.status_code == 403
        # The foreign row is untouched — the property that matters for a write path.
        listed = await async_client.get(_providers_url(second), headers=headers)
        assert [p["name"] for p in listed.json()] == ["groq"]

    @pytest.mark.asyncio
    async def test_rename_requires_admin(self, async_client, db_session, seed_workspace) -> None:
        """A member cannot rename a provider."""
        from uuid import uuid4

        user = await _create_user(db_session)
        ws_id = (await _seed(seed_workspace, user, role=WorkspaceRole.MEMBER)).workspace_id

        renamed = await async_client.patch(
            f"{_providers_url(ws_id)}/{uuid4()}",
            json={"name": "groq"},
            headers=_auth_headers(str(user.id)),
        )

        assert renamed.status_code == 403


@pytest.mark.integration
class TestRenameFollowsTheProviderSelection:
    """The selection is stored by name, so a rename of it must carry over."""

    @pytest.mark.asyncio
    async def test_renaming_the_selected_provider_repoints_the_llm_config(
        self, async_client, db_session, seed_workspace
    ) -> None:
        """Renaming the provider in use leaves no dangling selection behind."""
        user = await _create_user(db_session)
        ws_id = (await _seed(seed_workspace, user)).workspace_id
        headers = _auth_headers(str(user.id))
        created = await async_client.post(
            _providers_url(ws_id), json={"name": "deepseek"}, headers=headers
        )
        await async_client.put(_llm_url(ws_id), json={"provider": "deepseek"}, headers=headers)

        renamed = await async_client.patch(
            f"{_providers_url(ws_id)}/{created.json()['id']}",
            json={"name": "groq"},
            headers=headers,
        )
        assert renamed.status_code == 200

        config = await async_client.get(_llm_url(ws_id), headers=headers)
        assert config.json()["provider"] == "groq"

    @pytest.mark.asyncio
    async def test_renaming_another_provider_leaves_the_llm_config_alone(
        self, async_client, db_session, seed_workspace
    ) -> None:
        """Only the selected name is followed; other rows rename independently."""
        user = await _create_user(db_session)
        ws_id = (await _seed(seed_workspace, user)).workspace_id
        headers = _auth_headers(str(user.id))
        await async_client.put(_llm_url(ws_id), json={"provider": "ollama"}, headers=headers)
        created = await async_client.post(
            _providers_url(ws_id), json={"name": "deepseek"}, headers=headers
        )

        renamed = await async_client.patch(
            f"{_providers_url(ws_id)}/{created.json()['id']}",
            json={"name": "groq"},
            headers=headers,
        )
        assert renamed.status_code == 200

        config = await async_client.get(_llm_url(ws_id), headers=headers)
        assert config.json()["provider"] == "ollama"
