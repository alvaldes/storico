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
from storico.domain.entities.extraction import ExtractionStatus
from storico.domain.entities.project import Project
from storico.domain.entities.task import TaskStatus
from storico.domain.entities.trello_export import (
    TrelloExport,
    TrelloExportScope,
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
from tests._helpers import create_workspace, seed_extraction, seed_task
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
    async def test_a_chosen_version_exports_even_when_superseded(
        self, authed_client, db_session: AsyncSession, seed_workspace, monkeypatch, export_repo
    ) -> None:
        """Naming an extraction id exports that version, superseded or not —
        EP1's rule, now on the Trello trigger: the version travels in the
        dispatch kwargs and lands on the job row the member polls."""
        seeded = await seed_workspace()
        await _seed_credentials(db_session, seeded.workspace_id)
        superseded = await seed_extraction(
            db_session,
            seeded.story_id,
            status=ExtractionStatus.COMPLETED,
            completed_at=datetime.now(UTC),
        )
        # A second completed run supersedes the first — the trigger names the old one.
        await seed_extraction(
            db_session,
            seeded.story_id,
            status=ExtractionStatus.COMPLETED,
            completed_at=datetime.now(UTC),
        )
        scheduled = AsyncMock()
        monkeypatch.setattr("storico.api.routes.export.run_trello_export", scheduled)

        response = await authed_client.post(
            f"/api/v1/workspaces/{seeded.workspace_id}/export/trello",
            json={"user_story_id": str(seeded.story_id), "extraction_id": str(superseded.id)},
        )

        assert response.status_code == 202
        assert response.json()["extraction_id"] == str(superseded.id)
        job = await export_repo.find_by_id(UUID(response.json()["id"]))
        assert job is not None
        assert job.extraction_id == superseded.id
        kwargs = scheduled.call_args.kwargs
        assert kwargs["extraction_id"] == superseded.id

    @pytest.mark.asyncio
    async def test_a_version_without_its_story_is_422(
        self, authed_client, db_session: AsyncSession, seed_workspace, monkeypatch, export_repo
    ) -> None:
        """A version belongs to a story: extraction_id alone is refused before
        anything is created or dispatched — the same 422 the file export answers."""
        seeded = await seed_workspace()
        await _seed_credentials(db_session, seeded.workspace_id)
        scheduled = AsyncMock()
        monkeypatch.setattr("storico.api.routes.export.run_trello_export", scheduled)

        response = await authed_client.post(
            f"/api/v1/workspaces/{seeded.workspace_id}/export/trello",
            json={"extraction_id": str(uuid4())},
        )

        assert response.status_code == 422
        assert response.json()["error_code"] == "REQUEST_VALIDATION_FAILED"
        scheduled.assert_not_called()
        rows = (await db_session.execute(select(TrelloExportModel))).scalars().all()
        assert rows == []

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
        """A story id is only honored when its own project sits in the path workspace:
        the story here belongs to a *second* project of the same workspace, and the
        job must still resolve to that workspace."""
        seeded = await seed_workspace()
        await _seed_credentials(db_session, seeded.workspace_id)
        other_project = await SQLAlchemyProjectRepository(db_session).save(
            Project(name="Second Project", workspace_id=seeded.workspace_id)
        )
        story = await SQLAlchemyUserStoryRepository(db_session).save(
            UserStory(
                project_id=other_project.id,
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
        job = await export_repo.find_by_id(UUID(response.json()["id"]))
        assert job is not None
        assert job.scope.value == "story"
        assert job.user_story_id == story.id
        # A story scope must carry the story and *not* a second target — the
        # workspace_id line this replaced was a tautology: the route stamps the
        # path workspace onto the row, so no resolution bug could turn it red.
        assert job.project_id is None

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
    async def test_polling_reports_which_version_the_board_came_from(
        self, authed_client, db_session: AsyncSession, seed_workspace, export_repo
    ) -> None:
        """A member polling a job can say which version that board came from —
        the row records the named extraction, and a job without one reports null."""
        seeded = await seed_workspace()
        version_id = uuid4()
        job = await export_repo.save(
            TrelloExport(
                workspace_id=seeded.workspace_id,
                scope=TrelloExportScope.STORY,
                user_story_id=seeded.story_id,
                extraction_id=version_id,
            )
        )

        response = await authed_client.get(
            f"/api/v1/workspaces/{seeded.workspace_id}/export/trello/{job.id}"
        )

        assert response.status_code == 200
        assert response.json()["extraction_id"] == str(version_id)

        plain = await export_repo.save(TrelloExport(workspace_id=seeded.workspace_id))
        plain_response = await authed_client.get(
            f"/api/v1/workspaces/{seeded.workspace_id}/export/trello/{plain.id}"
        )
        assert plain_response.json()["extraction_id"] is None

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


# ── GET: the board plan preview ──────────────────────────────────────


class TestTrelloPreview:
    """GET .../export/trello/preview — the plan the trigger would send, serialized.

    Decision E4 (record ``export-page-rework``): the preview answers the board
    plan as JSON — the board's name, its lists in Kanban order, each card's
    title, description, labels and resolved dependency titles. It describes the
    export instead of performing it, so it creates nothing — no ``trello_exports``
    row, asserted against the repository — and needs no credentials: a workspace
    without the pair answers the preview, not ``409``. The scope parameters are
    the trigger's, with the same refusals.
    """

    async def _seed_board_rows(self, db_session: AsyncSession, seeded) -> None:
        """Two tasks in one completed run: a done predecessor and a labeled dependent."""
        story_repo = SQLAlchemyUserStoryRepository(db_session)
        story = await story_repo.save(
            UserStory(
                project_id=seeded.project_id,
                actor="user",
                feature="log in",
                benefit="access account",
                raw_text="As a user, I want to log in so that I can access my account",
            )
        )
        extraction = await seed_extraction(
            db_session, story.id, status=ExtractionStatus.COMPLETED, completed_at=datetime.now(UTC)
        )
        predecessor = await seed_task(
            db_session,
            story.id,
            "Build the auth API",
            extraction=extraction,
            description="Comes first",
            status=TaskStatus.DONE,
            labels=["backend"],
            dependencies=[],
        )
        await seed_task(
            db_session,
            story.id,
            "Wire the login form",
            extraction=extraction,
            description="Points back",
            status=TaskStatus.TODO,
            labels=["frontend", "ui"],
            dependencies=[str(predecessor.id)],
        )

    @pytest.mark.asyncio
    async def test_the_preview_is_the_plan_the_trigger_would_send(
        self, authed_client, db_session: AsyncSession, seed_workspace
    ) -> None:
        """Board name, list order, a card's labels and its resolved dependency titles."""
        seeded = await seed_workspace(stories=0)
        await self._seed_board_rows(db_session, seeded)

        response = await authed_client.get(
            f"/api/v1/workspaces/{seeded.workspace_id}/export/trello/preview"
        )

        assert response.status_code == 200
        body = response.json()
        # The board's name is the workspace's name — what the runner passes.
        assert body["name"] == "Seeded Workspace"
        # The lists are the five Kanban columns, in canonical order, always.
        assert [column["name"] for column in body["columns"]] == [
            "Backlog",
            "To Do",
            "In Progress",
            "Review",
            "Done",
        ]
        by_name = {column["name"]: column for column in body["columns"]}
        card = next(c for c in by_name["To Do"]["cards"] if c["title"] == "Wire the login form")
        assert card["labels"] == ["frontend", "ui"]
        assert card["dependency_titles"] == ["Build the auth API"]
        assert card["description"].startswith("Points back")
        # The predecessor sits in Done, not lost.
        assert [c["title"] for c in by_name["Done"]["cards"]] == ["Build the auth API"]

    @pytest.mark.asyncio
    async def test_the_preview_creates_no_job_row(
        self, authed_client, db_session: AsyncSession, seed_workspace
    ) -> None:
        """Asserted against the repository, not by reading the code."""
        seeded = await seed_workspace(stories=0)
        await self._seed_board_rows(db_session, seeded)

        response = await authed_client.get(
            f"/api/v1/workspaces/{seeded.workspace_id}/export/trello/preview"
        )

        assert response.status_code == 200
        rows = (await db_session.execute(select(TrelloExportModel))).scalars().all()
        assert rows == []

    @pytest.mark.asyncio
    async def test_a_workspace_without_credentials_answers_the_preview(
        self, authed_client, db_session: AsyncSession, seed_workspace
    ) -> None:
        """Describing the export needs no permission to create it: no 409."""
        seeded = await seed_workspace(stories=0)
        await self._seed_board_rows(db_session, seeded)
        # No ``_seed_credentials`` call: the workspace has no Trello pair.

        response = await authed_client.get(
            f"/api/v1/workspaces/{seeded.workspace_id}/export/trello/preview"
        )

        assert response.status_code == 200
        assert response.json()["name"] == "Seeded Workspace"

    @pytest.mark.asyncio
    async def test_two_targets_are_422(
        self, authed_client, db_session: AsyncSession, seed_workspace
    ) -> None:
        """The trigger's never-two rule, inherited by the preview's parameters."""
        seeded = await seed_workspace()

        response = await authed_client.get(
            f"/api/v1/workspaces/{seeded.workspace_id}/export/trello/preview"
            f"?project_id={seeded.project_id}&user_story_id={seeded.story_id}"
        )

        assert response.status_code == 422
        assert response.json()["error_code"] == "REQUEST_VALIDATION_FAILED"

    @pytest.mark.asyncio
    async def test_a_foreign_project_is_refused(
        self, authed_client, db_session: AsyncSession, seed_workspace
    ) -> None:
        """A preview cannot leak across workspaces either: foreign project, 403."""
        seeded = await seed_workspace()
        other = await create_workspace(
            db_session, name="Other WS", slug=f"other-{uuid4().hex[:8]}", owner_id=uuid4()
        )
        other_project = await SQLAlchemyProjectRepository(db_session).save(
            Project(name="Other Project", workspace_id=other.id)
        )

        response = await authed_client.get(
            f"/api/v1/workspaces/{seeded.workspace_id}/export/trello/preview"
            f"?project_id={other_project.id}"
        )

        assert response.status_code == 403
        assert response.json()["error_code"] == "PROJECT_NOT_IN_WORKSPACE"

    @pytest.mark.asyncio
    async def test_the_preview_shows_the_chosen_version_when_one_is_named(
        self, authed_client, db_session: AsyncSession, seed_workspace
    ) -> None:
        """extraction_id names the version the plan reads — superseded or not,
        the same read the trigger would run."""
        seeded = await seed_workspace()
        superseded = await seed_extraction(
            db_session,
            seeded.story_id,
            status=ExtractionStatus.COMPLETED,
            completed_at=datetime.now(UTC),
        )
        await seed_task(db_session, seeded.story_id, "Superseded card", extraction=superseded)
        current = await seed_extraction(
            db_session,
            seeded.story_id,
            status=ExtractionStatus.COMPLETED,
            completed_at=datetime.now(UTC),
        )
        await seed_task(db_session, seeded.story_id, "Current card", extraction=current)

        response = await authed_client.get(
            f"/api/v1/workspaces/{seeded.workspace_id}/export/trello/preview"
            f"?user_story_id={seeded.story_id}&extraction_id={superseded.id}"
        )

        assert response.status_code == 200
        titles = [
            card["title"] for column in response.json()["columns"] for card in column["cards"]
        ]
        assert titles == ["Superseded card"]

    @pytest.mark.asyncio
    async def test_the_preview_defaults_to_the_current_version(
        self, authed_client, db_session: AsyncSession, seed_workspace
    ) -> None:
        """Without extraction_id the plan stays the current-version read it has
        always been — the version parameter is additive, not a behaviour change."""
        seeded = await seed_workspace()
        superseded = await seed_extraction(
            db_session,
            seeded.story_id,
            status=ExtractionStatus.COMPLETED,
            completed_at=datetime.now(UTC),
        )
        await seed_task(db_session, seeded.story_id, "Superseded card", extraction=superseded)
        current = await seed_extraction(
            db_session,
            seeded.story_id,
            status=ExtractionStatus.COMPLETED,
            completed_at=datetime.now(UTC),
        )
        await seed_task(db_session, seeded.story_id, "Current card", extraction=current)

        response = await authed_client.get(
            f"/api/v1/workspaces/{seeded.workspace_id}/export/trello/preview"
            f"?user_story_id={seeded.story_id}"
        )

        assert response.status_code == 200
        titles = [
            card["title"] for column in response.json()["columns"] for card in column["cards"]
        ]
        assert titles == ["Current card"]

    @pytest.mark.asyncio
    async def test_a_version_without_its_story_is_422(
        self, authed_client, db_session: AsyncSession, seed_workspace
    ) -> None:
        """The pairing rule on the preview's query, exactly as the trigger and
        the file export apply it."""
        seeded = await seed_workspace()

        response = await authed_client.get(
            f"/api/v1/workspaces/{seeded.workspace_id}/export/trello/preview"
            f"?extraction_id={uuid4()}"
        )

        assert response.status_code == 422
        assert response.json()["error_code"] == "REQUEST_VALIDATION_FAILED"

    @pytest.mark.asyncio
    async def test_an_unknown_story_is_404(
        self, authed_client, db_session: AsyncSession, seed_workspace
    ) -> None:
        """A story target that does not exist is a miss, preview or not."""
        seeded = await seed_workspace()

        response = await authed_client.get(
            f"/api/v1/workspaces/{seeded.workspace_id}/export/trello/preview"
            f"?user_story_id={uuid4()}"
        )

        assert response.status_code == 404
