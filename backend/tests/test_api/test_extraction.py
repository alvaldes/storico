"""Integration tests for extraction API endpoints.

Tests the workspace-scoped routes at
``/api/v1/workspaces/{workspace_id}/extract/``.
"""

import asyncio
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from storico.domain.entities import Extraction, LLMConnectionError, User
from storico.domain.entities.extraction import ExtractionStatus
from storico.domain.entities.user_story import UserStoryStatus
from storico.domain.entities.workspace_member import WorkspaceMember, WorkspaceRole
from storico.domain.ports import LLMConfig, LLMPort
from storico.infrastructure.database.repositories import (
    SQLAlchemyExtractionRepository,
    SQLAlchemyProjectRepository,
    SQLAlchemyUserRepository,
    SQLAlchemyUserStoryRepository,
)
from storico.infrastructure.database.repositories.workspace_member_repository import (
    SQLAlchemyWorkspaceMemberRepository,
)
from storico.infrastructure.tasks import extraction_task
from tests._helpers import create_workspace


async def _create_user(db_session: AsyncSession, email: str = "test@example.com") -> User:
    """Create a user in the test database."""
    repo = SQLAlchemyUserRepository(db_session)
    user = User(email=email, name="Test User")
    saved = await repo.save(user)
    await repo.link_account(saved.id, "google", f"g-{email}")
    return saved


async def _create_story(db_session: AsyncSession):
    """Create a user story in the test database."""
    from storico.domain.entities.project import Project
    from storico.domain.entities.user_story import UserStory

    ws = await create_workspace(db_session)

    project_repo = SQLAlchemyProjectRepository(db_session)
    project = Project(name="Test Project", workspace_id=ws.id)
    project = await project_repo.save(project)

    story_repo = SQLAlchemyUserStoryRepository(db_session)
    story = UserStory(
        project_id=project.id,
        actor="user",
        feature="log in to my account",
        benefit="access my dashboard",
        raw_text="As a user, I want to log in so that I can access my dashboard",
    )
    return await story_repo.save(story), ws


async def _add_member(db_session: AsyncSession, ws_id, user_id) -> None:
    """Add a user as ADMIN member of a workspace."""
    repo = SQLAlchemyWorkspaceMemberRepository(db_session)
    member = WorkspaceMember(workspace_id=ws_id, user_id=user_id, role=WorkspaceRole.ADMIN)
    await repo.add(member)


