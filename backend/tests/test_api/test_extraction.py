"""Integration tests for extraction API endpoints.

Tests the workspace-scoped routes at
``/api/v1/workspaces/{workspace_id}/extract/``.
"""

import asyncio
from collections.abc import Iterator
from dataclasses import replace
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from storico.config.settings import _reset_settings_cache
from storico.domain.entities import (
    Extraction,
    LLMConnectionError,
    User,
    WorkspaceMember,
    WorkspacePrompt,
    WorkspaceRole,
)
from storico.domain.entities.extraction import ExtractionStatus
from storico.domain.entities.task_invalidation import TaskInvalidation
from storico.domain.entities.user_story import UserStoryStatus
from storico.domain.ports import LLMConfig, LLMPort, VectorStorePort
from storico.domain.services.extraction_service import ExtractionService
from storico.infrastructure.crypto import FernetCipher
from storico.infrastructure.database.models import (
    ExtractionModel,
    TaskModel,
    WorkspaceLLMConfigModel,
)
from storico.infrastructure.database.repositories import (
    SQLAlchemyExtractionRepository,
    SQLAlchemyProjectRepository,
    SQLAlchemyTaskInvalidationRepository,
    SQLAlchemyTaskRepository,
    SQLAlchemyUserRepository,
    SQLAlchemyUserStoryRepository,
    SQLAlchemyWorkspaceLLMConfigRepository,
    SQLAlchemyWorkspacePromptRepository,
)
from storico.infrastructure.database.repositories.workspace_member_repository import (
    SQLAlchemyWorkspaceMemberRepository,
)
from storico.infrastructure.llm import PromptManager, TaskParser
from storico.infrastructure.tasks import extraction_task
from tests._helpers import seed_extraction, seed_task, simple_context

_MASTER_KEY = Fernet.generate_key().decode("ascii")


