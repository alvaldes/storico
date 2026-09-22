"""Integration tests for extraction API endpoints.

Tests the workspace-scoped routes at
``/api/v1/workspaces/{workspace_id}/extract/``.
"""

import asyncio
from collections.abc import Iterator
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from storico.config.settings import _reset_settings_cache
from storico.domain.entities import Extraction, LLMConnectionError, User
from storico.domain.entities.extraction import ExtractionStatus
from storico.domain.entities.user_story import UserStoryStatus
from storico.domain.ports import LLMConfig, LLMPort, VectorStorePort
from storico.infrastructure.crypto import FernetCipher
from storico.infrastructure.database.models import WorkspaceLLMConfigModel
from storico.infrastructure.database.repositories import (
    SQLAlchemyExtractionRepository,
    SQLAlchemyTaskRepository,
    SQLAlchemyUserRepository,
    SQLAlchemyUserStoryRepository,
    SQLAlchemyWorkspaceLLMConfigRepository,
)
from storico.infrastructure.tasks import extraction_task

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
            pending = await repo.save(
                Extraction(
                    user_story_id=story_id,
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
            pending = await repo.save(
                Extraction(
                    user_story_id=seeded.story_id,
                    model_used="llama3.2",
                    raw_response="",
                    status=ExtractionStatus.PENDING,
                    user_story_status=UserStoryStatus.PENDING_EXTRACTION,
                )
            )

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
            repo = SQLAlchemyExtractionRepository(session)
            pending = await repo.save(
                Extraction(
                    user_story_id=seeded.story_id,
                    model_used="llama3.1:8b",
                    raw_response="",
                    status=ExtractionStatus.PENDING,
                    user_story_status=UserStoryStatus.PENDING_EXTRACTION,
                )
            )

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
        repo = SQLAlchemyExtractionRepository(db_session)

        extraction = Extraction(
            user_story_id=story_id,
            model_used="llama3.2",
            raw_response="1. summary: Task one\ndescription: Desc",
            status=ExtractionStatus.COMPLETED,
        )
        saved = await repo.save(extraction)

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
        repo = SQLAlchemyExtractionRepository(db_session)

        saved = await repo.save(
            Extraction(
                user_story_id=owner.story_id,
                model_used="llama3.2",
                raw_response="",
                status=ExtractionStatus.COMPLETED,
            )
        )

        response = await async_client.get(
            f"/api/v1/workspaces/{foreign.workspace_id}/extract/status/{saved.id}",
            headers=_auth_headers(str(user.id)),
        )
        assert response.status_code == 403
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
        repo = SQLAlchemyExtractionRepository(db_session)

        saved = await repo.save(
            Extraction(
                user_story_id=seeded.story_id,
                model_used="llama3.2",
                raw_response="1. summary: Task one\ndescription: Desc",
                status=ExtractionStatus.COMPLETED,
            )
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
        assert detail["error_code"] == "LLM_CONFIG_INCOMPLETE"
        assert detail["missing"] == ["model"]
        assert detail["provider"] == "ollama"

        # The side effects the refusal exists to prevent: no extraction record, and
        # a story still sitting in its pre-extraction status.
        assert await SQLAlchemyExtractionRepository(db_session).list_by_story(seeded.story_id) == []
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
        assert detail["error_code"] == "LLM_CONFIG_INCOMPLETE"
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