class TestExtractEndpoint:
    """POST /api/v1/workspaces/{workspace_id}/extract/"""

    @pytest.mark.asyncio
    async def test_extract_success(
        self, async_client, db_session: AsyncSession, monkeypatch
    ) -> None:
        """POST with a valid story returns 202 and persists a pending extraction."""
        user = await _create_user(db_session)
        story, ws = await _create_story(db_session)
        await _add_member(db_session, ws.id, user.id)
        headers = _auth_headers(str(user.id))

        # The endpoint is fire-and-forget: it persists a pending row and schedules
        # the LLM run. Patch the task so this asserts the scheduling contract
        # instead of racing a real LLM call against an unrelated database.
        scheduled = AsyncMock()
        monkeypatch.setattr("storico.api.routes.extraction.run_background_extraction", scheduled)

        response = await async_client.post(
            f"/api/v1/workspaces/{ws.id}/extract/",
            json={"user_story_id": str(story.id), "model": "llama3.2"},
            headers=headers,
        )

        assert response.status_code == 202
        data = response.json()
        assert data["status"] == "pending"
        assert data["user_story_id"] == str(story.id)

        # The pending row is the real contract: the client polls it by this id.
        repo = SQLAlchemyExtractionRepository(db_session)
        pending = await repo.find_by_id(UUID(data["extraction_id"]))
        assert pending is not None
        assert pending.status == ExtractionStatus.PENDING

        # ...and the background run was scheduled for that exact row.
        await asyncio.sleep(0)
        scheduled.assert_called_once()
        kwargs = scheduled.call_args.kwargs
        assert kwargs["extraction_id"] == pending.id
        assert kwargs["story_id"] == story.id
        assert kwargs["workspace_id"] == ws.id
        assert kwargs["model"] == "llama3.2"

    @pytest.mark.asyncio
    async def test_extract_story_not_found(self, async_client, db_session: AsyncSession) -> None:
        """POST with non-existent story ID returns 404."""
        user = await _create_user(db_session)
        ws = await create_workspace(db_session)
        await _add_member(db_session, ws.id, user.id)
        fake_id = uuid4()
        headers = _auth_headers(str(user.id))

        response = await async_client.post(
            f"/api/v1/workspaces/{ws.id}/extract/",
            json={"user_story_id": str(fake_id)},
            headers=headers,
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_llm_failure_is_recorded_on_the_extraction(
        self, test_engine: AsyncEngine, monkeypatch
    ) -> None:
        """An unreachable LLM is recorded as a failed extraction, never raised.

        The endpoint answers 202 before the LLM is ever called, so "the LLM
        failed" can only be observed on the record the client polls. That work
        lives in the background task, which builds its own session from settings
        — point both it and its adapter at this test's engine.
        """
        factory = async_sessionmaker(bind=test_engine, class_=AsyncSession, expire_on_commit=False)

        async with factory() as session:
            story, ws = await _create_story(session)

        async with factory() as session:
            repo = SQLAlchemyExtractionRepository(session)
            pending = await repo.save(
                Extraction(
                    user_story_id=story.id,
                    model_used="llama3.2",
                    raw_response="",
                    status=ExtractionStatus.PENDING,
                    user_story_status=UserStoryStatus.PENDING_EXTRACTION,
                )
            )

        class UnreachableLLM(LLMPort):
            async def generate(
                self,
                prompt: str,  # noqa: ARG002
                config: LLMConfig,  # noqa: ARG002
                system_prompt: str | None = None,  # noqa: ARG002
            ) -> str:
                raise LLMConnectionError("Ollama not running")

        monkeypatch.setattr(extraction_task, "get_engine", lambda: test_engine)
        monkeypatch.setattr(extraction_task, "OllamaAdapter", lambda **_: UnreachableLLM())

        await extraction_task.run_background_extraction(
            extraction_id=pending.id,
            story_id=story.id,
            workspace_id=ws.id,
            model="llama3.2",
            max_retries=0,
        )

        async with factory() as session:
            repo = SQLAlchemyExtractionRepository(session)
            failed = await repo.find_by_id(pending.id)

        assert failed is not None
        assert failed.status == ExtractionStatus.FAILED
        assert "Ollama not running" in (failed.error_info or "")

    @pytest.mark.asyncio
    async def test_extract_unauthorized(self, async_client) -> None:
        """POST without auth headers returns 401."""
        ws_id = uuid4()
        story_id = uuid4()
        response = await async_client.post(
            f"/api/v1/workspaces/{ws_id}/extract/",
            json={"user_story_id": str(story_id)},
            headers={},
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_extract_missing_token(self, async_client) -> None:
        """POST with user-id but no token returns 401."""
        ws_id = uuid4()
        story_id = uuid4()
        response = await async_client.post(
            f"/api/v1/workspaces/{ws_id}/extract/",
            json={"user_story_id": str(story_id)},
            headers={"X-Storico-User-Id": str(uuid4())},
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_extract_wrong_token(self, async_client) -> None:
        """POST with wrong token returns 401."""
        ws_id = uuid4()
        story_id = uuid4()
        headers = {
            "X-Storico-Internal-Token": "wrong-token",
            "X-Storico-User-Id": str(uuid4()),
        }
        response = await async_client.post(
            f"/api/v1/workspaces/{ws_id}/extract/",
            json={"user_story_id": str(story_id)},
            headers=headers,
        )
        assert response.status_code == 401


def _auth_headers(user_id: str) -> dict:
    """Generate JWT auth headers — mirrors conftest.make_jwt_headers."""
    import jwt as pyjwt

    from storico.config.settings import Settings

    secret = Settings.load().auth_jwt_secret
    token = pyjwt.encode({"sub": user_id}, secret, algorithm="HS256")
    return {"Authorization": f"Bearer {token}"}


class TestExtractionStatusEndpoint:
    """GET /api/v1/workspaces/{workspace_id}/extract/status/{extraction_id}"""

    @pytest.mark.asyncio
    async def test_status_completed(self, async_client, db_session: AsyncSession) -> None:
        """GET returns extraction details for completed extraction."""
        user = await _create_user(db_session)
        ws = await create_workspace(db_session)
        await _add_member(db_session, ws.id, user.id)
        story_id = uuid4()
        repo = SQLAlchemyExtractionRepository(db_session)

        extraction = Extraction(
            user_story_id=story_id,
            model_used="llama3.2",
            raw_response="1. summary: Task one\ndescription: Desc",
            status=ExtractionStatus.COMPLETED,
        )
        saved = await repo.save(extraction)

        response = await async_client.get(
            f"/api/v1/workspaces/{ws.id}/extract/status/{saved.id}",
            headers=_auth_headers(str(user.id)),
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "completed"
        assert data["model_used"] == "llama3.2"
        assert data["id"] == str(saved.id)

    @pytest.mark.asyncio
    async def test_status_failed(self, async_client, db_session: AsyncSession) -> None:
        """GET returns error_info for failed extraction."""
        user = await _create_user(db_session)
        ws = await create_workspace(db_session)
        await _add_member(db_session, ws.id, user.id)
        story_id = uuid4()
        repo = SQLAlchemyExtractionRepository(db_session)

        extraction = Extraction(
            user_story_id=story_id,
            model_used="llama3.2",
            raw_response="",
            status=ExtractionStatus.FAILED,
            error_info="LLM connection failed",
        )
        saved = await repo.save(extraction)

        response = await async_client.get(
            f"/api/v1/workspaces/{ws.id}/extract/status/{saved.id}",
            headers=_auth_headers(str(user.id)),
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "failed"
        assert data["error_info"] == "LLM connection failed"

    @pytest.mark.asyncio
    async def test_status_completed_with_confidence(
        self, async_client, db_session: AsyncSession
    ) -> None:
        """GET returns confidence_score when present."""
        user = await _create_user(db_session)
        ws = await create_workspace(db_session)
        await _add_member(db_session, ws.id, user.id)
        story_id = uuid4()
        repo = SQLAlchemyExtractionRepository(db_session)

        extraction = Extraction(
            user_story_id=story_id,
            model_used="mistral",
            raw_response="Some response",
            status=ExtractionStatus.COMPLETED,
            confidence_score=0.85,
        )
        saved = await repo.save(extraction)

        response = await async_client.get(
            f"/api/v1/workspaces/{ws.id}/extract/status/{saved.id}",
            headers=_auth_headers(str(user.id)),
        )
        assert response.status_code == 200
        data = response.json()
        assert data["confidence_score"] == 0.85
        assert data["raw_response"] == "Some response"

    @pytest.mark.asyncio
    async def test_status_not_found(self, async_client, db_session: AsyncSession) -> None:
        """GET for non-existent extraction returns 404."""
        user = await _create_user(db_session)
        ws = await create_workspace(db_session)
        await _add_member(db_session, ws.id, user.id)
        fake_id = uuid4()

        response = await async_client.get(
            f"/api/v1/workspaces/{ws.id}/extract/status/{fake_id}",
            headers=_auth_headers(str(user.id)),
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_status_unauthorized(self, async_client) -> None:
        """GET without auth returns 401."""
        ws_id = uuid4()
        response = await async_client.get(
            f"/api/v1/workspaces/{ws_id}/extract/status/{uuid4()}",
            headers={},
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_status_wrong_token(self, async_client) -> None:
        """GET with wrong token returns 401."""
        ws_id = uuid4()
        headers = {
            "X-Storico-Internal-Token": "wrong-token",
            "X-Storico-User-Id": str(uuid4()),
        }
        response = await async_client.get(
            f"/api/v1/workspaces/{ws_id}/extract/status/{uuid4()}",
            headers=headers,
        )
        assert response.status_code == 401
