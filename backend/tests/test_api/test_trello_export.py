"""API tests for the Trello export routes.

``POST /api/v1/workspaces/{workspace_id}/export/trello`` answers ``202`` with a
persisted pending job any member may trigger (D7 — the credentials are what is
admin-only, not the export), and ``GET .../export/trello/{export_id}`` answers
the job's state, board URL and error code. A workspace with no Trello
credentials answers a coded ``409``, never a ``500``.
"""

import asyncio
from collections.abc import Iterator
from dataclasses import replace
from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from storico.config.settings import _reset_settings_cache
from storico.domain.entities.project import Project
from storico.domain.entities.trello_export import (
    TrelloExport,
    TrelloExportStatus,
)
from storico.domain.entities.user_story import UserStory
from storico.domain.entities.workspace_member import WorkspaceRole
from storico.domain.entities.workspace_trello_config import WorkspaceTrelloConfig
from storico.infrastructure.crypto import FernetCipher
from storico.infrastructure.database.models import TrelloExportModel
from storico.infrastructure.database.repositories import (
    SQLAlchemyProjectRepository,
    SQLAlchemyUserStoryRepository,
)
from storico.infrastructure.database.repositories.trello_export_repository import (
    SQLAlchemyTrelloExportRepository,
)
from storico.infrastructure.database.repositories.workspace_trello_config_repository import (
    SQLAlchemyWorkspaceTrelloConfigRepository,
)
from tests._helpers import create_workspace
from tests.conftest import make_jwt_headers

_MASTER_KEY = Fernet.generate_key().decode("ascii")

_API_KEY = "trello-key-abc"
_TOKEN = "trello-token-xyz"


