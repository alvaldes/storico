"""Integration tests for extraction API endpoints — EXT-T22 + EXT-T23.

Tests the real FastAPI routes with in-memory SQLite (via conftest fixtures).
Most tests create a user (for auth) and then simulate extraction requests
with mocked or real dependencies.
"""

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from storico.api.dependencies import get_extract_use_case, get_llm_port
from storico.application.extraction import ExtractFromStoryUseCase
from storico.config.settings import Settings
from storico.domain.entities import Extraction, LLMConnectionError, User
from storico.domain.ports import LLMPort
from storico.infrastructure.database.repositories import (
    SQLAlchemyExtractionRepository,
    SQLAlchemyUserRepository,
    SQLAlchemyUserStoryRepository,
)
from tests.conftest import AUTH_INTERNAL_TOKEN

AUTH_TOKEN = AUTH_INTERNAL_TOKEN


def _auth_headers(user_id: str | None = None) -> dict:
    return {
        "X-Storico-Internal-Token": AUTH_TOKEN,
        "X-Storico-User-Id": user_id or str(uuid4()),
    }


async def _create_user(db_session: AsyncSession, email: str = "test@example.com") -> User:
    """Create a user in the test database for authentication."""
    repo = SQLAlchemyUserRepository(db_session)
    user = User(
        email=email,
        name="Test User",
        auth_provider="google",
        auth_id=f"g-{email}",
    )
    return await repo.save(user)


async def _create_story(db_session: AsyncSession):
    """Create a user story in the test database.

    Uses repository directly to avoid API call overhead.
    """
    from uuid import uuid4

    from storico.domain.entities.project import Project
    from storico.domain.entities.user_story import UserStory
    from storico.infrastructure.database.repositories import (
        SQLAlchemyProjectRepository,
    )

    # Create a project first
    project_repo = SQLAlchemyProjectRepository(db_session)
    project = Project(name="Test Project", owner_id=uuid4())
    project = await project_repo.save(project)

    # Create a user story
    story_repo = SQLAlchemyUserStoryRepository(db_session)
    story = UserStory(
        project_id=project.id,
        actor="user",
        feature="log in to my account",
        benefit="access my dashboard",
        raw_text="As a user, I want to log in so that I can access my dashboard",
    )
    return await story_repo.save(story)


