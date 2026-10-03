"""Unit tests for QdrantAdapter — VEC-T11.

Uses unittest.mock to mock AsyncQdrantClient and EmbeddingPort
so no real network calls or databases are needed.
"""

import inspect
import logging
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest
from qdrant_client.http import models as qdrant_models

from storico.domain.entities.exceptions import VectorStoreError
from storico.domain.ports import VectorStorePort
from storico.infrastructure.vector.qdrant_adapter import QdrantAdapter


def _make_embedding_port(dimensions: int = 3):
    """Build a mock EmbeddingPort with the given dimensions."""
    port = MagicMock()
    port.dimensions = dimensions
    port.embed = AsyncMock()
    return port


def _make_query_response(points):
    """Build a QueryResponse-like object carrying the given scored points."""
    response = MagicMock()
    response.points = points
    return response


class TestQdrantAdapter:
    """QdrantAdapter implements VectorStorePort backed by Qdrant.

    Tests mock both EmbeddingPort and AsyncQdrantClient.
    """

    def setup_method(self) -> None:
        self.workspace_id = uuid4()
        self.project_id = uuid4()
        self.story_id = uuid4()
        self.collection = "test_storico_extractions"
        self.qdrant_url = "http://localhost:6333"

    # ── search_similar — success ────────────────────────────────────

    @pytest.mark.asyncio
    async def test_search_similar_success(self) -> None:
        """Successful search returns ExtractionExample list."""
        port = _make_embedding_port()
        port.embed.return_value = [0.1, 0.2, 0.3]

        mock_point = MagicMock()
        mock_point.score = 0.92
        mock_point.payload = {
            "user_story_text": "As a user, I want login",
            "tasks_summary": "1. Implement auth\n2. Create login form",
            "model_used": "llama3.2",
            "confidence_score": 0.85,
            "workspace_id": str(self.workspace_id),
        }

        adapter = QdrantAdapter(
            embedding_port=port,
            qdrant_url=self.qdrant_url,
            collection_name=self.collection,
            vector_size=3,
        )

        # Mock the internal AsyncQdrantClient
        mock_client = AsyncMock()
        mock_client.get_collections.return_value = MagicMock(collections=[])
        mock_client.create_payload_index = AsyncMock()
        mock_client.query_points.return_value = _make_query_response([mock_point])
        adapter._client = mock_client

        results = await adapter.search_similar(
            text="As a user, I want login",
            limit=3,
            threshold=0.85,
            workspace_id=self.workspace_id,
            exclude_story_id=str(self.story_id),
        )

        assert len(results) == 1
        assert results[0].user_story_text == "As a user, I want login"
        assert results[0].similarity_score == 0.92
        assert results[0].confidence_score == 0.85

    @pytest.mark.asyncio
    async def test_search_similar_uses_workspace_filter(self) -> None:
        """The search sends a filter scoped to the workspace id."""
        port = _make_embedding_port()
        port.embed.return_value = [0.1, 0.2, 0.3]

        adapter = QdrantAdapter(
            embedding_port=port,
            qdrant_url=self.qdrant_url,
            collection_name=self.collection,
            vector_size=3,
        )

        mock_client = AsyncMock()
        mock_client.get_collections.return_value = MagicMock(collections=[])
        mock_client.create_payload_index = AsyncMock()
        mock_client.query_points.return_value = _make_query_response([])
        adapter._client = mock_client

        await adapter.search_similar(
            text="test",
            workspace_id=self.workspace_id,
            exclude_story_id=str(self.story_id),
        )

        mock_client.query_points.assert_called_once()
        call_kwargs = mock_client.query_points.call_args[1]
        query_filter = call_kwargs["query_filter"]
        # The filter restricts results to this workspace
        assert query_filter.must[0].key == "workspace_id"
        assert query_filter.must[0].match.value == str(self.workspace_id)

    @pytest.mark.asyncio
    async def test_search_similar_is_always_scoped_and_scope_is_required(self) -> None:
        """A search is always workspace-filtered; the scope cannot be omitted.

        Replaces the former ``test_search_similar_without_workspace_sends_no_filter``
        test, which pinned the leak: an unscoped lookup returned points from every
        workspace, so other workspaces' user stories were injected into this
        workspace's prompt. The scope is now required on both the port and the
        adapter, so re-adding a default makes this test fail.
        """
        port = _make_embedding_port()
        port.embed.return_value = [0.1, 0.2, 0.3]

        adapter = QdrantAdapter(
            embedding_port=port,
            qdrant_url=self.qdrant_url,
            collection_name=self.collection,
            vector_size=3,
        )

        mock_client = AsyncMock()
        mock_client.query_points.return_value = _make_query_response([])
        adapter._client = mock_client

        await adapter.search_similar(
            text="test",
            workspace_id=self.workspace_id,
            exclude_story_id=str(self.story_id),
        )

        call_kwargs = mock_client.query_points.call_args[1]
        query_filter = call_kwargs["query_filter"]
        # Every search carries the workspace filter — never None.
        assert query_filter is not None
        assert query_filter.must[0].key == "workspace_id"
        assert query_filter.must[0].match.value == str(self.workspace_id)

        # Omitting the scope is not expressible on either the port or the
        # adapter: no default exists, so the call fails before any search runs.
        # ``bind`` is given an explicit ``self``, so the only failure it can
        # report is the missing ``workspace_id`` — re-adding a default makes the
        # bind succeed and fails here. Without that ``self`` the bind would raise
        # for the missing ``self`` first and pass no matter what.
        for target in (VectorStorePort.search_similar, QdrantAdapter.search_similar):
            signature = inspect.signature(target)
            scope_param = signature.parameters["workspace_id"]
            assert scope_param.default is inspect.Parameter.empty
            with pytest.raises(TypeError, match="workspace_id"):
                signature.bind(object(), text="test")

    @pytest.mark.asyncio
    async def test_search_similar_with_explicit_none_still_sends_a_filter(self) -> None:
        """An explicit ``None`` scope can never produce an unfiltered query.

        The annotation says ``workspace_id: UUID``, but nothing stops a caller
        from passing ``None`` at runtime. This pins what the adapter does with
        that call: it still sends a ``workspace_id`` filter to ``query_points``.
        The one adapter-only edit that would silently reopen the cross-workspace
        leak -- ``query_filter = ... if workspace_id is not None else None`` --
        makes this assertion fail, while the non-null tests above stay green.
        """
        port = _make_embedding_port()
        port.embed.return_value = [0.1, 0.2, 0.3]

        adapter = QdrantAdapter(
            embedding_port=port,
            qdrant_url=self.qdrant_url,
            collection_name=self.collection,
            vector_size=3,
        )

        mock_client = AsyncMock()
        mock_client.query_points.return_value = _make_query_response([])
        adapter._client = mock_client

        # ``cast`` rather than ``# type: ignore[arg-type]``: no type checker runs
        # in this gate, so the cast only documents the deliberate breach of the
        # annotation. Either spelling keeps the call legal at runtime.
        await adapter.search_similar(
            text="test",
            workspace_id=cast(UUID, None),
            exclude_story_id=str(self.story_id),
        )

        call_kwargs = mock_client.query_points.call_args[1]
        query_filter = call_kwargs["query_filter"]
        # Not None: the query stays filtered even for a runtime ``None`` scope.
        assert query_filter is not None
        assert query_filter.must[0].key == "workspace_id"

    @pytest.mark.asyncio
    async def test_search_similar_carries_the_fail_closed_validity_filter(self) -> None:
        """The search filter is the unified exclusion expression: valid points only.

        The built filter must carry exactly this shape:

        - ``must``: ``workspace_id == str(workspace_id)`` **and**
          ``has_invalid_tasks == False``;
        - ``must_not``: ``user_story_id == str(exclude_story_id)``.

        The validity rule is asserted as a **positive ``must`` on ``False``**,
        never a ``must_not`` on ``True`` — and that is not a stylistic choice:
        ``must_not`` on ``True`` still admits a point with **no**
        ``has_invalid_tasks`` key at all, so a point written before this slice
        existed would sail through the validity rule and be retrieved as if it
        were valid. ``must`` on ``False`` is fail-closed: a legacy point without
        the key matches neither branch and is never retrieved.
        """
        port = _make_embedding_port()
        port.embed.return_value = [0.1, 0.2, 0.3]

        adapter = QdrantAdapter(
            embedding_port=port,
            qdrant_url=self.qdrant_url,
            collection_name=self.collection,
            vector_size=3,
        )

        mock_client = AsyncMock()
        mock_client.query_points.return_value = _make_query_response([])
        adapter._client = mock_client

        exclude_story_id = uuid4()
        await adapter.search_similar(
            text="test",
            workspace_id=self.workspace_id,
            exclude_story_id=str(exclude_story_id),
        )

        mock_client.query_points.assert_called_once()
        query_filter = mock_client.query_points.call_args[1]["query_filter"]

        # ``must``: the workspace scope plus the positive validity condition.
        must = query_filter.must
        assert [condition.key for condition in must] == ["workspace_id", "has_invalid_tasks"]
        assert must[0].match.value == str(self.workspace_id)
        assert must[1].match.value is False

        # ``must_not``: the story's own point, string-typed like the payload.
        must_not = query_filter.must_not
        assert must_not is not None
        assert [condition.key for condition in must_not] == ["user_story_id"]
        assert must_not[0].match.value == str(exclude_story_id)

    def test_search_similar_requires_exclude_story_id(self) -> None:
        """The story exclusion is required on both the port and the adapter.

        Retrieval has two unconditional rules — never return the story's own
        run, never return an invalid-marked extraction — and neither may be
        opt-out: a caller that could omit ``exclude_story_id`` would retrieve
        the story's own previous version as its own few-shot example. Following
        the ``workspace_id`` pin above, the parameter is keyword-only with no
        default, so re-adding one makes the bind succeed and fails here.
        """
        for target in (VectorStorePort.search_similar, QdrantAdapter.search_similar):
            signature = inspect.signature(target)
            param = signature.parameters.get("exclude_story_id")
            assert param is not None, (
                f"{target.__qualname__} must require keyword-only exclude_story_id"
            )
            assert param.kind is inspect.Parameter.KEYWORD_ONLY
            assert param.default is inspect.Parameter.empty
            with pytest.raises(TypeError, match="exclude_story_id"):
                signature.bind(object(), text="test", workspace_id=uuid4())

    @pytest.mark.asyncio
    async def test_search_similar_empty(self) -> None:
        """Empty search results return empty list."""
        port = _make_embedding_port()
        port.embed.return_value = [0.1, 0.2, 0.3]

        adapter = QdrantAdapter(
            embedding_port=port,
            qdrant_url=self.qdrant_url,
            collection_name=self.collection,
            vector_size=3,
        )

        mock_client = AsyncMock()
        mock_client.query_points.return_value = _make_query_response([])
        adapter._client = mock_client

        results = await adapter.search_similar(
            text="test",
            workspace_id=self.workspace_id,
            exclude_story_id=str(self.story_id),
        )
        assert results == []

    # ── search_similar — graceful degradation ────────────────────────

    @pytest.mark.asyncio
    async def test_search_similar_embedding_fails(self) -> None:
        """Embedding failure returns empty list gracefully."""
        port = _make_embedding_port()
        port.embed.return_value = []

        adapter = QdrantAdapter(
            embedding_port=port,
            qdrant_url=self.qdrant_url,
            collection_name=self.collection,
        )

        results = await adapter.search_similar(
            text="test",
            workspace_id=self.workspace_id,
            exclude_story_id=str(self.story_id),
        )
        assert results == []

    @pytest.mark.asyncio
    async def test_search_similar_qdrant_error(self) -> None:
        """Qdrant search error returns empty list gracefully."""
        port = _make_embedding_port()
        port.embed.return_value = [0.1, 0.2, 0.3]

        adapter = QdrantAdapter(
            embedding_port=port,
            qdrant_url=self.qdrant_url,
            collection_name=self.collection,
            vector_size=3,
        )

        mock_client = AsyncMock()
        mock_client.query_points.side_effect = RuntimeError("Qdrant down")
        adapter._client = mock_client

        results = await adapter.search_similar(
            text="test",
            workspace_id=self.workspace_id,
            exclude_story_id=str(self.story_id),
        )
        assert results == []

    # ── store_extraction — success ───────────────────────────────────

    @pytest.mark.asyncio
    async def test_store_extraction_success(self) -> None:
        """Successful store calls upsert with correct payload."""
        port = _make_embedding_port()
        port.embed.return_value = [0.1, 0.2, 0.3]

        adapter = QdrantAdapter(
            embedding_port=port,
            qdrant_url=self.qdrant_url,
            collection_name=self.collection,
            vector_size=3,
        )

        mock_client = AsyncMock()
        mock_client.get_collections.return_value = MagicMock(collections=[])
        mock_client.create_payload_index = AsyncMock()
        adapter._client = mock_client

        stored = await adapter.store_extraction(
            extraction_id="ext-123",
            user_story_text="As a user, I want login",
            tasks_summary="1. Implement auth",
            model_used="llama3.2",
            workspace_id=self.workspace_id,
            project_id=self.project_id,
            version_number=1,
            confidence_score=0.85,
            user_story_id="story-456",
        )

        # A landed point is reported as stored; the seed job counts only these.
        assert stored is True
        mock_client.upsert.assert_called_once()
        call_args = mock_client.upsert.call_args[1]
        assert call_args["collection_name"] == self.collection
        points = call_args["points"]
        assert len(points) == 1
        assert points[0].id == "ext-123"
        assert points[0].vector == [0.1, 0.2, 0.3]
        assert points[0].payload["model_used"] == "llama3.2"

    @pytest.mark.asyncio
    async def test_store_extraction_writes_workspace_id(self) -> None:
        """Stored point payload contains the workspace_id."""
        port = _make_embedding_port()
        port.embed.return_value = [0.1, 0.2, 0.3]

        adapter = QdrantAdapter(
            embedding_port=port,
            qdrant_url=self.qdrant_url,
            collection_name=self.collection,
            vector_size=3,
        )

        mock_client = AsyncMock()
        mock_client.get_collections.return_value = MagicMock(collections=[])
        mock_client.create_payload_index = AsyncMock()
        adapter._client = mock_client

        await adapter.store_extraction(
            extraction_id="ext-1",
            user_story_text="story text",
            tasks_summary="task list",
            model_used="llama3.2",
            workspace_id=self.workspace_id,
            project_id=self.project_id,
            version_number=1,
        )

        call_args = mock_client.upsert.call_args[1]
        payload = call_args["points"][0].payload
        assert payload["workspace_id"] == str(self.workspace_id)

    # ── store_extraction — graceful degradation ──────────────────────

    @pytest.mark.asyncio
    async def test_store_extraction_embedding_fails(self, caplog: pytest.LogCaptureFixture) -> None:
        """Embedding failure skips store (no qdrant call) and logs one loud ERROR.

        The skip itself is deliberate graceful degradation — the port returns ``False``
        and never raises. What changed is that the skip is no longer silent: an empty
        embedding once meant an extraction's RAG point vanished with nothing observable
        anywhere, because the embedding service degrades connection errors to ``[]``.
        """
        port = _make_embedding_port()
        port.embed.return_value = []

        adapter = QdrantAdapter(
            embedding_port=port,
            qdrant_url=self.qdrant_url,
            collection_name=self.collection,
        )

        mock_client = AsyncMock()
        adapter._client = mock_client

        with caplog.at_level(logging.ERROR, logger="storico.infrastructure.vector.qdrant_adapter"):
            stored = await adapter.store_extraction(
                extraction_id="ext-123",
                user_story_text="test",
                tasks_summary="tasks",
                model_used="test",
                workspace_id=self.workspace_id,
                project_id=self.project_id,
                version_number=1,
            )

        # Nothing landed, so the store reports a skip rather than success.
        assert stored is False
        mock_client.upsert.assert_not_called()

        # Exactly one ERROR record, asserted on the record itself (not just the message
        # string) so the structured fields are pinned, not only the prose.
        error_records = [r for r in caplog.records if r.levelno == logging.ERROR]
        assert len(error_records) == 1
        record = error_records[0]
        assert "empty embedding" in record.getMessage().lower()
        assert record.extraction_id == "ext-123"
        assert record.collection == self.collection
        assert record.reason == "empty_embedding"

    @pytest.mark.asyncio
    async def test_store_extraction_qdrant_error(self) -> None:
        """Qdrant error silently skips store (graceful degradation)."""
        port = _make_embedding_port()
        port.embed.return_value = [0.1, 0.2, 0.3]

        adapter = QdrantAdapter(
            embedding_port=port,
            qdrant_url=self.qdrant_url,
            collection_name=self.collection,
            vector_size=3,
        )

        mock_client = AsyncMock()
        mock_client.upsert.side_effect = RuntimeError("Qdrant down")
        adapter._client = mock_client

        stored = await adapter.store_extraction(
            extraction_id="ext-123",
            user_story_text="test",
            tasks_summary="tasks",
            model_used="test",
            workspace_id=self.workspace_id,
            project_id=self.project_id,
            version_number=1,
        )

        # A rejected upsert is a failure, never a silent success.
        assert stored is False

    @pytest.mark.asyncio
    async def test_store_extraction_client_unavailable_logs_one_error_record(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """An unavailable Qdrant client logs one ERROR with the shared field shape.

        The graceful-degradation contract (``False``, never raises) must survive, but
        every failure path of ``store_extraction`` must be observable with the same
        ``extraction_id`` / ``collection`` / ``reason`` fields, so an operator can
        correlate a missing RAG point with its cause from the log alone.
        """
        port = _make_embedding_port(dimensions=3)
        port.embed.return_value = [0.1, 0.2, 0.3]

        adapter = QdrantAdapter(
            embedding_port=port,
            qdrant_url=self.qdrant_url,
            collection_name=self.collection,
            vector_size=3,
        )
        # Force a fresh lazy init so the client is actually built (and fails) below.
        adapter._client = None

        with caplog.at_level(logging.ERROR, logger="storico.infrastructure.vector.qdrant_adapter"):
            with patch(
                "storico.infrastructure.vector.qdrant_adapter.AsyncQdrantClient",
                side_effect=RuntimeError("connection refused"),
            ):
                stored = await adapter.store_extraction(
                    extraction_id="ext-42",
                    user_story_text="test",
                    tasks_summary="tasks",
                    model_used="test",
                    workspace_id=self.workspace_id,
                    project_id=self.project_id,
                    version_number=1,
                )

        # The port's contract: a skip, never a raise.
        assert stored is False

        error_records = [r for r in caplog.records if r.levelno == logging.ERROR]
        assert len(error_records) == 1
        record = error_records[0]
        assert record.extraction_id == "ext-42"
        assert record.collection == self.collection
        assert record.reason == "client_unavailable"

    @pytest.mark.asyncio
    async def test_store_extraction_upsert_failure_logs_one_error_record(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """A failed upsert logs one ERROR with the shared field shape, not a warning.

        A lost RAG point is an incident-shaped outcome (it silently degraded future
        few-shot prompts), so it must be logged at ERROR like the other skip paths.
        """
        port = _make_embedding_port()
        port.embed.return_value = [0.1, 0.2, 0.3]

        adapter = QdrantAdapter(
            embedding_port=port,
            qdrant_url=self.qdrant_url,
            collection_name=self.collection,
            vector_size=3,
        )

        mock_client = AsyncMock()
        mock_client.upsert.side_effect = RuntimeError("Qdrant down")
        adapter._client = mock_client

        with caplog.at_level(logging.ERROR, logger="storico.infrastructure.vector.qdrant_adapter"):
            stored = await adapter.store_extraction(
                extraction_id="ext-7",
                user_story_text="test",
                tasks_summary="tasks",
                model_used="test",
                workspace_id=self.workspace_id,
                project_id=self.project_id,
                version_number=1,
            )

        assert stored is False

        error_records = [r for r in caplog.records if r.levelno == logging.ERROR]
        assert len(error_records) == 1
        record = error_records[0]
        assert record.extraction_id == "ext-7"
        assert record.collection == self.collection
        assert record.reason == "upsert_failed"

    # ── Lazy init / collection ensure ─────────────────────────────────

    @pytest.mark.asyncio
    async def test_lazy_init_creates_collection_and_index(self) -> None:
        """Collection and payload index created on first use if missing."""
        port = _make_embedding_port()
        port.embed.return_value = [0.1, 0.2, 0.3]

        adapter = QdrantAdapter(
            embedding_port=port,
            qdrant_url=self.qdrant_url,
            collection_name=self.collection,
            vector_size=3,
        )

        mock_client = AsyncMock()
        mock_get_collections = MagicMock()
        mock_get_collections.collections = []
        mock_client.get_collections.return_value = mock_get_collections
        mock_client.create_payload_index = AsyncMock()

        with patch(
            "storico.infrastructure.vector.qdrant_adapter.AsyncQdrantClient",
            return_value=mock_client,
        ):
            client = await adapter._get_client()

        assert client is mock_client
        mock_client.create_collection.assert_called_once()
        # All three filtered fields are ensured (see the dedicated schema test
        # below for the per-field schemas this generalised loop issues).
        ensured = {
            call.kwargs["field_name"] for call in mock_client.create_payload_index.call_args_list
        }
        assert ensured == {"workspace_id", "project_id", "has_invalid_tasks"}
        # Index is created with the boolean schema on the last ensured field;
        # the workspace_id/project_id keyword schemas are pinned by the
        # dedicated three-index test below.
        idx_call = mock_client.create_payload_index.call_args[1]
        assert idx_call["field_name"] == "has_invalid_tasks"
        assert idx_call["field_schema"] == qdrant_models.PayloadSchemaType.BOOL

    @pytest.mark.asyncio
    async def test_existing_collection_skips_create_but_ensures_index(self) -> None:
        """Existing collection is not recreated; payload index still ensured."""
        port = _make_embedding_port()
        port.embed.return_value = [0.1, 0.2, 0.3]

        adapter = QdrantAdapter(
            embedding_port=port,
            qdrant_url=self.qdrant_url,
            collection_name=self.collection,
            vector_size=3,
        )

        mock_client = AsyncMock()
        mock_get_collections = MagicMock()
        mock_get_collections.collections = [SimpleNamespace(name=self.collection)]
        mock_client.get_collections.return_value = mock_get_collections
        mock_client.create_payload_index = AsyncMock()

        with patch(
            "storico.infrastructure.vector.qdrant_adapter.AsyncQdrantClient",
            return_value=mock_client,
        ):
            client = await adapter._get_client()

        assert client is mock_client
        mock_client.create_collection.assert_not_called()
        # The payload indexes are still ensured on an existing collection.
        ensured = {
            call.kwargs["field_name"] for call in mock_client.create_payload_index.call_args_list
        }
        assert ensured == {"workspace_id", "project_id", "has_invalid_tasks"}

    @pytest.mark.asyncio
    async def test_lazy_init_creates_the_three_payload_indexes_with_their_schemas(self) -> None:
        """All three filtered fields get payload indexes, with per-field schemas.

        The read side of WU3 filters on ``workspace_id`` and ``has_invalid_tasks``
        and stores ``project_id``, so all three need indexes for the filtered
        searches to stay fast — one ``_ensure_payload_indexes`` loop behind one
        flag, called from ``_get_client`` right after the collection is ensured.
        ``workspace_id``/``project_id`` are stored as strings (``KEYWORD``);
        ``has_invalid_tasks`` is a JSON boolean, given ``PayloadSchemaType.BOOL``
        — the schema the pinned ``qdrant_client`` accepts (verified against the
        installed client's ``PayloadSchemaType`` enum, so this pins the schema
        the running dependency actually resolves).
        """
        port = _make_embedding_port()
        port.embed.return_value = [0.1, 0.2, 0.3]

        adapter = QdrantAdapter(
            embedding_port=port,
            qdrant_url=self.qdrant_url,
            collection_name=self.collection,
            vector_size=3,
        )

        mock_client = AsyncMock()
        mock_get_collections = MagicMock()
        mock_get_collections.collections = []
        mock_client.get_collections.return_value = mock_get_collections
        mock_client.create_payload_index = AsyncMock()

        with patch(
            "storico.infrastructure.vector.qdrant_adapter.AsyncQdrantClient",
            return_value=mock_client,
        ):
            await adapter._get_client()

        calls = mock_client.create_payload_index.call_args_list
        schemas = {call.kwargs["field_name"]: call.kwargs["field_schema"] for call in calls}
        assert schemas == {
            "workspace_id": qdrant_models.PayloadSchemaType.KEYWORD,
            "project_id": qdrant_models.PayloadSchemaType.KEYWORD,
            "has_invalid_tasks": qdrant_models.PayloadSchemaType.BOOL,
        }
        # Every index request waits for the index to be built before returning.
        assert all(call.kwargs["wait"] is True for call in calls)

    @pytest.mark.asyncio
    async def test_dimension_mismatch_raises(self) -> None:
        """A provider whose dimensions differ from the collection fails fast."""
        port = _make_embedding_port(dimensions=1536)
        adapter = QdrantAdapter(
            embedding_port=port,
            qdrant_url=self.qdrant_url,
            collection_name=self.collection,
            vector_size=768,
        )
        # Force a fresh lazy init so dimensions are validated before any client
        # connection attempt.
        adapter._client = None

        with pytest.raises(ValueError, match="dimensions"):
            await adapter.search_similar(
                text="test",
                workspace_id=self.workspace_id,
                exclude_story_id=str(self.story_id),
            )

    @pytest.mark.asyncio
    async def test_lazy_init_connection_error_returns_empty(self) -> None:
        """Connection error during lazy init returns None; methods return empty."""
        port = _make_embedding_port(dimensions=768)
        port.embed.return_value = [0.1, 0.2, 0.3]

        adapter = QdrantAdapter(
            embedding_port=port,
            qdrant_url="http://invalid:6333",
            collection_name=self.collection,
        )
        # Force a fresh lazy init and make the client connection fail gracefully.
        adapter._client = None

        with patch(
            "storico.infrastructure.vector.qdrant_adapter.AsyncQdrantClient",
            side_effect=RuntimeError("connection refused"),
        ):
            results = await adapter.search_similar(
                text="test",
                workspace_id=self.workspace_id,
                exclude_story_id=str(self.story_id),
            )
            assert results == []

            stored = await adapter.store_extraction(
                extraction_id="ext-1",
                user_story_text="test",
                tasks_summary="tasks",
                model_used="test",
                workspace_id=self.workspace_id,
                project_id=self.project_id,
                version_number=1,
            )
            # No client means nothing was stored.
            assert stored is False

    # ── Payload structure ────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_store_extraction_payload_has_all_fields(self) -> None:
        """Stored point payload contains all expected fields."""
        port = _make_embedding_port()
        port.embed.return_value = [0.1, 0.2, 0.3]

        adapter = QdrantAdapter(
            embedding_port=port,
            qdrant_url=self.qdrant_url,
            collection_name=self.collection,
            vector_size=3,
        )

        mock_client = AsyncMock()
        adapter._client = mock_client

        await adapter.store_extraction(
            extraction_id="ext-1",
            user_story_text="story text",
            tasks_summary="task list",
            model_used="llama3.2",
            workspace_id=self.workspace_id,
            project_id=self.project_id,
            version_number=3,
            confidence_score=0.9,
            user_story_id="story-1",
        )

        call_args = mock_client.upsert.call_args[1]
        payload = call_args["points"][0].payload
        assert payload["user_story_text"] == "story text"
        assert payload["tasks_summary"] == "task list"
        assert payload["model_used"] == "llama3.2"
        assert payload["workspace_id"] == str(self.workspace_id)
        assert payload["confidence_score"] == 0.9
        assert payload["user_story_id"] == "story-1"
        assert "created_at" in payload
        # (c)'s three new keys — the pinned payload grows from seven to ten.
        # ``project_id`` scopes the point to its project, ``version_number`` ties
        # it to the run that produced it (D22: a retry reuses the number the route
        # returned), and a point is born valid — ``has_invalid_tasks`` starts
        # ``False`` and only the mark handlers' refresh flips it.
        assert payload["project_id"] == str(self.project_id)
        assert payload["version_number"] == 3
        assert payload["has_invalid_tasks"] is False

    @pytest.mark.asyncio
    async def test_search_similar_maps_null_score(self) -> None:
        """Null score in qdrant result maps to 0.0 similarity."""
        port = _make_embedding_port()
        port.embed.return_value = [0.1, 0.2, 0.3]

        adapter = QdrantAdapter(
            embedding_port=port,
            qdrant_url=self.qdrant_url,
            collection_name=self.collection,
            vector_size=3,
        )

        mock_point = MagicMock()
        mock_point.score = None  # null score
        mock_point.payload = {
            "user_story_text": "test",
            "tasks_summary": "tasks",
            "model_used": "test",
        }

        mock_client = AsyncMock()
        mock_client.query_points.return_value = _make_query_response([mock_point])
        adapter._client = mock_client

        results = await adapter.search_similar(
            text="test",
            workspace_id=self.workspace_id,
            exclude_story_id=str(self.story_id),
        )
        assert len(results) == 1
        assert results[0].similarity_score == 0.0

    # ── delete_by_story — destructive cleanup (raises, unlike store/search) ──
    #
    # These cases exercise the adapter against a fake AsyncQdrantClient, so they
    # prove the calls the adapter ISSUES (filter shape, wait=True, error mapping) —
    # not that a real Qdrant actually drops the points. The real round trip is
    # proven where a Docker daemon exists (task 4.16 / CI); a fake-client green
    # here must never be read as "the collection really lost its points".

    @pytest.mark.asyncio
    async def test_delete_by_story_filters_on_both_payload_keys_as_strings(self) -> None:
        """The delete filter carries both workspace_id and user_story_id, string-typed.

        ``store_extraction`` writes ``workspace_id`` as ``str(workspace_id)`` and
        ``user_story_id`` as a plain string, so the filter must carry the exact
        same string-typed values: a type mismatch would match nothing, delete no
        points, and still look like success. A filter missing either key would
        silently over-delete (other stories' points in the workspace) or
        under-delete (orphan points of the deleted story).
        """
        port = _make_embedding_port(dimensions=3)
        adapter = QdrantAdapter(
            embedding_port=port,
            qdrant_url=self.qdrant_url,
            collection_name=self.collection,
            vector_size=3,
        )

        mock_client = AsyncMock()
        adapter._client = mock_client

        await adapter.delete_by_story(
            workspace_id=self.workspace_id,
            user_story_id="story-456",
        )

        mock_client.delete.assert_called_once()
        call_kwargs = mock_client.delete.call_args[1]
        assert call_kwargs["collection_name"] == self.collection

        selector = call_kwargs["points_selector"]
        conditions = selector.filter.must
        by_key = {c.key: c.match.value for c in conditions}
        assert set(by_key) == {"workspace_id", "user_story_id"}
        assert by_key["workspace_id"] == str(self.workspace_id)
        assert isinstance(by_key["workspace_id"], str)
        assert by_key["user_story_id"] == "story-456"
        assert isinstance(by_key["user_story_id"], str)

    @pytest.mark.asyncio
    async def test_delete_by_story_waits_for_the_delete_to_apply(self) -> None:
        """The delete is sent with wait=True, not fire-and-forget.

        The caller (story deletion) must not proceed to the relational delete
        believing the points are gone: ``wait=True`` is what makes "no points
        remain retrievable" true when the response returns rather than
        eventually. Asserted on the actual call kwargs, not assumed.
        """
        port = _make_embedding_port(dimensions=3)
        adapter = QdrantAdapter(
            embedding_port=port,
            qdrant_url=self.qdrant_url,
            collection_name=self.collection,
            vector_size=3,
        )

        mock_client = AsyncMock()
        adapter._client = mock_client

        await adapter.delete_by_story(
            workspace_id=self.workspace_id,
            user_story_id="story-456",
        )

        call_kwargs = mock_client.delete.call_args[1]
        assert call_kwargs["wait"] is True

    @pytest.mark.asyncio
    async def test_delete_by_story_driver_failure_raises_vector_store_error(self) -> None:
        """A Qdrant failure surfaces as VectorStoreError, not a swallow.

        This deliberately breaks the file's own convention: ``store_extraction``
        returns ``False`` on the same failure, but a destructive operation must
        not proceed on an unverified cleanup — a delete that was believed to
        happen but didn't leaves orphan points answering future similarity
        searches for a story that no longer exists. Asserting the exact type also
        proves the raw driver error is not allowed to escape unwrapped.
        """
        port = _make_embedding_port(dimensions=3)
        adapter = QdrantAdapter(
            embedding_port=port,
            qdrant_url=self.qdrant_url,
            collection_name=self.collection,
            vector_size=3,
        )

        mock_client = AsyncMock()
        mock_client.delete.side_effect = RuntimeError("Qdrant down")
        adapter._client = mock_client

        with pytest.raises(VectorStoreError, match="Qdrant down"):
            await adapter.delete_by_story(
                workspace_id=self.workspace_id,
                user_story_id="story-456",
            )

    @pytest.mark.asyncio
    async def test_delete_by_story_client_unavailable_raises(self) -> None:
        """An unavailable client raises instead of returning quietly.

        "No vector store configured" and "a vector store that cannot be reached"
        are different outcomes. The service (W4-T7) skips this call entirely when
        there is no store at all — a legitimate completion, since no points exist
        to clean. Here a store IS configured but its lazy init fails (the
        constructor's connection attempt raises, so ``_get_client`` returns
        ``None``), and that path must raise: the destructive path must not
        continue on an unverified cleanup.
        """
        port = _make_embedding_port(dimensions=3)
        adapter = QdrantAdapter(
            embedding_port=port,
            qdrant_url=self.qdrant_url,
            collection_name=self.collection,
            vector_size=3,
        )
        # Force a fresh lazy init so the client is actually built (and fails) below.
        adapter._client = None

        with patch(
            "storico.infrastructure.vector.qdrant_adapter.AsyncQdrantClient",
            side_effect=RuntimeError("connection refused"),
        ):
            with pytest.raises(VectorStoreError, match="unavailable"):
                await adapter.delete_by_story(
                    workspace_id=self.workspace_id,
                    user_story_id="story-456",
                )

    # ── set_has_invalid_tasks — the validity flag refresh ─────────────
    #
    # Same evidence class as the delete_by_story block above: these cases prove
    # the calls the adapter ISSUES against a fake AsyncQdrantClient — the point
    # id, the merged payload, wait=True, the error posture. Whether a real
    # Qdrant actually treats a missing point as a no-op is task 3.9's live
    # proof; a fake-client green here must never be read as that.

    @pytest.mark.asyncio
    async def test_set_has_invalid_tasks_flags_the_point_by_extraction_id(self) -> None:
        """The refresh addresses the point whose id IS the extraction id, and waits.

        ``store_extraction`` upserts with ``id=extraction_id``, so no search is
        needed to find the point: ``set_payload`` is issued directly with
        ``points=[extraction_id]``. The payload carries only the flag —
        ``set_payload`` merges it into the stored payload, so the other nine
        keys survive without a re-embed or re-upsert. ``wait=True`` makes the
        flag observable when the call returns, which the mark handlers'
        ordering (refresh before the relational write) depends on.
        """
        port = _make_embedding_port(dimensions=3)
        adapter = QdrantAdapter(
            embedding_port=port,
            qdrant_url=self.qdrant_url,
            collection_name=self.collection,
            vector_size=3,
        )

        mock_client = AsyncMock()
        adapter._client = mock_client

        await adapter.set_has_invalid_tasks(extraction_id="ext-123", has_invalid_tasks=True)

        mock_client.set_payload.assert_called_once()
        call_kwargs = mock_client.set_payload.call_args[1]
        assert call_kwargs["collection_name"] == self.collection
        assert call_kwargs["points"] == ["ext-123"]
        assert call_kwargs["payload"] == {"has_invalid_tasks": True}
        assert call_kwargs["wait"] is True

    @pytest.mark.asyncio
    async def test_set_has_invalid_tasks_false_clears_the_flag(self) -> None:
        """Revoking the last active mark writes ``False`` — the flag flips both ways.

        The same setter serves the create path (``True``, before the mark row is
        persisted) and the revoke path (``False``, when
        ``count_active_for_extraction`` returns 0), so the payload value must be
        the caller's, not a hardcoded ``True``.
        """
        port = _make_embedding_port(dimensions=3)
        adapter = QdrantAdapter(
            embedding_port=port,
            qdrant_url=self.qdrant_url,
            collection_name=self.collection,
            vector_size=3,
        )

        mock_client = AsyncMock()
        adapter._client = mock_client

        await adapter.set_has_invalid_tasks(extraction_id="ext-123", has_invalid_tasks=False)

        call_kwargs = mock_client.set_payload.call_args[1]
        assert call_kwargs["payload"] == {"has_invalid_tasks": False}

    @pytest.mark.asyncio
    async def test_set_has_invalid_tasks_missing_point_is_a_noop(self) -> None:
        """A point that was never stored is nothing to flag — not an error.

        The adapter issues the call unconditionally, with no pre-read to check
        existence: Qdrant's ``set_payload`` over zero matched points changes
        nothing and returns normally, and that is the documented no-op — nothing
        was ever stored, so nothing can be retrieved, so there is nothing for a
        future search to be contaminated by. The adapter must neither raise nor
        retry on that quiet result (that a real Qdrant behaves this way is 3.9's
        live proof).
        """
        port = _make_embedding_port(dimensions=3)
        adapter = QdrantAdapter(
            embedding_port=port,
            qdrant_url=self.qdrant_url,
            collection_name=self.collection,
            vector_size=3,
        )

        mock_client = AsyncMock()
        mock_client.set_payload.return_value = SimpleNamespace(status="completed")
        adapter._client = mock_client

        await adapter.set_has_invalid_tasks(extraction_id="ext-ghost", has_invalid_tasks=True)

        # One quiet call, no raise, no retry.
        mock_client.set_payload.assert_called_once()

    @pytest.mark.asyncio
    async def test_set_has_invalid_tasks_driver_failure_raises_vector_store_error(self) -> None:
        """A driver failure raises VectorStoreError, not a swallow.

        Unlike ``search_similar``/``store_extraction``, this method does not
        degrade gracefully: its caller is a destructive-adjacent operation (the
        mark handlers' refresh, which runs before the relational write) that
        must not proceed — and must not persist the mark — on an unverified
        result. Asserting the exact type also proves the raw driver error does
        not escape unwrapped.
        """
        port = _make_embedding_port(dimensions=3)
        adapter = QdrantAdapter(
            embedding_port=port,
            qdrant_url=self.qdrant_url,
            collection_name=self.collection,
            vector_size=3,
        )

        mock_client = AsyncMock()
        mock_client.set_payload.side_effect = RuntimeError("Qdrant down")
        adapter._client = mock_client

        with pytest.raises(VectorStoreError, match="Qdrant down"):
            await adapter.set_has_invalid_tasks(extraction_id="ext-1", has_invalid_tasks=True)

    @pytest.mark.asyncio
    async def test_set_has_invalid_tasks_client_unavailable_raises(self) -> None:
        """An unavailable client raises instead of returning quietly.

        Same distinction as ``delete_by_story``: "no vector store configured"
        (part (iii)'s handlers skip the refresh entirely) is different from "a
        configured store that cannot be reached", which raises — the mark must
        not be persisted while the vector half of the operation is unverified.
        """
        port = _make_embedding_port(dimensions=3)
        adapter = QdrantAdapter(
            embedding_port=port,
            qdrant_url=self.qdrant_url,
            collection_name=self.collection,
            vector_size=3,
        )
        # Force a fresh lazy init so the client is actually built (and fails) below.
        adapter._client = None

        with patch(
            "storico.infrastructure.vector.qdrant_adapter.AsyncQdrantClient",
            side_effect=RuntimeError("connection refused"),
        ):
            with pytest.raises(VectorStoreError, match="unavailable"):
                await adapter.set_has_invalid_tasks(extraction_id="ext-1", has_invalid_tasks=True)