@pytest.fixture(autouse=True)
def _master_key(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Give the app a master key and force Settings to re-read it.

    The cache reset is what makes the fixture work inside the full suite: a
    Settings instance loaded by an earlier test (with no key in the env) would
    otherwise be served to this module's app, and the cipher would refuse to
    decrypt the pair these tests seed.
    """
    monkeypatch.setenv("STORICO_ENCRYPTION_KEY", _MASTER_KEY)
    _reset_settings_cache()
    yield
    _reset_settings_cache()


def _config_repo(session: AsyncSession) -> SQLAlchemyWorkspaceTrelloConfigRepository:
    return SQLAlchemyWorkspaceTrelloConfigRepository(session, FernetCipher(_MASTER_KEY))


async def _seed_credentials(session: AsyncSession, workspace_id: UUID) -> None:
    await _config_repo(session).upsert(
        WorkspaceTrelloConfig(workspace_id=workspace_id, api_key=_API_KEY, token=_TOKEN)
    )


async def _headers_for(db_session: AsyncSession, user_id) -> dict:
    return make_jwt_headers(str(user_id))


@pytest.fixture
def export_repo(db_session: AsyncSession) -> SQLAlchemyTrelloExportRepository:
    return SQLAlchemyTrelloExportRepository(db_session)


# ── POST: the trigger gate and the scope ─────────────────────────────


class TestPostTrelloExport:
    @pytest.mark.asyncio
    async def test_a_member_may_trigger_and_gets_a_pending_job(
        self, authed_client, db_session: AsyncSession, seed_workspace, monkeypatch, export_repo
    ) -> None:
        seeded = await seed_workspace(role=WorkspaceRole.MEMBER)
        await _seed_credentials(db_session, seeded.workspace_id)
        scheduled = AsyncMock()
        monkeypatch.setattr("storico.api.routes.export.run_trello_export", scheduled)

        response = await authed_client.post(
            f"/api/v1/workspaces/{seeded.workspace_id}/export/trello", json={}
        )

        assert response.status_code == 202
        body = response.json()
        assert body["status"] == "pending"
        assert body["scope"] == "workspace"

        job = await export_repo.find_by_id(UUID(body["id"]))
        assert job is not None
        assert job.status.value == "pending"
        assert job.workspace_id == seeded.workspace_id

        await asyncio.sleep(0)
        scheduled.assert_called_once()
        kwargs = scheduled.call_args.kwargs
        assert kwargs["export_id"] == job.id
        assert kwargs["credentials"].api_key == _API_KEY
        assert kwargs["credentials"].token == _TOKEN

    @pytest.mark.asyncio
    async def test_no_credentials_answers_409_never_500(
        self, authed_client, db_session: AsyncSession, seed_workspace, monkeypatch, export_repo
    ) -> None:
        seeded = await seed_workspace()
        scheduled = AsyncMock()
        monkeypatch.setattr("storico.api.routes.export.run_trello_export", scheduled)

        response = await authed_client.post(
            f"/api/v1/workspaces/{seeded.workspace_id}/export/trello", json={}
        )

        assert response.status_code == 409
        assert response.json()["error_code"] == "TRELLO_CREDENTIALS_MISSING"
        scheduled.assert_not_called()
        # Nothing was created: there is nothing to poll.
        rows = (await db_session.execute(select(TrelloExportModel))).scalars().all()
        assert rows == []

    @pytest.mark.asyncio
    async def test_half_a_credential_pair_is_not_configured(
        self, authed_client, db_session: AsyncSession, seed_workspace, monkeypatch, export_repo
    ) -> None:
        seeded = await seed_workspace()
        await _config_repo(db_session).upsert(
            WorkspaceTrelloConfig(workspace_id=seeded.workspace_id, api_key=_API_KEY, token=None)
        )
        monkeypatch.setattr(
            "storico.api.routes.export.run_trello_export",
            AsyncMock(),
        )

        response = await authed_client.post(
            f"/api/v1/workspaces/{seeded.workspace_id}/export/trello", json={}
        )

        assert response.status_code == 409
        assert response.json()["error_code"] == "TRELLO_CREDENTIALS_MISSING"

    @pytest.mark.asyncio
    async def test_two_targets_answer_422(
        self, authed_client, db_session: AsyncSession, seed_workspace, monkeypatch, export_repo
    ) -> None:
        seeded = await seed_workspace()
        await _seed_credentials(db_session, seeded.workspace_id)
        monkeypatch.setattr(
            "storico.api.routes.export.run_trello_export",
            AsyncMock(),
        )

        response = await authed_client.post(
            f"/api/v1/workspaces/{seeded.workspace_id}/export/trello",
            json={
                "project_id": str(seeded.project_id),
                "user_story_id": str(seeded.story_id),
            },
        )

        assert response.status_code == 422
        assert response.json()["error_code"] == "REQUEST_VALIDATION_FAILED"

    @pytest.mark.asyncio
    async def test_project_scope_persists_the_target(
        self, authed_client, db_session: AsyncSession, seed_workspace, monkeypatch, export_repo
    ) -> None:
        seeded = await seed_workspace()
        await _seed_credentials(db_session, seeded.workspace_id)
        monkeypatch.setattr(
            "storico.api.routes.export.run_trello_export",
            AsyncMock(),
        )

        response = await authed_client.post(
            f"/api/v1/workspaces/{seeded.workspace_id}/export/trello",
            json={"project_id": str(seeded.project_id)},
        )

        assert response.status_code == 202
        job = await export_repo.find_by_id(UUID(response.json()["id"]))
        assert job is not None
        assert job.scope.value == "project"
        assert job.project_id == seeded.project_id

    @pytest.mark.asyncio
    async def test_story_scope_persists_the_target(
        self, authed_client, db_session: AsyncSession, seed_workspace, monkeypatch, export_repo
    ) -> None:
        seeded = await seed_workspace()
        await _seed_credentials(db_session, seeded.workspace_id)
        monkeypatch.setattr(
            "storico.api.routes.export.run_trello_export",
            AsyncMock(),
        )

        response = await authed_client.post(
            f"/api/v1/workspaces/{seeded.workspace_id}/export/trello",
            json={"user_story_id": str(seeded.story_id)},
        )

        assert response.status_code == 202
        job = await export_repo.find_by_id(UUID(response.json()["id"]))
        assert job is not None
        assert job.scope.value == "story"
        assert job.user_story_id == seeded.story_id

    @pytest.mark.asyncio
    async def test_an_unknown_story_id_is_a_miss(
        self, authed_client, db_session: AsyncSession, seed_workspace, monkeypatch, export_repo
    ) -> None:
        seeded = await seed_workspace()
        await _seed_credentials(db_session, seeded.workspace_id)
        monkeypatch.setattr(
            "storico.api.routes.export.run_trello_export",
            AsyncMock(),
        )

        response = await authed_client.post(
            f"/api/v1/workspaces/{seeded.workspace_id}/export/trello",
            json={"user_story_id": str(uuid4())},
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_a_foreign_project_is_refused(
        self, authed_client, db_session: AsyncSession, seed_workspace, monkeypatch, export_repo
    ) -> None:
        seeded = await seed_workspace()
        await _seed_credentials(db_session, seeded.workspace_id)
        other = await create_workspace(
            db_session, name="Other WS", slug=f"other-{uuid4().hex[:8]}", owner_id=uuid4()
        )
        other_project = await SQLAlchemyProjectRepository(db_session).save(
            Project(name="Other Project", workspace_id=other.id)
        )
        monkeypatch.setattr(
            "storico.api.routes.export.run_trello_export",
            AsyncMock(),
        )

        response = await authed_client.post(
            f"/api/v1/workspaces/{seeded.workspace_id}/export/trello",
            json={"project_id": str(other_project.id)},
        )

        assert response.status_code == 403
        assert response.json()["error_code"] == "PROJECT_NOT_IN_WORKSPACE"

    @pytest.mark.asyncio
    async def test_a_story_of_another_project_in_this_workspace_resolves_to_its_workspace(
        self, authed_client, db_session: AsyncSession, seed_workspace, monkeypatch, export_repo
    ) -> None:
        """A story id is only honored when its own project sits in the path workspace."""
        seeded = await seed_workspace()
        await _seed_credentials(db_session, seeded.workspace_id)
        story = await SQLAlchemyUserStoryRepository(db_session).save(
            UserStory(
                project_id=seeded.project_id,
                actor="user",
                feature="log in",
                benefit="access account",
                raw_text="As a user, I want to log in",
            )
        )
        monkeypatch.setattr(
            "storico.api.routes.export.run_trello_export",
            AsyncMock(),
        )

        response = await authed_client.post(
            f"/api/v1/workspaces/{seeded.workspace_id}/export/trello",
            json={"user_story_id": str(story.id)},
        )

        assert response.status_code == 202

    @pytest.mark.asyncio
    async def test_a_non_member_is_refused(
        self, authed_client, db_session: AsyncSession, seed_workspace
    ) -> None:
        seeded = await seed_workspace(member=False)

        response = await authed_client.post(
            f"/api/v1/workspaces/{seeded.workspace_id}/export/trello", json={}
        )

        assert response.status_code == 403
        assert response.json()["error_code"] == "NOT_A_WORKSPACE_MEMBER"


# ── GET: polling the job ─────────────────────────────────────────────


class TestGetTrelloExport:
    @pytest.mark.asyncio
    async def test_polling_reports_the_job_state(
        self, authed_client, db_session: AsyncSession, seed_workspace, export_repo
    ) -> None:
        seeded = await seed_workspace()
        job = await export_repo.save(TrelloExport(workspace_id=seeded.workspace_id))

        response = await authed_client.get(
            f"/api/v1/workspaces/{seeded.workspace_id}/export/trello/{job.id}"
        )

        assert response.status_code == 200
        body = response.json()
        assert body["id"] == str(job.id)
        assert body["status"] == "pending"
        assert body["board_url"] is None
        assert body["error_code"] is None

    @pytest.mark.asyncio
    async def test_a_failed_job_reports_error_code_and_board_url(
        self, authed_client, db_session: AsyncSession, seed_workspace, export_repo
    ) -> None:
        seeded = await seed_workspace()
        job = await export_repo.save(
            replace(
                TrelloExport(workspace_id=seeded.workspace_id),
                status=TrelloExportStatus.FAILED,
                error_code="TRELLO_CARD_REFUSED",
                board_id="board-1",
                board_url="https://trello.com/b/board-1",
                completed_at=datetime.now(UTC),
            )
        )

        response = await authed_client.get(
            f"/api/v1/workspaces/{seeded.workspace_id}/export/trello/{job.id}"
        )

        body = response.json()
        assert body["status"] == "failed"
        assert body["error_code"] == "TRELLO_CARD_REFUSED"
        assert body["board_url"] == "https://trello.com/b/board-1"

    @pytest.mark.asyncio
    async def test_unknown_export_id_answers_404(
        self, authed_client, db_session: AsyncSession, seed_workspace
    ) -> None:
        seeded = await seed_workspace()

        response = await authed_client.get(
            f"/api/v1/workspaces/{seeded.workspace_id}/export/trello/{uuid4()}"
        )

        assert response.status_code == 404
        assert response.json()["error_code"] == "TRELLO_EXPORT_NOT_FOUND"

    @pytest.mark.asyncio
    async def test_another_workspaces_job_is_not_readable(
        self, authed_client, db_session: AsyncSession, seed_workspace, export_repo
    ) -> None:
        seeded = await seed_workspace()
        other = await create_workspace(
            db_session, name="Other WS", slug=f"other-{uuid4().hex[:8]}", owner_id=uuid4()
        )
        foreign_job = await export_repo.save(TrelloExport(workspace_id=other.id))

        response = await authed_client.get(
            f"/api/v1/workspaces/{seeded.workspace_id}/export/trello/{foreign_job.id}"
        )

        assert response.status_code == 404