class TestExtractEndpoint:
    """POST /api/v1/extract/"""

    # ── Success (mocked use case) ──────────────────────────────────

    @pytest.mark.asyncio
    async def test_extract_success(self, async_client, app, db_session: AsyncSession) -> None:
        """POST with valid story returns 201 with extraction metadata."""
        user = await _create_user(db_session)
        story = await _create_story(db_session)
        headers = _auth_headers(str(user.id))

        mock_use_case = AsyncMock(spec=ExtractFromStoryUseCase)
        mock_use_case.execute.return_value = {
            "extraction_id": uuid4(),
            "status": "completed",
            "error_info": None,
            "model_used": "llama3.2",
            "confidence_score": 0.9,
            "created_at": "2026-07-06T00:00:00Z",
        }

        app.dependency_overrides[get_extract_use_case] = lambda: mock_use_case

        try:
            response = await async_client.post(
                "/api/v1/extract/",
                json={"user_story_id": str(story.id)},
                headers=headers,
            )
            assert response.status_code == 201
            data = response.json()
            assert data["status"] == "completed"
            assert "extraction_id" in data
            assert data["model_used"] == "llama3.2"
        finally:
            app.dependency_overrides.pop(get_extract_use_case, None)

    # ── Story not found ────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_extract_story_not_found(
        self, async_client, db_session: AsyncSession
    ) -> None:
        """POST with non-existent story ID returns 404.

        Uses the real use case — EntityNotFound is raised before any
        LLM call.
        """
        user = await _create_user(db_session)
        fake_id = uuid4()
        headers = _auth_headers(str(user.id))

        response = await async_client.post(
            "/api/v1/extract/",
            json={"user_story_id": str(fake_id)},
            headers=headers,
        )
        assert response.status_code == 404

    # ── LLM error → failed status ─────────────────────────────────

    @pytest.mark.asyncio
    async def test_extract_llm_error(
        self, async_client, app, db_session: AsyncSession
    ) -> None:
        """POST when LLM fails returns 201 with failed status (not 500)."""
        user = await _create_user(db_session)
        story = await _create_story(db_session)
        headers = _auth_headers(str(user.id))

        # Override get_llm_port to return a failing adapter
        class FailingLLM(LLMPort):
            async def generate(self, prompt: str, config: object) -> str:  # noqa: ARG002
                raise LLMConnectionError("Ollama not running")

        async def failing_get_llm_port() -> LLMPort:
            return FailingLLM()

        app.dependency_overrides[get_llm_port] = failing_get_llm_port

        try:
            response = await async_client.post(
                "/api/v1/extract/",
                json={"user_story_id": str(story.id)},
                headers=headers,
            )
            # The use case persists the failed extraction, so we get 201 with status failed
            assert response.status_code == 201
            data = response.json()
            assert data["status"] == "failed"
        finally:
            app.dependency_overrides.pop(get_llm_port, None)

    # ── Unauthorized ───────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_extract_unauthorized(self, async_client) -> None:
        """POST without auth headers returns 401."""
        story_id = uuid4()
        response = await async_client.post(
            "/api/v1/extract/",
            json={"user_story_id": str(story_id)},
            headers={},  # No auth headers
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_extract_missing_token(self, async_client) -> None:
        """POST with user-id but no token returns 401."""
        story_id = uuid4()
        response = await async_client.post(
            "/api/v1/extract/",
            json={"user_story_id": str(story_id)},
            headers={"X-Storico-User-Id": str(uuid4())},
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_extract_wrong_token(self, async_client) -> None:
        """POST with wrong token returns 401."""
        story_id = uuid4()
        headers = {
            "X-Storico-Internal-Token": "wrong-token",
            "X-Storico-User-Id": str(uuid4()),
        }
        response = await async_client.post(
            "/api/v1/extract/",
            json={"user_story_id": str(story_id)},
            headers=headers,
        )
        assert response.status_code == 401


class TestExtractionStatusEndpoint:
    """GET /api/v1/extract/status/{extraction_id}"""

    @pytest.mark.asyncio
    async def test_status_completed(
        self, async_client, db_session: AsyncSession
    ) -> None:
        """GET returns extraction details for completed extraction."""
        user = await _create_user(db_session)
        story_id = uuid4()
        repo = SQLAlchemyExtractionRepository(db_session)

        extraction = Extraction(
            user_story_id=story_id,
            model_used="llama3.2",
            raw_response="1. summary: Task one\ndescription: Desc",
            status="completed",
        )
        saved = await repo.save(extraction)

        response = await async_client.get(
            f"/api/v1/extract/status/{saved.id}",
            headers=_auth_headers(str(user.id)),
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "completed"
        assert data["model_used"] == "llama3.2"
        assert data["id"] == str(saved.id)

    @pytest.mark.asyncio
    async def test_status_failed(
        self, async_client, db_session: AsyncSession
    ) -> None:
        """GET returns error_info for failed extraction."""
        user = await _create_user(db_session)
        story_id = uuid4()
        repo = SQLAlchemyExtractionRepository(db_session)

        extraction = Extraction(
            user_story_id=story_id,
            model_used="llama3.2",
            raw_response="",
            status="failed",
            error_info="LLM connection failed",
        )
        saved = await repo.save(extraction)

        response = await async_client.get(
            f"/api/v1/extract/status/{saved.id}",
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
        story_id = uuid4()
        repo = SQLAlchemyExtractionRepository(db_session)

        extraction = Extraction(
            user_story_id=story_id,
            model_used="mistral",
            raw_response="Some response",
            status="completed",
            confidence_score=0.85,
        )
        saved = await repo.save(extraction)

        response = await async_client.get(
            f"/api/v1/extract/status/{saved.id}",
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
        fake_id = uuid4()

        response = await async_client.get(
            f"/api/v1/extract/status/{fake_id}",
            headers=_auth_headers(str(user.id)),
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_status_unauthorized(self, async_client) -> None:
        """GET without auth returns 401."""
        response = await async_client.get(
            f"/api/v1/extract/status/{uuid4()}",
            headers={},
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_status_wrong_token(self, async_client) -> None:
        """GET with wrong token returns 401."""
        headers = {
            "X-Storico-Internal-Token": "wrong-token",
            "X-Storico-User-Id": str(uuid4()),
        }
        response = await async_client.get(
            f"/api/v1/extract/status/{uuid4()}",
            headers=headers,
        )
        assert response.status_code == 401