@pytest.fixture(autouse=True)
def _master_key(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Give the app a master key, so a seeded credential is stored as ciphertext."""
    monkeypatch.setenv("STORICO_ENCRYPTION_KEY", _MASTER_KEY)
    _reset_settings_cache()
    yield
    _reset_settings_cache()


def _repo(session) -> SQLAlchemyWorkspaceLLMConfigRepository:
    """The repository as the app wires it: a session plus the cipher."""
    return SQLAlchemyWorkspaceLLMConfigRepository(session, FernetCipher(_MASTER_KEY))


async def _create_user(db_session: AsyncSession, email: str = "test@example.com") -> User:
    """Create a user in the test database."""
    repo = SQLAlchemyUserRepository(db_session)
    user = User(email=email, name="Test User")
    saved = await repo.save(user)
    await repo.link_account(saved.id, "google", f"g-{email}")
    return saved


class _RecordingVectorStore(VectorStorePort):
    """Vector store that records ``store_extraction`` calls instead of writing anywhere."""

    def __init__(self) -> None:
        self.stored: list[dict] = []

    async def search_similar(  # noqa: ARG002
        self,
        text: str,
        limit: int = 3,
        threshold: float = 0.85,
        *,
        workspace_id: UUID,  # noqa: ARG002
    ) -> list:
        return []

    async def store_extraction(self, **kwargs: object) -> bool:
        self.stored.append(kwargs)
        return True

    async def delete_by_story(
        self,
        *,
        workspace_id: UUID,  # noqa: ARG002
        user_story_id: str,  # noqa: ARG002
    ) -> None:
        # Deliberately inert: the extraction path never deletes vector points,
        # so this fake has nothing to record. The deletion-recording fake that
        # exercises ``delete_by_story`` lives where the deletion behaviour is
        # tested (tests/test_api/test_stories.py).
        return None


def _make_the_vector_store_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    """Turn the RAG dependency off before the background task builds it.

    Called by tests whose subject is the extraction record, not retrieval. ``_run_extraction``
    builds the embedding port and the ``QdrantAdapter`` inside one ``try``, and any failure
    there takes the production "vector store unavailable" branch (``vector_store=None``) —
    the same branch a deployment with no vector store configured runs. Raising from the
    factory is therefore a real code path and not a stub, and it keeps the test off every
    live service: with the real factory the adapter's lazy ``AsyncQdrantClient`` embeds the
    seeded story against the live Ollama and upserts a point into the developer's own Qdrant
    collection, which is the leak ``tests/conftest.py`` now refuses.
    """

    def _unavailable(_settings) -> None:
        raise RuntimeError("vector store deliberately unavailable for this test")

    monkeypatch.setattr(extraction_task, "get_embedding_port", _unavailable)


class TestExtractEndpoint:
    """POST /api/v1/workspaces/{workspace_id}/extract/"""

    @pytest.mark.asyncio
    async def test_extract_success(
        self, async_client, db_session: AsyncSession, monkeypatch, seed_workspace
    ) -> None:
        """POST with a valid story returns 202 and persists a pending extraction."""
        user = await _create_user(db_session)
        seeded = await seed_workspace(user=user)
        story_id = seeded.story_id
        ws_id = seeded.workspace_id
        headers = _auth_headers(str(user.id))

        # The endpoint is fire-and-forget: it persists a pending row and schedules
        # the LLM run. Patch the task so this asserts the scheduling contract
        # instead of racing a real LLM call against an unrelated database.
        scheduled = AsyncMock()
        monkeypatch.setattr("storico.api.routes.extraction.run_background_extraction", scheduled)

        response = await async_client.post(
            f"/api/v1/workspaces/{ws_id}/extract/",
            json={"user_story_id": str(story_id), "model": "llama3.2"},
            headers=headers,
        )

        assert response.status_code == 202
        data = response.json()
        assert data["status"] == "pending"
        assert data["user_story_id"] == str(story_id)

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
        assert kwargs["story_id"] == story_id
        assert kwargs["workspace_id"] == ws_id
        assert kwargs["model"] == "llama3.2"

    @pytest.mark.asyncio
    async def test_extract_story_not_found(
        self, async_client, db_session: AsyncSession, seed_workspace
    ) -> None:
        """POST with non-existent story ID returns 404."""
        user = await _create_user(db_session)
        # An accessible workspace with no stories in it: the 404 must come from
        # the unknown story id, not from a failed workspace membership check.
        seeded = await seed_workspace(user=user, stories=0)
        ws_id = seeded.workspace_id
        fake_id = uuid4()
        headers = _auth_headers(str(user.id))

        response = await async_client.post(
            f"/api/v1/workspaces/{ws_id}/extract/",
            json={"user_story_id": str(fake_id)},
            headers=headers,
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_llm_failure_is_recorded_on_the_extraction(
        self, test_engine: AsyncEngine, monkeypatch, seed_workspace
    ) -> None:
        """An unreachable LLM is recorded as a failed extraction, never raised.

        The endpoint answers 202 before the LLM is ever called, so "the LLM
        failed" can only be observed on the record the client polls. That work
        lives in the background task, which builds its own session from settings
        — point both it and its adapter at this test's engine.
        """
        factory = async_sessionmaker(bind=test_engine, class_=AsyncSession, expire_on_commit=False)

        # Seeded through the shared fixture: it writes to the same in-memory
        # engine this test's own sessions read from, and ``member=False`` keeps
        # this test about the background task rather than route authorization.
        seeded = await seed_workspace(member=False)
        story_id = seeded.story_id
        ws_id = seeded.workspace_id

        async with factory() as session:
            repo = SQLAlchemyExtractionRepository(session)
            pending = await seed_extraction(session, story_id, model_used="llama3.2")

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
        # This test is about the failure being recorded, so it must not depend on a live
        # vector store (nor write into one) — see the helper.
        _make_the_vector_store_unavailable(monkeypatch)

        await extraction_task.run_background_extraction(
            extraction_id=pending.id,
            story_id=story_id,
            workspace_id=ws_id,
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
    async def test_the_completed_save_records_when_it_finished(
        self, test_engine: AsyncEngine, monkeypatch, seed_workspace
    ) -> None:
        """The happy path — the one production actually takes — stamps ``completed_at``.

        This is the site a mutation could remove without any other test noticing: the failure
        paths are covered, and this one only runs when an LLM answers. Leaving it uncovered
        would mean the field this column exists for could go back to being null on every
        successful extraction, silently, which is the bug the column was added to fix.
        """
        factory = async_sessionmaker(bind=test_engine, class_=AsyncSession, expire_on_commit=False)
        seeded = await seed_workspace(member=False)

        async with factory() as session:
            repo = SQLAlchemyExtractionRepository(session)
            pending = await seed_extraction(session, seeded.story_id, model_used="llama3.2")

        class AnsweringLLM(LLMPort):
            async def generate(
                self,
                prompt: str,  # noqa: ARG002
                config: LLMConfig,  # noqa: ARG002
                system_prompt: str | None = None,  # noqa: ARG002
            ) -> str:
                return (
                    "1. summary: Set up the schema\n"
                    "description: Create the tables.\n\n"
                    "2. summary: Build the endpoint\n"
                    "description: Expose the data.\n"
                )

        monkeypatch.setattr(extraction_task, "get_engine", lambda: test_engine)
        monkeypatch.setattr(extraction_task, "OllamaAdapter", lambda **_: AnsweringLLM())
        # The subject here is ``completed_at``, so this test must not depend on a live
        # vector store — and must not write into one. See the helper.
        _make_the_vector_store_unavailable(monkeypatch)

        await extraction_task.run_background_extraction(
            extraction_id=pending.id,
            story_id=seeded.story_id,
            workspace_id=seeded.workspace_id,
            model="llama3.2",
            max_retries=0,
        )

        async with factory() as session:
            repo = SQLAlchemyExtractionRepository(session)
            completed = await repo.find_by_id(pending.id)
            tasks = await SQLAlchemyTaskRepository(session).list_by_story(seeded.story_id)

        assert completed is not None
        assert completed.status == ExtractionStatus.COMPLETED
        assert completed.completed_at is not None
        # Not merely non-null: after the row it completes, and not in the future.
        assert completed.completed_at >= completed.created_at.replace(tzinfo=None)
        assert len(tasks) == 2

    @pytest.mark.asyncio
    async def test_the_rag_point_records_the_real_model_and_no_judge_confidence(
        self, test_engine: AsyncEngine, monkeypatch, seed_workspace
    ) -> None:
        """The RAG point written on the happy path carries the model, not an empty string.

        The ``extractions`` row and the Qdrant point come out of the same run, so they
        must agree on ``model_used``. This runs the real background path with the vector
        store available but replaced by a recording fake: the fake stands in for both
        ``get_embedding_port`` and ``QdrantAdapter``, so no real embedding port or Qdrant
        client is ever constructed and the live cluster is untouched (which the autouse
        guard in ``tests/conftest.py`` would refuse anyway).
        """
        factory = async_sessionmaker(bind=test_engine, class_=AsyncSession, expire_on_commit=False)
        seeded = await seed_workspace(member=False)

        async with factory() as session:
            pending = await seed_extraction(session, seeded.story_id, model_used="llama3.1:8b")

        class AnsweringLLM(LLMPort):
            async def generate(
                self,
                prompt: str,  # noqa: ARG002
                config: LLMConfig,  # noqa: ARG002
                system_prompt: str | None = None,  # noqa: ARG002
            ) -> str:
                return "1. summary: Set up the schema\ndescription: Create the tables.\n"

        store = _RecordingVectorStore()
        monkeypatch.setattr(extraction_task, "get_engine", lambda: test_engine)
        monkeypatch.setattr(extraction_task, "OllamaAdapter", lambda **_: AnsweringLLM())
        # Both halves of the vector-store construction are replaced: the fake embedding
        # port means nothing embeds, and the fake adapter means nothing is written.
        monkeypatch.setattr(extraction_task, "get_embedding_port", lambda _settings: object())
        monkeypatch.setattr(extraction_task, "QdrantAdapter", lambda **_: store)

        await extraction_task.run_background_extraction(
            extraction_id=pending.id,
            story_id=seeded.story_id,
            workspace_id=seeded.workspace_id,
            model="llama3.1:8b",
            max_retries=0,
        )

        assert len(store.stored) == 1
        point = store.stored[0]
        assert point["extraction_id"] == str(pending.id)
        # The point must say what actually ran — not the hardcoded "".
        assert point["model_used"] == "llama3.1:8b"
        # No judge ran (validate defaults to False), so the point must carry no
        # confidence — matching the persisted row it was written alongside.
        assert point["confidence_score"] is None

        async with factory() as session:
            completed = await SQLAlchemyExtractionRepository(session).find_by_id(pending.id)
        assert completed is not None
        assert completed.status == ExtractionStatus.COMPLETED
        assert completed.model_used == "llama3.1:8b"
        assert completed.confidence_score is None

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
    async def test_status_completed(
        self, async_client, db_session: AsyncSession, seed_workspace
    ) -> None:
        """GET returns extraction details for completed extraction."""
        user = await _create_user(db_session)
        # The status route checks containment as well as membership, so the
        # extraction must hang off a story that really lives in this workspace.
        seeded = await seed_workspace(user=user)
        ws_id = seeded.workspace_id
        story_id = seeded.story_id

        saved = await seed_extraction(
            db_session,
            story_id,
            model_used="llama3.2",
            raw_response="1. summary: Task one\ndescription: Desc",
            status=ExtractionStatus.COMPLETED,
        )

        response = await async_client.get(
            f"/api/v1/workspaces/{ws_id}/extract/status/{saved.id}",
            headers=_auth_headers(str(user.id)),
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "completed"
        assert data["model_used"] == "llama3.2"
        assert data["id"] == str(saved.id)

    @pytest.mark.asyncio
    async def test_status_failed(
        self, async_client, db_session: AsyncSession, seed_workspace
    ) -> None:
        """GET returns error_info for failed extraction."""
        user = await _create_user(db_session)
        seeded = await seed_workspace(user=user)
        ws_id = seeded.workspace_id
        story_id = seeded.story_id

        saved = await seed_extraction(
            db_session,
            story_id,
            model_used="llama3.2",
            status=ExtractionStatus.FAILED,
            error_info="LLM connection failed",
        )

        response = await async_client.get(
            f"/api/v1/workspaces/{ws_id}/extract/status/{saved.id}",
            headers=_auth_headers(str(user.id)),
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "failed"
        assert data["error_info"] == "LLM connection failed"

    @pytest.mark.asyncio
    async def test_status_completed_with_confidence(
        self, async_client, db_session: AsyncSession, seed_workspace
    ) -> None:
        """GET returns confidence_score when present."""
        user = await _create_user(db_session)
        seeded = await seed_workspace(user=user)
        ws_id = seeded.workspace_id
        story_id = seeded.story_id

        saved = await seed_extraction(
            db_session,
            story_id,
            model_used="mistral",
            raw_response="Some response",
            status=ExtractionStatus.COMPLETED,
            confidence_score=0.85,
        )

        response = await async_client.get(
            f"/api/v1/workspaces/{ws_id}/extract/status/{saved.id}",
            headers=_auth_headers(str(user.id)),
        )
        assert response.status_code == 200
        data = response.json()
        assert data["confidence_score"] == 0.85
        assert data["raw_response"] == "Some response"

    @pytest.mark.asyncio
    async def test_status_is_forbidden_for_another_workspaces_extraction(
        self, async_client, db_session: AsyncSession, seed_workspace
    ) -> None:
        """GET with a path workspace that does not own the extraction returns 403.

        Membership of the workspace in the URL is not containment: without the
        extra ``story → project → workspace`` check, any member of any workspace
        could read any extraction by id. Both workspaces below belong to the
        caller, so only containment separates the request from a 200.
        """
        user = await _create_user(db_session)
        owner = await seed_workspace(user=user)
        foreign = await seed_workspace(user=user, stories=0)

        saved = await seed_extraction(
            db_session,
            owner.story_id,
            model_used="llama3.2",
            status=ExtractionStatus.COMPLETED,
        )

        response = await async_client.get(
            f"/api/v1/workspaces/{foreign.workspace_id}/extract/status/{saved.id}",
            headers=_auth_headers(str(user.id)),
        )
        assert response.status_code == 403
        assert response.json()["error_code"] == "STORY_NOT_IN_WORKSPACE"
        assert response.json()["detail"] == (
            "This user story does not belong to the specified workspace"
        )

    @pytest.mark.asyncio
    async def test_status_still_returns_the_extraction_for_its_own_workspace(
        self, async_client, db_session: AsyncSession, seed_workspace
    ) -> None:
        """GET for the workspace that owns the extraction still returns the payload.

        The positive pin for the containment check: it must reject foreign
        workspaces without disturbing the owning workspace's read path.
        """
        user = await _create_user(db_session)
        seeded = await seed_workspace(user=user)

        saved = await seed_extraction(
            db_session,
            seeded.story_id,
            model_used="llama3.2",
            raw_response="1. summary: Task one\ndescription: Desc",
            status=ExtractionStatus.COMPLETED,
        )

        response = await async_client.get(
            f"/api/v1/workspaces/{seeded.workspace_id}/extract/status/{saved.id}",
            headers=_auth_headers(str(user.id)),
        )
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == str(saved.id)
        assert data["user_story_id"] == str(seeded.story_id)
        assert data["status"] == "completed"

    @pytest.mark.asyncio
    async def test_status_not_found(
        self, async_client, db_session: AsyncSession, seed_workspace
    ) -> None:
        """GET for non-existent extraction returns 404."""
        user = await _create_user(db_session)
        seeded = await seed_workspace(user=user, stories=0)
        ws_id = seeded.workspace_id
        fake_id = uuid4()

        response = await async_client.get(
            f"/api/v1/workspaces/{ws_id}/extract/status/{fake_id}",
            headers=_auth_headers(str(user.id)),
        )
        assert response.status_code == 404
        assert response.json()["error_code"] == "EXTRACTION_NOT_FOUND"

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


async def _seed_llm_config(
    db_session: AsyncSession,
    workspace_id: UUID,
    *,
    provider: str,
    model: str | None = None,
    api_key: str | None = None,
    base_url: str | None = None,
) -> None:
    """Persist the workspace's LLM row exactly as the settings form would."""
    from storico.domain.entities.workspace_llm_config import WorkspaceLLMConfig

    await _repo(db_session).upsert(
        WorkspaceLLMConfig(
            workspace_id=workspace_id,
            provider=provider,
            model=model,
            api_key=api_key,
            base_url=base_url,
        )
    )


class TestExtractionRefusesAnIncompleteConfig:
    """POST refuses before creating anything when the configuration cannot extract.

    The old behaviour created the pending row first and let the missing credential
    surface inside the background task, which dragged the story into
    ``failed_extraction`` for a configuration that was never usable. These tests pin
    the refusal *and* the absence of its previous side effects.
    """

    @pytest.mark.asyncio
    async def test_an_unconfigured_workspace_is_refused_with_the_missing_model(
        self, async_client, db_session: AsyncSession, seed_workspace
    ) -> None:
        """No row and no body model leaves exactly one gap, and nothing is created."""
        user = await _create_user(db_session)
        seeded = await seed_workspace(user=user)
        headers = _auth_headers(str(user.id))

        response = await async_client.post(
            f"/api/v1/workspaces/{seeded.workspace_id}/extract/",
            json={"user_story_id": str(seeded.story_id)},
            headers=headers,
        )

        assert response.status_code == 400
        detail = response.json()["detail"]
        assert response.json()["error_code"] == "LLM_CONFIG_INCOMPLETE"
        assert detail["missing"] == ["model"]
        assert detail["provider"] == "ollama"

        # The side effects the refusal exists to prevent: no extraction record, and
        # a story still sitting in its pre-extraction status.
        page, total = await SQLAlchemyExtractionRepository(db_session).list_page(
            user_story_id=seeded.story_id, limit=10, offset=0
        )
        assert page == []
        assert total == 0
        story = await SQLAlchemyUserStoryRepository(db_session).find_by_id(seeded.story_id)
        assert story is not None
        assert story.status == UserStoryStatus.PENDING_EXTRACTION

    @pytest.mark.asyncio
    async def test_a_cloud_provider_with_a_model_but_no_key_is_refused(
        self, async_client, db_session: AsyncSession, seed_workspace
    ) -> None:
        """The gap the background task used to discover, reported before any work."""
        user = await _create_user(db_session)
        seeded = await seed_workspace(user=user)
        await _seed_llm_config(
            db_session, seeded.workspace_id, provider="openai", model="gpt-4o-mini"
        )

        response = await async_client.post(
            f"/api/v1/workspaces/{seeded.workspace_id}/extract/",
            json={"user_story_id": str(seeded.story_id)},
            headers=_auth_headers(str(user.id)),
        )

        assert response.status_code == 400
        detail = response.json()["detail"]
        assert response.json()["error_code"] == "LLM_CONFIG_INCOMPLETE"
        assert detail["missing"] == ["api_key"]
        assert detail["provider"] == "openai"

    @pytest.mark.asyncio
    async def test_a_custom_provider_without_an_endpoint_is_refused(
        self, async_client, db_session: AsyncSession, seed_workspace
    ) -> None:
        """A custom provider is unusable without the endpoint it should be called at."""
        user = await _create_user(db_session)
        seeded = await seed_workspace(user=user)
        await _seed_llm_config(
            db_session, seeded.workspace_id, provider="deepseek", model="deepseek-chat"
        )

        response = await async_client.post(
            f"/api/v1/workspaces/{seeded.workspace_id}/extract/",
            json={"user_story_id": str(seeded.story_id)},
            headers=_auth_headers(str(user.id)),
        )

        assert response.status_code == 400
        assert response.json()["detail"]["missing"] == ["base_url"]

    @pytest.mark.asyncio
    async def test_a_body_model_cannot_complete_a_workspace_missing_its_key(
        self, async_client, db_session: AsyncSession, seed_workspace
    ) -> None:
        """The body override fills the model field only; the credential still has to exist."""
        user = await _create_user(db_session)
        seeded = await seed_workspace(user=user)
        await _seed_llm_config(db_session, seeded.workspace_id, provider="anthropic")

        response = await async_client.post(
            f"/api/v1/workspaces/{seeded.workspace_id}/extract/",
            json={"user_story_id": str(seeded.story_id), "model": "claude-3-haiku"},
            headers=_auth_headers(str(user.id)),
        )

        assert response.status_code == 400
        assert response.json()["detail"]["missing"] == ["api_key"]

    @pytest.mark.asyncio
    async def test_an_ollama_workspace_with_only_a_model_is_accepted(
        self, async_client, db_session: AsyncSession, seed_workspace, monkeypatch
    ) -> None:
        """Ollama's host is not a gap, so the model alone is a complete configuration."""
        user = await _create_user(db_session)
        seeded = await seed_workspace(user=user)
        await _seed_llm_config(db_session, seeded.workspace_id, provider="ollama", model="llama3.2")
        monkeypatch.setattr("storico.api.routes.extraction.run_background_extraction", AsyncMock())

        response = await async_client.post(
            f"/api/v1/workspaces/{seeded.workspace_id}/extract/",
            json={"user_story_id": str(seeded.story_id)},
            headers=_auth_headers(str(user.id)),
        )

        assert response.status_code == 202

    @pytest.mark.asyncio
    async def test_a_custom_provider_without_a_key_is_accepted(
        self, async_client, db_session: AsyncSession, seed_workspace, monkeypatch
    ) -> None:
        """A self-hosted gateway commonly accepts unauthenticated requests."""
        user = await _create_user(db_session)
        seeded = await seed_workspace(user=user)
        await _seed_llm_config(
            db_session,
            seeded.workspace_id,
            provider="deepseek",
            model="deepseek-chat",
            base_url="https://api.deepseek.com/v1",
        )
        monkeypatch.setattr("storico.api.routes.extraction.run_background_extraction", AsyncMock())

        response = await async_client.post(
            f"/api/v1/workspaces/{seeded.workspace_id}/extract/",
            json={"user_story_id": str(seeded.story_id)},
            headers=_auth_headers(str(user.id)),
        )

        assert response.status_code == 202

    @pytest.mark.asyncio
    async def test_a_blank_stored_endpoint_reaches_the_task_as_absent(
        self, async_client, db_session: AsyncSession, seed_workspace, monkeypatch
    ) -> None:
        """A row holding spaces for its endpoint hands the task ``None``.

        The adapter would otherwise be built with a URL of spaces and fail *inside* the
        background task, after this route had already created the pending extraction.
        """
        user = await _create_user(db_session)
        seeded = await seed_workspace(user=user)
        await _seed_llm_config(
            db_session,
            seeded.workspace_id,
            provider="ollama",
            model="llama3.2",
            base_url="   ",
        )
        scheduled = AsyncMock()
        monkeypatch.setattr("storico.api.routes.extraction.run_background_extraction", scheduled)

        response = await async_client.post(
            f"/api/v1/workspaces/{seeded.workspace_id}/extract/",
            json={"user_story_id": str(seeded.story_id)},
            headers=_auth_headers(str(user.id)),
        )

        assert response.status_code == 202
        await asyncio.sleep(0)
        assert scheduled.call_args.kwargs["base_url"] is None

    @pytest.mark.asyncio
    async def test_a_blank_stored_credential_reaches_the_task_as_absent(
        self, async_client, db_session: AsyncSession, seed_workspace, monkeypatch
    ) -> None:
        """Same for the credential: the task is handed ``None``, not whitespace."""
        user = await _create_user(db_session)
        seeded = await seed_workspace(user=user)
        await _seed_llm_config(
            db_session,
            seeded.workspace_id,
            provider="deepseek",
            model="deepseek-chat",
            api_key="   ",
            base_url="https://api.deepseek.com/v1",
        )
        scheduled = AsyncMock()
        monkeypatch.setattr("storico.api.routes.extraction.run_background_extraction", scheduled)

        response = await async_client.post(
            f"/api/v1/workspaces/{seeded.workspace_id}/extract/",
            json={"user_story_id": str(seeded.story_id)},
            headers=_auth_headers(str(user.id)),
        )

        assert response.status_code == 202
        await asyncio.sleep(0)
        assert scheduled.call_args.kwargs["api_key"] is None


class TestExtractionReceivesTheDecryptedCredential:
    """The background task is the last consumer of the key, so it must receive plaintext."""

    @pytest.mark.asyncio
    async def test_the_adapter_is_built_with_the_plaintext_not_the_ciphertext(
        self, async_client, db_session: AsyncSession, seed_workspace, monkeypatch
    ) -> None:
        """A stored ciphertext credential has to reach the adapter decrypted."""
        user = await _create_user(db_session)
        seeded = await seed_workspace(user=user)
        await _seed_llm_config(
            db_session,
            seeded.workspace_id,
            provider="openai",
            model="gpt-4o-mini",
            api_key="sk-decrypted-for-the-adapter",
        )

        stored = (
            await db_session.execute(
                select(WorkspaceLLMConfigModel.api_key).where(
                    WorkspaceLLMConfigModel.workspace_id == seeded.workspace_id
                )
            )
        ).scalar_one()
        # The row really is ciphertext, so a plaintext hand-off can only have come from
        # the repository decrypting it on the way out.
        assert stored is not None, (
            "the seeded config row must exist before its value means anything"
        )
        assert stored.startswith("v1:")

        scheduled = AsyncMock()
        monkeypatch.setattr("storico.api.routes.extraction.run_background_extraction", scheduled)

        response = await async_client.post(
            f"/api/v1/workspaces/{seeded.workspace_id}/extract/",
            json={"user_story_id": str(seeded.story_id)},
            headers=_auth_headers(str(user.id)),
        )

        assert response.status_code == 202
        assert scheduled.call_args.kwargs["api_key"] == "sk-decrypted-for-the-adapter"


@pytest.mark.unit
class TestLegacyExtractEndpointGone:
    """The pre-workspaces ``/api/v1/extract`` routes answer 410 with their code.

    Like the projects catch-all, this route is registered with
    ``include_in_schema=False`` and no test ever drove it: its only callers are
    stale clients, and the whole point of its 410 is to point them at the
    workspace-scoped replacement rather than leave them reading a 404.
    """

    @pytest.mark.asyncio
    async def test_a_stale_start_answers_410_gone_with_its_code(self, async_client) -> None:
        """POST, the action a stale client would attempt, carries the code."""
        response = await async_client.post("/api/v1/extract/", json={"user_story": "..."})

        assert response.status_code == 410
        assert response.json()["error_code"] == "EXTRACTION_ENDPOINT_REMOVED"

    @pytest.mark.asyncio
    async def test_a_stale_poll_answers_410_gone_with_its_code(self, async_client) -> None:
        """GET on a status path carries the code too."""
        response = await async_client.get(
            "/api/v1/extract/status/00000000-0000-0000-0000-000000000000"
        )

        assert response.status_code == 410
        assert response.json()["error_code"] == "EXTRACTION_ENDPOINT_REMOVED"


@pytest.mark.unit
class TestExtractionVersioningAtBirth:
    """The pending row is born versioned (WU1 task 2.1, absorbed from WU2 on 2026-09-29).

    ``0028`` declares ``version_number``, ``provider`` and ``temperature`` ``NOT NULL``, and
    ``version_number`` has no server default: allocation happens at INSERT time or the INSERT
    is refused. That makes the birth path part of the schema unit — a schema unit that leaves
    the route writing ``NULL`` into a ``NOT NULL`` column has no green end state, so this
    class lands in the same commit as the migration.
    """

    async def _post_extract(self, async_client, db_session, seed_workspace, monkeypatch, **body):
        """POST one extraction and return ``(row, scheduled)`` for the assertions below.

        The background run is replaced by a recording mock: the subject here is what the
        route wrote at birth, not what an adapter would answer.
        """
        user = await _create_user(db_session)
        seeded = await seed_workspace(user=user)
        await _seed_llm_config(
            db_session,
            seeded.workspace_id,
            provider="gemini",
            model="gemini-2.0-flash",
            api_key="g-workspace-key",
        )
        scheduled = AsyncMock()
        monkeypatch.setattr("storico.api.routes.extraction.run_background_extraction", scheduled)

        response = await async_client.post(
            f"/api/v1/workspaces/{seeded.workspace_id}/extract/",
            json={"user_story_id": str(seeded.story_id), **body},
            headers=_auth_headers(str(user.id)),
        )
        assert response.status_code == 202, response.text

        repo = SQLAlchemyExtractionRepository(db_session)
        row = await repo.find_by_id(UUID(response.json()["extraction_id"]))
        assert row is not None
        return row, seeded, user, scheduled

    @pytest.mark.asyncio
    async def test_the_pending_row_is_born_with_its_version_number(
        self, async_client, db_session, seed_workspace, monkeypatch
    ) -> None:
        """The first run on a story is version 1, and the number exists before any task runs."""
        row, _seeded, _user, _scheduled = await self._post_extract(
            async_client, db_session, seed_workspace, monkeypatch
        )

        assert row.version_number == 1

    @pytest.mark.asyncio
    async def test_the_pending_row_is_born_with_the_workspace_provider(
        self, async_client, db_session, seed_workspace, monkeypatch
    ) -> None:
        """The provider column carries the workspace's configured provider, not a default."""
        row, _seeded, _user, _scheduled = await self._post_extract(
            async_client, db_session, seed_workspace, monkeypatch
        )

        assert row.provider == "gemini"

    @pytest.mark.asyncio
    async def test_an_omitted_temperature_is_recorded_as_the_default(
        self, async_client, db_session, seed_workspace, monkeypatch
    ) -> None:
        """No ``temperature`` in the body still stores ``0.1``, the value the adapter gets.

        One literal for the default: the route reads the same constant ``LLMConfig`` uses, so
        a row can never claim a temperature the provider did not run at.
        """
        row, _seeded, _user, scheduled = await self._post_extract(
            async_client, db_session, seed_workspace, monkeypatch
        )

        assert row.temperature == 0.1
        assert scheduled.call_args.kwargs["temperature"] == 0.1

    @pytest.mark.asyncio
    async def test_an_explicit_temperature_is_recorded_on_the_row(
        self, async_client, db_session, seed_workspace, monkeypatch
    ) -> None:
        """The explicit request value is what the column holds — resolved once, in the route."""
        row, _seeded, _user, scheduled = await self._post_extract(
            async_client, db_session, seed_workspace, monkeypatch, temperature=0.7
        )

        assert row.temperature == 0.7
        assert scheduled.call_args.kwargs["temperature"] == 0.7

    @pytest.mark.asyncio
    async def test_prompt_config_no_longer_carries_the_temperature(
        self, async_client, db_session, seed_workspace, monkeypatch
    ) -> None:
        """``temperature`` has its own column now; a second copy in JSON is drift bait."""
        row, _seeded, _user, _scheduled = await self._post_extract(
            async_client, db_session, seed_workspace, monkeypatch
        )

        assert "temperature" not in (row.prompt_config or {})

    @pytest.mark.asyncio
    async def test_two_posts_on_one_story_mint_one_then_two(
        self, async_client, db_session, seed_workspace, monkeypatch
    ) -> None:
        """Two runs on one story are two versions, not one row rewritten in place.

        The same caller posts twice: a second number minted under a different user would
        prove allocation but not that the pair belongs to the one story.
        """
        first, seeded, user, _scheduled = await self._post_extract(
            async_client, db_session, seed_workspace, monkeypatch
        )

        scheduled_second = AsyncMock()
        monkeypatch.setattr(
            "storico.api.routes.extraction.run_background_extraction", scheduled_second
        )
        response = await async_client.post(
            f"/api/v1/workspaces/{seeded.workspace_id}/extract/",
            json={"user_story_id": str(seeded.story_id)},
            headers=_auth_headers(str(user.id)),
        )
        assert response.status_code == 202, response.text

        second = await SQLAlchemyExtractionRepository(db_session).find_by_id(
            UUID(response.json()["extraction_id"])
        )

        assert (first.version_number, second.version_number) == (1, 2)


@pytest.mark.unit
class TestVersioningTriangulation:
    """The edges the allocation and the default temperature are judged on (WU1 task 2.5).

    Task 1.1 pins the repository and 2.1 pins the birth path; this class pins what neither can
    see: the three runner call sites that never name a temperature, the fact that two POSTs are
    two rows before either finishes, and that an exhausted allocation is not a silent 202.
    """

    @pytest.mark.asyncio
    async def test_a_run_that_never_names_a_temperature_still_runs_at_the_default(
        self, test_engine: AsyncEngine, monkeypatch, seed_workspace
    ) -> None:
        """``run_background_extraction`` without a ``temperature`` argument runs at 0.1.

        The runner's public wrapper defaults to ``DEFAULT_TEMPERATURE``, so the three pre-existing
        call sites that omit the keyword are not a hole in the one-literal rule: the adapter must
        receive the default, not ``None``. A recording adapter is the only witness — the column
        would happily store whatever the caller passed.
        """
        factory = async_sessionmaker(bind=test_engine, class_=AsyncSession, expire_on_commit=False)
        seeded = await seed_workspace(member=False)

        async with factory() as session:
            pending = await SQLAlchemyExtractionRepository(session).create_next_version(
                Extraction(
                    user_story_id=seeded.story_id,
                    model_used="llama3.2",
                    raw_response="",
                    provider="ollama",
                    temperature=0.1,
                    status=ExtractionStatus.PENDING,
                    user_story_status=UserStoryStatus.PENDING_EXTRACTION,
                )
            )

        seen: list[LLMConfig] = []

        class RecordingLLM(LLMPort):
            async def generate(
                self,
                prompt: str,  # noqa: ARG002
                config: LLMConfig,
                system_prompt: str | None = None,  # noqa: ARG002
            ) -> str:
                seen.append(config)
                return "1. summary: Seed the schema\ndescription: Create the tables.\n"

        monkeypatch.setattr(extraction_task, "get_engine", lambda: test_engine)
        monkeypatch.setattr(extraction_task, "OllamaAdapter", lambda **_: RecordingLLM())
        _make_the_vector_store_unavailable(monkeypatch)

        await extraction_task.run_background_extraction(
            extraction_id=pending.id,
            story_id=seeded.story_id,
            workspace_id=seeded.workspace_id,
            model="llama3.2",
            max_retries=0,
        )

        assert seen, "the adapter was never called, so nothing was observed"
        assert seen[0].temperature == 0.1

    @pytest.mark.asyncio
    async def test_two_posts_are_two_rows_and_neither_is_current_until_one_finishes(
        self, async_client, db_session, seed_workspace, monkeypatch
    ) -> None:
        """Two POSTs leave the board populated and the current version undecided.

        Each run consumes a number at birth (D22), so the story has two versions while both are
        ``pending`` — and "current" is derived from ``status = 'completed'``, so it is ``None`` until
        one of them finishes. The tablero does not empty when a second run starts, and it does not
        promote a run that has not answered.
        """
        user = await _create_user(db_session)
        seeded = await seed_workspace(user=user)
        await _seed_llm_config(db_session, seeded.workspace_id, provider="ollama", model="llama3.2")
        monkeypatch.setattr("storico.api.routes.extraction.run_background_extraction", AsyncMock())

        ids = []
        for _ in range(2):
            response = await async_client.post(
                f"/api/v1/workspaces/{seeded.workspace_id}/extract/",
                json={"user_story_id": str(seeded.story_id)},
                headers=_auth_headers(str(user.id)),
            )
            assert response.status_code == 202, response.text
            ids.append(UUID(response.json()["extraction_id"]))

        repo = SQLAlchemyExtractionRepository(db_session)
        first, second = await repo.find_by_id(ids[0]), await repo.find_by_id(ids[1])
        assert (first.version_number, second.version_number) == (1, 2)
        assert await repo.find_current_version(seeded.story_id) is None, (
            "a pending run was made current"
        )

        await repo.mark_completed(
            second.id, raw_response="r", confidence_score=0.9, completed_at=datetime.now(UTC)
        )
        current = await repo.find_current_version(seeded.story_id)
        assert current is not None and current.version_number == 2

    @pytest.mark.asyncio
    async def test_an_exhausted_allocation_is_not_silent(
        self, async_client, db_session, seed_workspace, monkeypatch
    ) -> None:
        """A lost race on every attempt surfaces as an explicit conflict, never silently.

        An exhausted version allocation answers 409 ``VERSION_ALLOCATION_CONFLICT``: every
        bounded attempt lost the race, so the run never started — there is no extraction to
        poll and the caller may retry. The handler was registered for
        ``VersionAllocationConflictError`` itself (task 4.7), so the MRO resolves the
        subclass here instead of falling through to ``repository_error_handler``'s generic
        500 ``REPOSITORY_ERROR``. Task 4.2 owns the remaining edges of this contract: the
        "never 202" refusal, that no extraction row is written, and the ``MEMBER`` gate
        refusal that precedes it.
        """
        from storico.domain.entities.exceptions import VersionAllocationConflictError

        user = await _create_user(db_session)
        seeded = await seed_workspace(user=user)
        await _seed_llm_config(db_session, seeded.workspace_id, provider="ollama", model="llama3.2")

        async def exhaust_every_attempt(*args: object, **kwargs: object) -> Extraction:
            raise VersionAllocationConflictError("Could not allocate a version number")

        monkeypatch.setattr(
            SQLAlchemyExtractionRepository, "create_next_version", exhaust_every_attempt
        )

        response = await async_client.post(
            f"/api/v1/workspaces/{seeded.workspace_id}/extract/",
            json={"user_story_id": str(seeded.story_id)},
            headers=_auth_headers(str(user.id)),
        )

        assert response.status_code == 409
        assert response.json()["error_code"] == "VERSION_ALLOCATION_CONFLICT"
        # The remainder task 4.2 promises: the run never started. The response was
        # never a 202 and no extraction row exists for the story — there is
        # nothing to poll, and the caller may retry.
        assert response.status_code != 202
        assert await _extraction_rows(db_session, seeded.story_id) == []


class TestExtractionOwnerOrAdminGate:
    """POST extract is gated to the workspace owner or an admin (D13 / task 4.6).

    The dependency runs before the handler body, so every refusal below is
    deliberately witnessed **without** a seeded LLM configuration: a
    config-completeness 400 leaking ahead of the gate would fail the case. The
    202 cases seed the config, exactly like the success case does.
    """

    @pytest.mark.asyncio
    async def test_a_member_who_is_neither_owner_nor_admin_is_refused(
        self, async_client, db_session: AsyncSession, seed_workspace
    ) -> None:
        """A plain MEMBER posting extract gets 403 and leaves the story untouched.

        No extraction row may exist for the story afterwards and the story's
        status stays exactly what a birth gives it: a refusal must not drag the
        story into any extraction state.
        """
        owner = await _create_user(db_session, "owner@example.com")
        member = await _create_user(db_session, "member@example.com")
        seeded = await seed_workspace(user=owner)
        await SQLAlchemyWorkspaceMemberRepository(db_session).add(
            WorkspaceMember(
                workspace_id=seeded.workspace_id,
                user_id=member.id,
                role=WorkspaceRole.MEMBER,
            )
        )

        response = await async_client.post(
            f"/api/v1/workspaces/{seeded.workspace_id}/extract/",
            json={"user_story_id": str(seeded.story_id)},
            headers=_auth_headers(str(member.id)),
        )

        assert response.status_code == 403
        assert response.json()["error_code"] == "WORKSPACE_OWNER_OR_ADMIN_REQUIRED"
        assert await _extraction_rows(db_session, seeded.story_id) == []
        story = await SQLAlchemyUserStoryRepository(db_session).find_by_id(seeded.story_id)
        assert story is not None
        assert story.status == UserStoryStatus.PENDING_EXTRACTION

    @pytest.mark.asyncio
    async def test_the_owner_posts_even_when_their_member_role_is_member(
        self, async_client, db_session, seed_workspace, monkeypatch
    ) -> None:
        """Ownership is ``workspace.owner_id == user.id``, not a member role.

        The owner below holds a MEMBER-role membership row, and the gate still
        admits them: the rule is a disjunction over a data fact and a role.
        """
        user = await _create_user(db_session)
        seeded = await seed_workspace(user=user, role=WorkspaceRole.MEMBER)
        await _seed_llm_config(db_session, seeded.workspace_id, provider="ollama", model="llama3.2")
        monkeypatch.setattr("storico.api.routes.extraction.run_background_extraction", AsyncMock())

        response = await async_client.post(
            f"/api/v1/workspaces/{seeded.workspace_id}/extract/",
            json={"user_story_id": str(seeded.story_id)},
            headers=_auth_headers(str(user.id)),
        )

        assert response.status_code == 202, response.text

    @pytest.mark.asyncio
    async def test_a_non_owner_admin_member_posts(
        self, async_client, db_session, seed_workspace, monkeypatch
    ) -> None:
        """A member with role ADMIN who is not the owner passes the gate."""
        owner = await _create_user(db_session, "owner@example.com")
        admin = await _create_user(db_session, "admin@example.com")
        seeded = await seed_workspace(user=owner)
        await SQLAlchemyWorkspaceMemberRepository(db_session).add(
            WorkspaceMember(
                workspace_id=seeded.workspace_id,
                user_id=admin.id,
                role=WorkspaceRole.ADMIN,
            )
        )
        await _seed_llm_config(db_session, seeded.workspace_id, provider="ollama", model="llama3.2")
        monkeypatch.setattr("storico.api.routes.extraction.run_background_extraction", AsyncMock())

        response = await async_client.post(
            f"/api/v1/workspaces/{seeded.workspace_id}/extract/",
            json={"user_story_id": str(seeded.story_id)},
            headers=_auth_headers(str(admin.id)),
        )

        assert response.status_code == 202, response.text

    @pytest.mark.asyncio
    async def test_a_non_member_keeps_the_not_a_workspace_member_code(
        self, async_client, db_session: AsyncSession, seed_workspace
    ) -> None:
        """A user with no membership row keeps the unchanged 403, not the gate code.

        ``require_owner_or_admin`` chains ``get_workspace_for_user``, whose
        membership refusal fires first: a non-member never sees
        ``WORKSPACE_OWNER_OR_ADMIN_REQUIRED``.
        """
        owner = await _create_user(db_session, "owner@example.com")
        outsider = await _create_user(db_session, "outsider@example.com")
        seeded = await seed_workspace(user=owner)

        response = await async_client.post(
            f"/api/v1/workspaces/{seeded.workspace_id}/extract/",
            json={"user_story_id": str(seeded.story_id)},
            headers=_auth_headers(str(outsider.id)),
        )

        assert response.status_code == 403
        assert response.json()["error_code"] == "NOT_A_WORKSPACE_MEMBER"
        assert await _extraction_rows(db_session, seeded.story_id) == []

    @pytest.mark.asyncio
    async def test_a_member_who_is_not_the_owner_still_reads_the_status(
        self, async_client, db_session: AsyncSession, seed_workspace
    ) -> None:
        """The gate is on the mutation, not on the read: a MEMBER still polls 200."""
        owner = await _create_user(db_session, "owner@example.com")
        member = await _create_user(db_session, "member@example.com")
        seeded = await seed_workspace(user=owner)
        await SQLAlchemyWorkspaceMemberRepository(db_session).add(
            WorkspaceMember(
                workspace_id=seeded.workspace_id,
                user_id=member.id,
                role=WorkspaceRole.MEMBER,
            )
        )
        saved = await seed_extraction(db_session, seeded.story_id, model_used="llama3.2")

        response = await async_client.get(
            f"/api/v1/workspaces/{seeded.workspace_id}/extract/status/{saved.id}",
            headers=_auth_headers(str(member.id)),
        )

        assert response.status_code == 200
        assert response.json()["id"] == str(saved.id)


# ── Tasks 3.2 / 3.8 — versioning on the live runner path ────────────────────

_RESPONSE_V1 = (
    "1. summary: Write the migration\ndescription: Add the new columns.\n\n"
    "2. summary: Seed the defaults\ndescription: Fill the config rows.\n"
)
_RESPONSE_V2 = "1. summary: Second-run task\ndescription: Output of version two.\n"


class _AnsweringLLM(LLMPort):
    """An LLM boundary that answers with a fixed transcript every call."""

    def __init__(self, answer: str) -> None:
        self.answer = answer
        self.calls = 0

    async def generate(
        self,
        prompt: str,  # noqa: ARG002
        config: LLMConfig,  # noqa: ARG002
        system_prompt: str | None = None,  # noqa: ARG002
    ) -> str:
        self.calls += 1
        return self.answer


class _RetryingAdapterLLM(_AnsweringLLM):
    """An LLM boundary whose adapter retries internally, then answers.

    Mirrors the real adapter contract: ``OllamaAdapter.generate`` loops up to three
    attempts with backoff before it answers or raises, so the runner sees exactly one
    ``generate`` call no matter how many times the provider was hit. The transient
    failure here never escapes the adapter — which is precisely the case that must not
    disturb versioning.
    """

    async def generate(
        self,
        prompt: str,  # noqa: ARG002
        config: LLMConfig,  # noqa: ARG002
        system_prompt: str | None = None,  # noqa: ARG002
    ) -> str:
        for attempt in range(3):
            self.calls += 1  # counts provider attempts, not runner calls
            try:
                if attempt == 0:
                    raise ConnectionError("transient provider blip, the adapter retries")
                return self.answer
            except ConnectionError:
                continue  # the real adapter backs off here (1s, 2s) before retrying
        raise LLMConnectionError("unreachable: the answer always arrives on attempt 2")


async def _extraction_rows(session: AsyncSession, story_id: UUID) -> list[ExtractionModel]:
    """Read the extraction rows for one story straight off the table."""
    result = await session.execute(
        select(ExtractionModel)
        .where(ExtractionModel.user_story_id == story_id)
        .order_by(ExtractionModel.version_number)
    )
    return list(result.scalars().all())


async def _task_rows(session: AsyncSession, story_id: UUID) -> list[TaskModel]:
    """Read the task rows for one story straight off the table.

    The rows, not the entities a runner or a repository returned, are the witness:
    what versioning guarantees lives in the table, not in memory.
    """
    result = await session.execute(
        select(TaskModel)
        .where(TaskModel.user_story_id == story_id)
        .order_by(TaskModel.created_at, TaskModel.title)
    )
    return list(result.scalars().all())


def _task_snapshot(row: TaskModel) -> tuple:
    """Every column of a task row, for the byte-for-byte comparison task 3.8 needs."""
    return (
        row.id,
        row.user_story_id,
        row.extraction_id,
        row.title,
        row.description,
        row.status,
        row.priority,
        row.labels,
        row.dependencies,
        row.created_at,
        row.updated_at,
    )


@pytest.mark.unit
class TestVersionedTaskRowsOnTheLivePath:
    """What versioning guarantees when the real runner writes tasks (3.2, 3.8).

    The route mints the number at birth and the runner never allocates, so the
    invariants below should already hold on a tree where 3b-i/3b-ii-a landed — these
    cases pin them so a future change to the runner cannot quietly break them.
    """

    async def _seed_pending(self, factory, story_id: UUID) -> Extraction:
        """Birth one pending extraction through the allocation path."""
        async with factory() as session:
            return await seed_extraction(session, story_id, model_used="llama3.2")

    async def _run(
        self,
        monkeypatch,
        test_engine: AsyncEngine,
        pending: Extraction,
        seeded,
        llm: LLMPort,
        *,
        max_retries: int = 0,
    ) -> None:
        """Run the real background task against the test engine with a fake LLM."""
        monkeypatch.setattr(extraction_task, "get_engine", lambda: test_engine)
        monkeypatch.setattr(extraction_task, "OllamaAdapter", lambda **_: llm)
        # The subject here is the rows the runner writes, not retrieval — see the helper.
        _make_the_vector_store_unavailable(monkeypatch)
        await extraction_task.run_background_extraction(
            extraction_id=pending.id,
            story_id=seeded.story_id,
            workspace_id=seeded.workspace_id,
            model="llama3.2",
            max_retries=max_retries,
        )

    @pytest.mark.asyncio
    async def test_the_retry_path_leaves_one_extraction_row_and_one_number(
        self, test_engine: AsyncEngine, monkeypatch, seed_workspace
    ) -> None:
        """A run that retries inside the LLM call never mints a second version.

        The adapter's own retry loop hits the provider twice inside one ``generate``
        call; from the runner's view it is one LLM call for one extraction id, so the
        run must land on the row it already has — one row, one number, completed once.
        """
        factory = async_sessionmaker(bind=test_engine, class_=AsyncSession, expire_on_commit=False)
        seeded = await seed_workspace(member=False)
        pending = await self._seed_pending(factory, seeded.story_id)

        llm = _RetryingAdapterLLM(_RESPONSE_V1)
        await self._run(monkeypatch, test_engine, pending, seeded, llm)

        assert llm.calls == 2, "the run never actually retried, so nothing was exercised"
        async with factory() as session:
            rows = await _extraction_rows(session, seeded.story_id)
            tasks = await _task_rows(session, seeded.story_id)

        assert len(rows) == 1
        assert [row.version_number for row in rows] == [1]
        assert rows[0].status == ExtractionStatus.COMPLETED
        # The retry's tasks belong to the same run, not to some second version.
        assert {task.extraction_id for task in tasks} == {pending.id}

    @pytest.mark.asyncio
    async def test_a_redispatch_of_the_same_extraction_mints_no_second_row_or_number(
        self, test_engine: AsyncEngine, monkeypatch, seed_workspace
    ) -> None:
        """Re-dispatching ``run_background_extraction`` for one extraction id stays one row.

        The dispatch is fire-and-forget, so a doubled ``create_task`` is the accident
        this pins: the second dispatch runs the pipeline again for the same id, and
        versioning must still answer with exactly one extraction row, version 1.
        """
        factory = async_sessionmaker(bind=test_engine, class_=AsyncSession, expire_on_commit=False)
        seeded = await seed_workspace(member=False)
        pending = await self._seed_pending(factory, seeded.story_id)

        first = _AnsweringLLM(_RESPONSE_V1)
        await self._run(monkeypatch, test_engine, pending, seeded, first)

        second = _AnsweringLLM(_RESPONSE_V2)
        await self._run(monkeypatch, test_engine, pending, seeded, second)

        assert first.calls == 1 and second.calls == 1, "the re-dispatch never actually ran"
        async with factory() as session:
            rows = await _extraction_rows(session, seeded.story_id)

        assert len(rows) == 1
        assert [row.version_number for row in rows] == [1]

    @pytest.mark.asyncio
    async def test_every_task_row_the_completed_run_writes_carries_its_extraction_id(
        self, test_engine: AsyncEngine, monkeypatch, seed_workspace
    ) -> None:
        """R5 read back off the table: no task row is orphaned from its run.

        The rows are the witness — the entity the runner built in memory could carry
        the id while the INSERT dropped it, and only the table decides.
        """
        factory = async_sessionmaker(bind=test_engine, class_=AsyncSession, expire_on_commit=False)
        seeded = await seed_workspace(member=False)
        pending = await self._seed_pending(factory, seeded.story_id)

        await self._run(monkeypatch, test_engine, pending, seeded, _AnsweringLLM(_RESPONSE_V1))

        async with factory() as session:
            tasks = await _task_rows(session, seeded.story_id)

        assert len(tasks) == 2
        assert all(task.extraction_id == pending.id for task in tasks)
        assert all(task.extraction_id is not None for task in tasks)

    @pytest.mark.asyncio
    async def test_a_v2_run_mints_new_task_rows_while_v1s_remain(
        self, test_engine: AsyncEngine, monkeypatch, seed_workspace
    ) -> None:
        """A second run adds its own task rows; v1's are neither reused nor deleted.

        The two sets are disjoint by primary key and by extraction: v2's tasks are new
        rows that belong to v2, and v1's rows still carry v1's id with v1's content.
        """
        factory = async_sessionmaker(bind=test_engine, class_=AsyncSession, expire_on_commit=False)
        seeded = await seed_workspace(member=False)
        v1 = await self._seed_pending(factory, seeded.story_id)
        await self._run(monkeypatch, test_engine, v1, seeded, _AnsweringLLM(_RESPONSE_V1))

        v2 = await self._seed_pending(factory, seeded.story_id)
        await self._run(monkeypatch, test_engine, v2, seeded, _AnsweringLLM(_RESPONSE_V2))

        async with factory() as session:
            tasks = await _task_rows(session, seeded.story_id)

        v1_tasks = [task for task in tasks if task.extraction_id == v1.id]
        v2_tasks = [task for task in tasks if task.extraction_id == v2.id]
        assert {task.title for task in v1_tasks} == {"Write the migration", "Seed the defaults"}
        assert {task.title for task in v2_tasks} == {"Second-run task"}
        assert {task.id for task in v1_tasks}.isdisjoint({task.id for task in v2_tasks})
        assert len(tasks) == len(v1_tasks) + len(v2_tasks)

    @pytest.mark.asyncio
    async def test_rerunning_a_story_leaves_v1s_task_rows_byte_for_byte_untouched(
        self, test_engine: AsyncEngine, monkeypatch, seed_workspace
    ) -> None:
        """The invariant the whole slice exists for: a re-run rewrites nothing (3.8).

        v1's rows are captured column-for-column before v2 runs and compared after:
        identical. v2's tasks are new rows, the derived current version is v2, and the
        story-level read still returns both sets.
        """
        factory = async_sessionmaker(bind=test_engine, class_=AsyncSession, expire_on_commit=False)
        seeded = await seed_workspace(member=False)
        v1 = await self._seed_pending(factory, seeded.story_id)
        await self._run(monkeypatch, test_engine, v1, seeded, _AnsweringLLM(_RESPONSE_V1))

        async with factory() as session:
            before = [_task_snapshot(row) for row in await _task_rows(session, seeded.story_id)]
        assert len(before) == 2

        v2 = await self._seed_pending(factory, seeded.story_id)
        await self._run(monkeypatch, test_engine, v2, seeded, _AnsweringLLM(_RESPONSE_V2))

        async with factory() as session:
            rows = await _task_rows(session, seeded.story_id)
            current = await SQLAlchemyExtractionRepository(session).find_current_version(
                seeded.story_id
            )
            story_read = await SQLAlchemyTaskRepository(session).list_by_story(seeded.story_id)

        v1_rows = [row for row in rows if row.extraction_id == v1.id]
        v2_rows = [row for row in rows if row.extraction_id == v2.id]
        # v1's rows, column-for-column, are exactly what they were before v2 ran.
        assert [_task_snapshot(row) for row in v1_rows] == before
        assert len(v2_rows) == 1
        assert {row.id for row in v2_rows}.isdisjoint({snapshot[0] for snapshot in before})
        assert current is not None and current.version_number == 2
        assert len(story_read) == 3


# ── WU1 1.7 — the project enters the prompt on the live runner path ─────────


def _context_block(prompt_rendered: str) -> str:
    """The text between the context header and the story line, for block-level comparison."""
    start = prompt_rendered.index("## Project Context")
    end = prompt_rendered.index("User story:", start)
    return prompt_rendered[start:end]


@pytest.mark.unit
class TestExtractionPromptCarriesTheProject:
    """The runner composes the project into the prompt it renders (WU1 1.7).

    The subject is the stored ``prompt_rendered`` — the context block the
    provider actually received is readable from the row, which is what makes
    these assertions possible without re-rendering anything.
    """

    async def _seed_pending(self, factory, story_id: UUID) -> Extraction:
        """Birth one pending extraction through the allocation path."""
        async with factory() as session:
            return await seed_extraction(session, story_id, model_used="llama3.2")

    async def _run(
        self,
        monkeypatch,
        test_engine: AsyncEngine,
        pending: Extraction,
        story_id: UUID,
        workspace_id: UUID,
        llm: LLMPort,
    ) -> None:
        """Run the real background task against the test engine with a fake LLM."""
        monkeypatch.setattr(extraction_task, "get_engine", lambda: test_engine)
        monkeypatch.setattr(extraction_task, "OllamaAdapter", lambda **_: llm)
        # The subject here is the rendered prompt, not retrieval — see the helper.
        _make_the_vector_store_unavailable(monkeypatch)
        await extraction_task.run_background_extraction(
            extraction_id=pending.id,
            story_id=story_id,
            workspace_id=workspace_id,
            model="llama3.2",
            max_retries=0,
        )

    @pytest.mark.asyncio
    async def test_the_context_block_carries_the_project(
        self, test_engine: AsyncEngine, monkeypatch, seed_workspace
    ) -> None:
        """The prompt names the project, the other stories and their current tasks."""
        factory = async_sessionmaker(bind=test_engine, class_=AsyncSession, expire_on_commit=False)
        seeded = await seed_workspace(stories=2)
        other_story = seeded.story_ids[0]
        story_id = seeded.story_ids[1]

        async with factory() as session:
            completed = await seed_extraction(
                session,
                other_story,
                status=ExtractionStatus.COMPLETED,
                completed_at=datetime.now(UTC),
            )
            await seed_task(
                session, other_story, "Add password reset endpoint", extraction=completed
            )

        pending = await self._seed_pending(factory, story_id)
        await self._run(
            monkeypatch,
            test_engine,
            pending,
            story_id,
            seeded.workspace_id,
            _AnsweringLLM(_RESPONSE_V1),
        )

        async with factory() as session:
            row = (await _extraction_rows(session, story_id))[0]

        assert row.prompt_rendered is not None
        assert "## Project Context" in row.prompt_rendered
        assert "Seeded Project" in row.prompt_rendered
        # The other story's text and its task paired with the owning story id.
        assert (
            "As a user, I want to use seeded feature 0 so that the seeded chain is addressable"
            in row.prompt_rendered
        )
        assert "Add password reset endpoint" in row.prompt_rendered
        assert f"(story: {other_story})" in row.prompt_rendered
        # The story being decomposed appears exactly once — as the story, never as context.
        assert row.prompt_rendered.count("use seeded feature 1") == 1

    @pytest.mark.asyncio
    async def test_a_storys_own_completed_tasks_never_enter_its_own_context_block(
        self, test_engine: AsyncEngine, monkeypatch, seed_workspace
    ) -> None:
        """WU1 1.11 — a story's own previous run is not its own context.

        The story being decomposed carries a completed v1 that produced
        "Implement login retry"; the v2 prompt about to run must not carry that
        title in its existing-tasks block, while a *different* story's "Set up
        database schema" is positive context and is paired with its owning
        story id. The story's own raw text appears exactly once in the whole
        prompt — as the story to decompose, never as context.

        Read-level half: the exclusion-in-``WHERE`` fact this end-to-end case
        rides on is already pinned by
        ``test_repositories/test_task_repo.py::TestListForContext::
        test_the_excluded_story_is_absent_in_every_version`` (v1 + v2 tasks of
        the excluded story, neither returns), so nothing is duplicated here.
        """
        factory = async_sessionmaker(bind=test_engine, class_=AsyncSession, expire_on_commit=False)
        seeded = await seed_workspace(stories=2)
        other_story = seeded.story_ids[0]
        story_id = seeded.story_ids[1]

        async with factory() as session:
            own_v1 = await seed_extraction(
                session,
                story_id,
                status=ExtractionStatus.COMPLETED,
                completed_at=datetime.now(UTC),
            )
            await seed_task(session, story_id, "Implement login retry", extraction=own_v1)
            other_v = await seed_extraction(
                session,
                other_story,
                status=ExtractionStatus.COMPLETED,
                completed_at=datetime.now(UTC),
            )
            await seed_task(session, other_story, "Set up database schema", extraction=other_v)

        pending = await self._seed_pending(factory, story_id)
        await self._run(
            monkeypatch,
            test_engine,
            pending,
            story_id,
            seeded.workspace_id,
            _AnsweringLLM(_RESPONSE_V1),
        )

        async with factory() as session:
            rows = await _extraction_rows(session, story_id)
        row = next(r for r in rows if r.id == pending.id)

        assert row.prompt_rendered is not None
        # The other story's task is positive context, paired with its story.
        assert "Set up database schema" in row.prompt_rendered
        assert f"(story: {other_story})" in row.prompt_rendered
        # The story's own completed v1 task never enters its own block.
        assert "Implement login retry" not in row.prompt_rendered
        # Its raw text appears exactly once — as the story to decompose.
        assert row.prompt_rendered.count("use seeded feature 1") == 1

    @pytest.mark.asyncio
    async def test_an_invalid_task_leaves_every_context_block_and_returns_after_revoke(
        self, test_engine: AsyncEngine, monkeypatch, seed_workspace
    ) -> None:
        """WU1 1.12 — an invalid task is positive context for nobody, until revoked.

        A task of story A carries an active mark: it is absent from the
        existing-tasks block of *every* other story's prompt (two different
        stories are decomposed here), while each of their own valid tasks stays.
        Once the mark is revoked while A's version is still current, the task
        returns to the blocks; the decomposing story's own task stays excluded,
        because the own-story exclusion and the validity rule are independent
        ``WHERE`` terms. Story A is never itself decomposed: a completed run for
        it would mint a newer version and retire the marked task by currency,
        which is the read-level case below, not this one.

        Read-level half: the hide/restore fact is already pinned by
        ``test_repositories/test_task_repo.py::TestListForContext::
        test_an_active_mark_hides_the_task_and_revoking_restores_it``, created
        and revoked through the same invalidation repository used here.
        """
        factory = async_sessionmaker(bind=test_engine, class_=AsyncSession, expire_on_commit=False)
        seeded = await seed_workspace(stories=3)
        marked_story = seeded.story_ids[0]
        first_decomposed = seeded.story_ids[1]
        second_decomposed = seeded.story_ids[2]

        async with factory() as session:
            marked_v = await seed_extraction(
                session,
                marked_story,
                status=ExtractionStatus.COMPLETED,
                completed_at=datetime.now(UTC),
            )
            marked_task = await seed_task(
                session, marked_story, "Implement login retry", extraction=marked_v
            )
            for story_id, title in (
                (first_decomposed, "Configure the billing database"),
                (second_decomposed, "Build the history UI component"),
            ):
                version = await seed_extraction(
                    session,
                    story_id,
                    status=ExtractionStatus.COMPLETED,
                    completed_at=datetime.now(UTC),
                )
                await seed_task(session, story_id, title, extraction=version)
            mark = await SQLAlchemyTaskInvalidationRepository(session).create(
                TaskInvalidation(task_id=marked_task.id, reason="Duplicates the auth task")
            )

        # While the mark is active: no story's prompt carries the marked task.
        # The first decomposing story's block still carries the other story's
        # valid seeded task; the second one's block carries the first story's
        # run-output tasks (its seeded v1 was superseded by its own run).
        for story_id in (first_decomposed, second_decomposed):
            pending = await self._seed_pending(factory, story_id)
            await self._run(
                monkeypatch,
                test_engine,
                pending,
                story_id,
                seeded.workspace_id,
                _AnsweringLLM(_RESPONSE_V1),
            )

        async with factory() as session:
            while_marked = {
                story_id: {
                    row.version_number: row for row in await _extraction_rows(session, story_id)
                }
                for story_id in (first_decomposed, second_decomposed)
            }
        first_while_marked = while_marked[first_decomposed][max(while_marked[first_decomposed])]
        assert first_while_marked.prompt_rendered is not None
        assert "Implement login retry" not in first_while_marked.prompt_rendered
        assert "Build the history UI component" in first_while_marked.prompt_rendered
        # Its own valid task stays out of its own block.
        assert "Configure the billing database" not in first_while_marked.prompt_rendered
        second_while_marked = while_marked[second_decomposed][max(while_marked[second_decomposed])]
        assert second_while_marked.prompt_rendered is not None
        assert "Implement login retry" not in second_while_marked.prompt_rendered
        assert "Write the migration" in second_while_marked.prompt_rendered

        # Revoke while the marked task's version is still current (story A has
        # no newer completed version), through the same write path the
        # endpoint drives.
        async with factory() as session:
            await SQLAlchemyTaskInvalidationRepository(session).revoke(
                mark.id, revoked_by=uuid4(), revoked_at=datetime.now(UTC)
            )

        pending = await self._seed_pending(factory, first_decomposed)
        await self._run(
            monkeypatch,
            test_engine,
            pending,
            first_decomposed,
            seeded.workspace_id,
            _AnsweringLLM(_RESPONSE_V2),
        )

        async with factory() as session:
            after = {
                row.version_number: row for row in await _extraction_rows(session, first_decomposed)
            }
        restored = after[max(after)]
        assert restored.prompt_rendered is not None
        # The task returns as positive context, paired with its owning story.
        assert "Implement login retry" in restored.prompt_rendered
        assert f"(story: {marked_story})" in restored.prompt_rendered
        # The other story's current-version tasks never left (its seeded v1 was
        # superseded by its own run, so the run output is what is current).
        assert "Write the migration" in restored.prompt_rendered
        # The own-story exclusion is independent of validity: the decomposing
        # story's own task stays out of its own block even though it is valid.
        assert "Configure the billing database" not in restored.prompt_rendered
        assert restored.prompt_rendered.count("use seeded feature 1") == 1

    @pytest.mark.asyncio
    async def test_a_description_edit_after_v1_does_not_change_v1s_stored_prompt(
        self, test_engine: AsyncEngine, monkeypatch, seed_workspace
    ) -> None:
        """v1's stored prompt keeps the description it was rendered with; v2's carries the new one.

        The snapshot is what makes the divergence readable: two rows, each
        holding the project state of its own render moment.
        """
        factory = async_sessionmaker(bind=test_engine, class_=AsyncSession, expire_on_commit=False)
        seeded = await seed_workspace()
        story_id = seeded.story_ids[0]

        async with factory() as session:
            project = await SQLAlchemyProjectRepository(session).find_by_id(seeded.project_id)
            assert project is not None
            await SQLAlchemyProjectRepository(session).save(
                replace(project, description="Original description")
            )

        v1 = await self._seed_pending(factory, story_id)
        await self._run(
            monkeypatch, test_engine, v1, story_id, seeded.workspace_id, _AnsweringLLM(_RESPONSE_V1)
        )

        async with factory() as session:
            project = await SQLAlchemyProjectRepository(session).find_by_id(seeded.project_id)
            assert project is not None
            await SQLAlchemyProjectRepository(session).save(
                replace(project, description="Edited description")
            )

        v2 = await self._seed_pending(factory, story_id)
        await self._run(
            monkeypatch, test_engine, v2, story_id, seeded.workspace_id, _AnsweringLLM(_RESPONSE_V2)
        )

        async with factory() as session:
            rows = await _extraction_rows(session, story_id)

        assert [row.version_number for row in rows] == [1, 2]
        assert rows[0].prompt_rendered is not None
        assert rows[1].prompt_rendered is not None
        assert "Original description" in rows[0].prompt_rendered
        assert "Edited description" not in rows[0].prompt_rendered
        assert "Edited description" in rows[1].prompt_rendered
        assert "Original description" not in rows[1].prompt_rendered

    @pytest.mark.asyncio
    async def test_two_runs_over_unchanged_project_state_compose_identical_blocks(
        self, test_engine: AsyncEngine, monkeypatch, seed_workspace
    ) -> None:
        """Same project state → byte-identical context blocks in both stored prompts."""
        factory = async_sessionmaker(bind=test_engine, class_=AsyncSession, expire_on_commit=False)
        seeded = await seed_workspace(stories=2)
        other_story = seeded.story_ids[0]
        story_id = seeded.story_ids[1]

        async with factory() as session:
            completed = await seed_extraction(
                session,
                other_story,
                status=ExtractionStatus.COMPLETED,
                completed_at=datetime.now(UTC),
            )
            await seed_task(
                session, other_story, "Add password reset endpoint", extraction=completed
            )

        first = await self._seed_pending(factory, story_id)
        await self._run(
            monkeypatch,
            test_engine,
            first,
            story_id,
            seeded.workspace_id,
            _AnsweringLLM(_RESPONSE_V1),
        )
        second = await self._seed_pending(factory, story_id)
        await self._run(
            monkeypatch,
            test_engine,
            second,
            story_id,
            seeded.workspace_id,
            _AnsweringLLM(_RESPONSE_V2),
        )

        async with factory() as session:
            rows = await _extraction_rows(session, story_id)

        assert [row.version_number for row in rows] == [1, 2]
        assert rows[0].prompt_rendered is not None
        assert rows[1].prompt_rendered is not None
        assert _context_block(rows[0].prompt_rendered) == _context_block(rows[1].prompt_rendered)

    @pytest.mark.asyncio
    async def test_render_refuses_to_run_without_a_context(self) -> None:
        """The ``context`` argument is required — a call without it fails.

        No default: a caller able to omit it could render 0.8.0's two-variable
        prompt while the row claimed to be a 0.9.0 version. The type carries the
        requirement, so the failure is a ``TypeError`` at the call itself.
        """
        service = ExtractionService(
            llm_port=AsyncMock(),
            prompt_manager=PromptManager(),
            task_parser=TaskParser(),
        )
        story = SimpleNamespace(raw_text="As a user, I want to log in")

        with pytest.raises(TypeError):
            await service.render(
                story,
                system_prompt=None,
                instruction_template=None,
                workspace_id=None,
                few_shot_config=None,
            )


@pytest.mark.unit
class TestWorkspaceTemplateOptOutAtTheRecord:
    """WU1 1.13 — a workspace template that references only ``{{ user_story }}``.

    The spec blesses the opt-out, and the detection contract is the version's
    own record: what the provider received is ``prompt_rendered``'s to say, and
    what was composed lives beside it on the same row — readable afterwards by
    comparing the stored facts, never by re-rendering anything. No runtime
    warning exists or should: it would fire on every run of a workspace that
    chose the opt-out.

    At this head the runner's snapshot (``prompt_config``) records the
    composed *config* (``validate``, ``system_prompt``); filling it from
    ``RenderedPrompt.template_variables`` with the context keys is WU2 task
    2.5's write, so the full snapshot-vs-rendered comparison this class
    documents becomes assertable there (2.6 reads
    ``prompt_config["negative_examples_omitted"]`` back from the row).
    """

    async def _seed_pending(self, factory, story_id: UUID) -> Extraction:
        """Birth one pending extraction through the allocation path."""
        async with factory() as session:
            return await seed_extraction(session, story_id, model_used="llama3.2")

    async def _run(
        self,
        monkeypatch,
        test_engine: AsyncEngine,
        pending: Extraction,
        story_id: UUID,
        workspace_id: UUID,
        llm: LLMPort,
    ) -> None:
        """Run the real background task against the test engine with a fake LLM."""
        monkeypatch.setattr(extraction_task, "get_engine", lambda: test_engine)
        monkeypatch.setattr(extraction_task, "OllamaAdapter", lambda **_: llm)
        # The subject here is the stored record, not retrieval — see the helper.
        _make_the_vector_store_unavailable(monkeypatch)
        await extraction_task.run_background_extraction(
            extraction_id=pending.id,
            story_id=story_id,
            workspace_id=workspace_id,
            model="llama3.2",
            max_retries=0,
        )

    @pytest.mark.asyncio
    async def test_the_opt_out_run_completes_and_the_row_records_what_each_fact_saw(
        self, test_engine: AsyncEngine, monkeypatch, seed_workspace
    ) -> None:
        """The run completes; the stored prompt shows the provider got neither block.

        The other story's data exists in the project when the prompt is
        composed — the row proves the provider never saw it — and the
        snapshot's composed config is still on the row, read back from the
        record and not from any render call.
        """
        factory = async_sessionmaker(bind=test_engine, class_=AsyncSession, expire_on_commit=False)
        seeded = await seed_workspace(stories=2)
        other_story = seeded.story_ids[0]
        story_id = seeded.story_ids[1]

        async with factory() as session:
            completed = await seed_extraction(
                session,
                other_story,
                status=ExtractionStatus.COMPLETED,
                completed_at=datetime.now(UTC),
            )
            await seed_task(
                session, other_story, "Add password reset endpoint", extraction=completed
            )
            await SQLAlchemyWorkspacePromptRepository(session).upsert(
                WorkspacePrompt(
                    workspace_id=seeded.workspace_id,
                    system_prompt="Opted-out system prompt",
                    instruction_template="Break down: {{user_story}}",
                )
            )

        pending = await self._seed_pending(factory, story_id)
        await self._run(
            monkeypatch,
            test_engine,
            pending,
            story_id,
            seeded.workspace_id,
            _AnsweringLLM(_RESPONSE_V1),
        )

        async with factory() as session:
            row = (await _extraction_rows(session, story_id))[0]

        assert row.status is ExtractionStatus.COMPLETED
        assert row.prompt_rendered is not None
        assert "use seeded feature 1" in row.prompt_rendered
        # Neither new block reached the provider.
        assert "## Project Context" not in row.prompt_rendered
        assert (
            "## Do Not Produce These Tasks (Previously Marked Invalid)" not in row.prompt_rendered
        )
        # The context data existed in the project; the opt-out kept it out.
        assert "use seeded feature 0" not in row.prompt_rendered
        assert "Add password reset endpoint" not in row.prompt_rendered
        # The snapshot's composed config, read back from the row: the system
        # prompt was composed and delivered separately, whatever the template
        # chose to interpolate.
        assert (row.prompt_config or {}).get("system_prompt") == "Opted-out system prompt"

    @pytest.mark.asyncio
    async def test_the_opt_out_templates_variables_still_carry_the_composed_context(self) -> None:
        """``RenderedPrompt.template_variables`` carries the keys the template ignores.

        Jinja renders unknown kwargs as unused — the composed context is not
        lost at the render boundary, it is only absent from the rendered text.
        The template half of this contract (the rendered text) is pinned by
        ``test_unit/test_prompt_manager.py::TestTaskGenerationContextBlocks::
        test_a_workspace_template_without_the_variables_renders_neither_block``.
        """
        service = ExtractionService(
            llm_port=AsyncMock(),
            prompt_manager=PromptManager(),
            task_parser=TaskParser(),
        )
        story = SimpleNamespace(raw_text="As a user, I want to log in")

        rendered = await service.render(
            story,
            system_prompt=None,
            instruction_template="Break down: {{user_story}}",
            workspace_id=None,
            few_shot_config=None,
            context=simple_context(),
        )

        assert rendered.instruction == "Break down: As a user, I want to log in"
        assert "## Project Context" not in rendered.text
        # The composed context is in the variables, unused by this template.
        assert rendered.template_variables["project_context"]["name"] == "Test Project"
        assert rendered.template_variables["negative_examples_omitted"] == 0
        assert rendered.template_variables["negative_examples"] == []
