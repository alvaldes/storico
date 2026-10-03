"""Live integration test for the Qdrant + few-shot retrieval path.

This is the runtime evidence the archived ``few-shot-qdrant`` verify report
listed as outstanding: *"runtime-only checks still to confirm: live embedding
calls and a real workspace-scoped retrieval + end-to-end extraction — mocked
SDKs only."* Every other automated proof of this feature mocks the vector store
or the embedding SDK, so a green run there is compatible with Qdrant being
unreachable and the embedding model being absent. This module talks to a
**real Ollama** for embeddings and a **real Qdrant** for storage/retrieval; only
the LLM is doubled, by ``RecordingLLM``, so the rendered prompt can be asserted
without a model call.

Gate
----
The tests are opt-in and never probe reachability:

    cd backend && STORICO_TEST_LIVE_QDRANT=1 python -m pytest \\
        tests/test_integration/test_few_shot_rag_qdrant.py -v

Without ``STORICO_TEST_LIVE_QDRANT=1`` every test skips. Once an operator sets
the flag, an unreachable Ollama or Qdrant **fails** the run — the adapter's
graceful degradation turns those into empty results and ``False``, and the
assertions catch it. There is deliberately no try/except-skip here: a skip on
an opted-in run would prove nothing.

Isolation
---------
Each test builds its own throwaway collection
(``storico_extractions_pytest_<hex>``), deleted in teardown, and its own random
``workspace_id``. The application's real collection is never touched. All
connection values, the collection vector size, and the embedding provider come
from ``Settings.load()`` / ``get_embedding_port(settings)``; the only hardcoded
URL is the deliberately dead one in the degradation tests.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from datetime import UTC, datetime

import pytest
import pytest_asyncio
from qdrant_client import AsyncQdrantClient
from qdrant_client.http import models as qdrant_models

from storico.config.settings import Settings
from storico.domain.ports import (
    EmbeddingPort,
    LLMConfig,
    LLMPort,
    ParsedTask,
    VectorStorePort,
)
from storico.domain.ports.llm_port import LLMResponse
from storico.domain.services.extraction_service import ExtractionService, FewShotConfig
from storico.infrastructure.llm.prompt_manager import PromptManager
from storico.infrastructure.llm.task_parser import TaskParser
from storico.infrastructure.vector import QdrantAdapter, get_embedding_port
from tests._helpers import simple_context

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.environ.get("STORICO_TEST_LIVE_QDRANT") != "1",
        reason=(
            "Live Qdrant/Ollama integration is opt-in: set STORICO_TEST_LIVE_QDRANT=1 to run it. "
            "With the flag set, unreachable services fail the run instead of skipping."
        ),
    ),
]

EXPECTED_DIMENSIONS = 768
DEAD_QDRANT_URL = "http://127.0.0.1:6333"
COLLECTION_PREFIX = "storico_extractions_pytest_"

STORY_QUERY = (
    "As a registered user, I want to log in with my email and password "
    "so that I can access my account dashboard."
)
# Near-duplicate of STORY_QUERY (measured cosine similarity 0.9668 against the
# live nomic-embed-text embedding), so a threshold above 0.9 must still find it.
STORY_SIMILAR = (
    "As a registered user, I want to sign in with my email and password "
    "so that I can reach my account dashboard."
)
STORY_VARIANTS = (
    STORY_SIMILAR,
    "As a registered user, I want to log in using my email and password "
    "so that I can open my account dashboard.",
    "As a registered user, I want to authenticate with my email and password "
    "so that I can see my account dashboard.",
)
STORY_UNRELATED = (
    "As an inventory manager, I want to export monthly warehouse stock reports "
    "as CSV so that I can reconcile physical counts."
)
TASKS_SUMMARY = "1. Implement the credential form: add email and password inputs with validation."
LLM_RESPONSE = "1. summary: Probe task\ndescription: Probe description."


@dataclass(frozen=True, slots=True)
class Story:
    """Minimal user-story stand-in — ``extract`` reads ``raw_text`` and ``id``."""

    raw_text: str
    id: str = ""


@dataclass(frozen=True, slots=True)
class LiveVectorStore:
    """The live adapter under test plus a separate client for inspection/cleanup."""

    adapter: QdrantAdapter
    inspector: AsyncQdrantClient
    collection_name: str


class RecordingLLM(LLMPort):
    """LLM double that records the rendered prompt instead of calling a model."""

    def __init__(self) -> None:
        self.prompts: list[str] = []

    async def generate(
        self,
        prompt: str,
        config: LLMConfig,
        system_prompt: str | None = None,
        **kwargs: object,
    ) -> LLMResponse:
        """Record the prompt and return a response ``TaskParser`` can parse."""
        self.prompts.append(prompt)
        return LLMResponse(text=LLM_RESPONSE)


# loop_scope="module" keeps every async fixture and test on one event loop, for
# the same reason the sibling test_projects_integration.py does: pytest-asyncio
# otherwise gives each test a fresh loop, and the Ollama embedding adapter's
# ``httpx.AsyncClient`` — created once when the port is built and pooled across
# calls — then reuses a connection from a closed loop and fails the next call
# with ``Event loop is closed``. That is a harness artifact (production runs the
# port and its client in a single process loop), not a defect in the code under
# test, so the fix is the loop scope, not the assertion.
@pytest.fixture(scope="module")
def settings() -> Settings:
    """The real application settings (environment + ``.env``), never hardcoded."""
    return Settings.load()


@pytest.fixture(scope="module")
def embedding_port(settings: Settings) -> EmbeddingPort:
    """The real embedding provider configured for this environment."""
    return get_embedding_port(settings)


async def _close_adapter_client(adapter: QdrantAdapter) -> None:
    """Close the client the adapter lazily opened, if it ever did.

    ``QdrantAdapter`` exposes no ``close()``; the live client holds a real
    connection pool, so a per-test fixture must release it explicitly.
    """
    client = adapter._client
    if client is not None:
        await client.close()


@pytest_asyncio.fixture(loop_scope="module")
async def live_store(
    settings: Settings, embedding_port: EmbeddingPort
) -> AsyncGenerator[LiveVectorStore, None]:
    """Wire the adapter to a throwaway collection and delete it on teardown.

    The ad-hoc ``inspector`` client is what the teardown and the collection
    contract test use, so deleting the collection never depends on the adapter
    under test having connected successfully.
    """
    collection_name = f"{COLLECTION_PREFIX}{uuid.uuid4().hex[:12]}"
    adapter = QdrantAdapter(
        embedding_port=embedding_port,
        qdrant_url=settings.qdrant_url,
        qdrant_api_key=settings.qdrant_api_key,
        collection_name=collection_name,
        vector_size=settings.embedding_dimensions,
    )
    inspector = AsyncQdrantClient(
        url=settings.qdrant_url, api_key=settings.qdrant_api_key, timeout=10
    )
    try:
        yield LiveVectorStore(adapter=adapter, inspector=inspector, collection_name=collection_name)
    finally:
        # Idempotent on the server: deleting a missing collection is not an error,
        # so a test that failed before storing still tears down cleanly.
        await inspector.delete_collection(collection_name=collection_name)
        await inspector.close()
        await _close_adapter_client(adapter)


async def _store_live(
    adapter: QdrantAdapter,
    *,
    workspace_id: uuid.UUID,
    user_story_text: str,
    tasks_summary: str = TASKS_SUMMARY,
    user_story_id: str = "",
) -> str:
    """Store one live point and assert the server accepted it.

    The point id is a real ``uuid4``: Qdrant accepts only an unsigned integer or
    a UUID, and the ``"<uuid>:<index>"`` shape was an actual defect that every
    mocked test stayed green against. ``project_id`` and ``version_number``
    carry fresh values per point — they are required keywords of the port, and
    the filter semantics under test here do not depend on them. Returns the
    point id, which is the extraction id ``set_has_invalid_tasks`` addresses.
    """
    point_id = str(uuid.uuid4())
    stored = await adapter.store_extraction(
        extraction_id=point_id,
        user_story_text=user_story_text,
        tasks_summary=tasks_summary,
        model_used="pytest-live",
        workspace_id=workspace_id,
        project_id=uuid.uuid4(),
        version_number=1,
        user_story_id=user_story_id,
        confidence_score=0.9,
    )
    assert stored is True, "the live vector store rejected the point"
    return point_id


async def _store_point_without_validity_flag(
    live_store: LiveVectorStore,
    embedding_port: EmbeddingPort,
    *,
    workspace_id: uuid.UUID,
    user_story_text: str,
) -> str:
    """Upsert a pre-slice point whose payload has no ``has_invalid_tasks`` key.

    The production write path can no longer produce such a point — it always
    writes the flag ``False`` — so the fail-closed case writes the legacy shape
    directly through the inspector client: the seven payload keys a point
    carried before this slice existed, and no validity flag. This is the exact
    shape a point written before the slice would still have in the collection,
    and the shape a ``must_not``-on-``True`` validity rule would wrongly admit.
    Returns the point id.
    """
    point_id = str(uuid.uuid4())
    embedding = await embedding_port.embed(user_story_text)
    assert embedding, "the live embedding provider returned no vector for the legacy point"
    await live_store.inspector.upsert(
        collection_name=live_store.collection_name,
        points=[
            qdrant_models.PointStruct(
                id=point_id,
                vector=embedding,
                payload={
                    "user_story_text": user_story_text,
                    "tasks_summary": TASKS_SUMMARY,
                    "model_used": "pytest-live-legacy",
                    "workspace_id": str(workspace_id),
                    "confidence_score": 0.9,
                    "user_story_id": "",
                    "created_at": datetime.now(UTC).isoformat(),
                },
            )
        ],
        wait=True,
    )
    return point_id


def _build_service(llm: RecordingLLM, vector_store: VectorStorePort) -> ExtractionService:
    """Build the real service with a recording LLM and no persistence.

    The service renders prompts and calls the provider only — it holds no
    repositories at all, so there is nothing to pass or stub out.
    """
    return ExtractionService(
        llm_port=llm,
        prompt_manager=PromptManager(),
        task_parser=TaskParser(),
        vector_store=vector_store,
    )


async def _scroll_all(live_store: LiveVectorStore) -> list[qdrant_models.Record]:
    """Every point in the throwaway collection, via a payload-bearing scroll.

    ``limit=100`` is far above what any single test stores, and the return shape
    is a ``(records, next_page_offset)`` tuple, so an empty collection scrolls
    to an empty list rather than raising.
    """
    records, _next_page_offset = await live_store.inspector.scroll(
        collection_name=live_store.collection_name, limit=100, with_payload=True
    )
    return list(records)


async def _extract(
    vector_store: VectorStorePort,
    *,
    story_text: str,
    workspace_id: uuid.UUID,
    few_shot_config: FewShotConfig,
) -> tuple[list[ParsedTask], str]:
    """Run the real prompt pipeline and return the parsed tasks and the prompt.

    The story carries a fresh id that matches no stored point: these cases pin
    workspace scoping, thresholds and the limit, not the self-exclusion, so the
    ``exclude_story_id`` rule must not remove any fixture point from play. (A
    story with no id would fail closed and skip retrieval entirely.)
    """
    llm = RecordingLLM()
    service = _build_service(llm, vector_store)
    rendered = await service.render(
        Story(raw_text=story_text, id=str(uuid.uuid4())),
        workspace_id=workspace_id,
        few_shot_config=few_shot_config,
        context=simple_context(),
    )
    result = await service.generate(rendered, LLMConfig(model="pytest-recording"))
    assert len(llm.prompts) == 1, "render must hand the provider exactly one prompt"
    return result.tasks, llm.prompts[0]


def _dead_adapter(settings: Settings, embedding_port: EmbeddingPort) -> QdrantAdapter:
    """An adapter pointed at a URL nothing listens on.

    Only the URL deviates from the real configuration. The collection name
    keeps the pytest prefix so that a stray listener on that port still could
    not reach the application's collection.
    """
    return QdrantAdapter(
        embedding_port=embedding_port,
        qdrant_url=DEAD_QDRANT_URL,
        qdrant_api_key=settings.qdrant_api_key,
        collection_name=f"{COLLECTION_PREFIX}{uuid.uuid4().hex[:12]}",
        vector_size=settings.embedding_dimensions,
    )


class TestLiveEmbeddings:
    """The live embedding provider really returns the configured dimensions."""

    @pytest.mark.asyncio(loop_scope="module")
    async def test_live_embedding_is_non_empty_and_768_dims(
        self, settings: Settings, embedding_port: EmbeddingPort
    ) -> None:
        """A real embedding call returns a non-empty 768-length vector."""
        embedding = await embedding_port.embed(STORY_QUERY)

        # 768 is both "non-empty" and "exactly the configured size": an empty
        # vector (model absent / provider unreachable) fails here.
        assert len(embedding) == EXPECTED_DIMENSIONS, (
            f"live embedding returned {len(embedding)} dims, expected {EXPECTED_DIMENSIONS} — "
            "an empty vector means the configured embedding model could not be served"
        )
        assert settings.embedding_dimensions == EXPECTED_DIMENSIONS
        assert embedding_port.dimensions == EXPECTED_DIMENSIONS


class TestLiveCollectionContract:
    """The collection the adapter creates matches the size/distance/payload contract."""

    @pytest.mark.asyncio(loop_scope="module")
    async def test_live_collection_has_unnamed_cosine_vector_and_workspace_index(
        self, live_store: LiveVectorStore
    ) -> None:
        """After one live store: unnamed 768d cosine vector plus workspace_id index."""
        await _store_live(
            live_store.adapter, workspace_id=uuid.uuid4(), user_story_text=STORY_QUERY
        )

        info = await live_store.inspector.get_collection(live_store.collection_name)
        vectors = info.config.params.vectors
        assert isinstance(vectors, qdrant_models.VectorParams), (
            f"expected a single unnamed vector config, got {vectors!r}"
        )
        assert vectors.size == EXPECTED_DIMENSIONS
        assert vectors.distance == qdrant_models.Distance.COSINE
        assert "workspace_id" in info.payload_schema

    @pytest.mark.asyncio(loop_scope="module")
    async def test_live_collection_payload_schema_carries_all_three_indexes(
        self, live_store: LiveVectorStore
    ) -> None:
        """After one live store: KEYWORD on both id fields, BOOL on the flag."""
        await _store_live(
            live_store.adapter, workspace_id=uuid.uuid4(), user_story_text=STORY_QUERY
        )

        info = await live_store.inspector.get_collection(live_store.collection_name)
        assert {"workspace_id", "project_id", "has_invalid_tasks"} <= set(info.payload_schema), (
            f"the collection's payload_schema is missing a filtered-field index: "
            f"{sorted(info.payload_schema)}"
        )
        assert (
            info.payload_schema["workspace_id"].data_type == qdrant_models.PayloadSchemaType.KEYWORD
        )
        assert (
            info.payload_schema["project_id"].data_type == qdrant_models.PayloadSchemaType.KEYWORD
        )
        assert (
            info.payload_schema["has_invalid_tasks"].data_type
            == qdrant_models.PayloadSchemaType.BOOL
        )


class TestLiveRetrieval:
    """Workspace-scoped retrieval against the real server."""

    @pytest.mark.asyncio(loop_scope="module")
    async def test_similar_story_in_same_workspace_returns_one_high_score_hit(
        self, live_store: LiveVectorStore
    ) -> None:
        """A similar story retrieves the stored point with score above 0.9."""
        workspace_id = uuid.uuid4()
        await _store_live(
            live_store.adapter, workspace_id=workspace_id, user_story_text=STORY_QUERY
        )

        hits = await live_store.adapter.search_similar(
            STORY_SIMILAR,
            limit=3,
            threshold=0.85,
            workspace_id=workspace_id,
            exclude_story_id=str(uuid.uuid4()),
        )

        assert len(hits) == 1
        assert hits[0].user_story_text == STORY_QUERY
        assert hits[0].similarity_score > 0.9, (
            f"similar story scored {hits[0].similarity_score:.4f}, expected > 0.9"
        )

    @pytest.mark.asyncio(loop_scope="module")
    async def test_same_story_from_another_workspace_is_isolated(
        self, live_store: LiveVectorStore
    ) -> None:
        """The identical query is reachable from its workspace and invisible from another."""
        workspace_a = uuid.uuid4()
        workspace_b = uuid.uuid4()
        await _store_live(live_store.adapter, workspace_id=workspace_a, user_story_text=STORY_QUERY)

        in_a = await live_store.adapter.search_similar(
            STORY_QUERY,
            limit=3,
            threshold=0.85,
            workspace_id=workspace_a,
            exclude_story_id=str(uuid.uuid4()),
        )
        assert len(in_a) == 1, "the point must be reachable from its own workspace"

        in_b = await live_store.adapter.search_similar(
            STORY_QUERY,
            limit=3,
            threshold=0.85,
            workspace_id=workspace_b,
            exclude_story_id=str(uuid.uuid4()),
        )
        assert in_b == [], "a workspace must never see another workspace's stored story"


class TestLiveValidityAndExclusionFilter:
    """The fail-closed retrieval rules, proved against a real Qdrant index.

    A fake client can assert the filter's *shape*; only a real server proves the
    *semantics*: that a positive ``must`` on ``has_invalid_tasks == False``
    actually excludes a flagged point, that a payload missing the key entirely
    is never read as valid (fail-closed), that the ``must_not`` on
    ``user_story_id`` keeps a story out of its own few-shot examples, and that
    an excluded point does not consume ``limit``.
    """

    @pytest.mark.asyncio(loop_scope="module")
    async def test_own_story_previous_point_is_not_returned(
        self, live_store: LiveVectorStore
    ) -> None:
        """The story's own previous point is invisible to its re-extraction."""
        workspace_id = uuid.uuid4()
        story_id = str(uuid.uuid4())
        await _store_live(
            live_store.adapter,
            workspace_id=workspace_id,
            user_story_text=STORY_QUERY,
            user_story_id=story_id,
        )

        own = await live_store.adapter.search_similar(
            STORY_SIMILAR,
            limit=3,
            threshold=0.85,
            workspace_id=workspace_id,
            exclude_story_id=story_id,
        )
        assert own == [], "a story must never be retrieved as its own few-shot example"

        # Control: the identical point IS reachable when the exclusion names a
        # different story — the miss above was the must_not, not the index.
        other = await live_store.adapter.search_similar(
            STORY_SIMILAR,
            limit=3,
            threshold=0.85,
            workspace_id=workspace_id,
            exclude_story_id=str(uuid.uuid4()),
        )
        assert len(other) == 1
        assert other[0].user_story_text == STORY_QUERY

    @pytest.mark.asyncio(loop_scope="module")
    async def test_marked_extraction_is_not_returned(self, live_store: LiveVectorStore) -> None:
        """A point flagged by the setter is excluded; the revoke restores it."""
        workspace_id = uuid.uuid4()
        point_id = await _store_live(
            live_store.adapter, workspace_id=workspace_id, user_story_text=STORY_QUERY
        )

        await live_store.adapter.set_has_invalid_tasks(
            extraction_id=point_id, has_invalid_tasks=True
        )
        marked = await live_store.adapter.search_similar(
            STORY_SIMILAR,
            limit=3,
            threshold=0.85,
            workspace_id=workspace_id,
            exclude_story_id=str(uuid.uuid4()),
        )
        assert marked == [], "a point carrying an active mark must never be retrieved"

        await live_store.adapter.set_has_invalid_tasks(
            extraction_id=point_id, has_invalid_tasks=False
        )
        revoked = await live_store.adapter.search_similar(
            STORY_SIMILAR,
            limit=3,
            threshold=0.85,
            workspace_id=workspace_id,
            exclude_story_id=str(uuid.uuid4()),
        )
        assert len(revoked) == 1
        assert revoked[0].user_story_text == STORY_QUERY

    @pytest.mark.asyncio(loop_scope="module")
    async def test_limit_one_with_two_contaminated_points_returns_the_valid_one(
        self, live_store: LiveVectorStore
    ) -> None:
        """With limit=1 and both excluded points above the threshold, the valid
        point is the one returned — an exclusion happens before the limit, so a
        contaminated point never consumes it."""
        workspace_id = uuid.uuid4()
        story_id = str(uuid.uuid4())
        valid_text = STORY_VARIANTS[0]
        # Contaminated point 1: the story's own previous point (must_not).
        await _store_live(
            live_store.adapter,
            workspace_id=workspace_id,
            user_story_text=STORY_QUERY,
            user_story_id=story_id,
        )
        # Contaminated point 2: an active mark (must has_invalid_tasks == False).
        flagged_id = await _store_live(
            live_store.adapter, workspace_id=workspace_id, user_story_text=STORY_SIMILAR
        )
        await live_store.adapter.set_has_invalid_tasks(
            extraction_id=flagged_id, has_invalid_tasks=True
        )
        await _store_live(live_store.adapter, workspace_id=workspace_id, user_story_text=valid_text)

        hits = await live_store.adapter.search_similar(
            STORY_QUERY,
            limit=1,
            threshold=0.85,
            workspace_id=workspace_id,
            exclude_story_id=story_id,
        )

        assert len(hits) == 1, "neither excluded point may consume the limit"
        assert hits[0].user_story_text == valid_text

    @pytest.mark.asyncio(loop_scope="module")
    async def test_point_without_validity_flag_is_excluded_while_a_valid_point_is_returned(
        self, live_store: LiveVectorStore, embedding_port: EmbeddingPort
    ) -> None:
        """Fail-closed: a payload with no ``has_invalid_tasks`` key is not valid.

        This is the proof a fake client cannot give: against a mocked SDK the
        filter's shape is all there is, but here a point whose payload simply
        lacks the key — the shape every pre-slice point still has — is written
        into a real index and must not be read as valid.
        """
        workspace_id = uuid.uuid4()
        # The valid point is stored first: the adapter's lazy init creates the
        # collection (and its indexes), which the direct legacy upsert below
        # then targets — the inspector client never creates collections.
        valid_text = STORY_VARIANTS[0]
        await _store_live(live_store.adapter, workspace_id=workspace_id, user_story_text=valid_text)
        legacy_id = await _store_point_without_validity_flag(
            live_store,
            embedding_port,
            workspace_id=workspace_id,
            user_story_text=STORY_QUERY,
        )

        # Precondition: the legacy point really is in the collection, and its
        # payload really lacks the key — otherwise the outcome proves nothing.
        points = await _scroll_all(live_store)
        assert len(points) == 2, f"expected the legacy point and the valid one, got {len(points)}"
        legacy_payload = next(p.payload for p in points if str(p.id) == legacy_id)
        assert legacy_payload is not None
        assert "has_invalid_tasks" not in legacy_payload

        hits = await live_store.adapter.search_similar(
            STORY_QUERY,
            limit=3,
            threshold=0.85,
            workspace_id=workspace_id,
            exclude_story_id=str(uuid.uuid4()),
        )
        assert len(hits) == 1, "a point without the validity flag must fail closed"
        assert hits[0].user_story_text == valid_text

    @pytest.mark.asyncio(loop_scope="module")
    async def test_delete_by_story_removes_a_flagged_point_and_refresh_then_is_a_noop(
        self, live_store: LiveVectorStore
    ) -> None:
        """Cross-slice coexistence: (b)'s cleanup removes a flagged point that
        carries the new payload keys, and the point-id refresh on the deleted
        point is a no-op, not an error and not a resurrection.
        """
        workspace_id = uuid.uuid4()
        story_id = str(uuid.uuid4())
        point_id = await _store_live(
            live_store.adapter,
            workspace_id=workspace_id,
            user_story_text=STORY_QUERY,
            user_story_id=story_id,
        )
        await live_store.adapter.set_has_invalid_tasks(
            extraction_id=point_id, has_invalid_tasks=True
        )

        points = await _scroll_all(live_store)
        assert len(points) == 1
        assert points[0].payload is not None
        assert points[0].payload["has_invalid_tasks"] is True, (
            "precondition: the point carries an active mark"
        )
        assert points[0].payload["project_id"], "precondition: the payload carries the new keys"
        assert "version_number" in points[0].payload

        # (b)'s destructive cleanup must remove the point regardless of the flag.
        await live_store.adapter.delete_by_story(workspace_id=workspace_id, user_story_id=story_id)
        assert await _scroll_all(live_store) == []

        # ...and the refresh on the now-deleted point is a no-op, not an error.
        await live_store.adapter.set_has_invalid_tasks(
            extraction_id=point_id, has_invalid_tasks=True
        )
        assert await _scroll_all(live_store) == [], "a refresh cannot resurrect a deleted point"

    @pytest.mark.asyncio(loop_scope="module")
    async def test_unrelated_story_below_threshold_returns_nothing(
        self, live_store: LiveVectorStore
    ) -> None:
        """An unrelated story scores below 0.85 and yields no hit."""
        workspace_id = uuid.uuid4()
        await _store_live(
            live_store.adapter, workspace_id=workspace_id, user_story_text=STORY_QUERY
        )

        hits = await live_store.adapter.search_similar(
            STORY_UNRELATED,
            limit=3,
            threshold=0.85,
            workspace_id=workspace_id,
            exclude_story_id=str(uuid.uuid4()),
        )

        assert hits == []

    @pytest.mark.asyncio(loop_scope="module")
    async def test_limit_caps_the_returned_points(self, live_store: LiveVectorStore) -> None:
        """Three stored points with limit=2 return exactly two."""
        workspace_id = uuid.uuid4()
        for story in STORY_VARIANTS:
            await _store_live(live_store.adapter, workspace_id=workspace_id, user_story_text=story)

        hits = await live_store.adapter.search_similar(
            STORY_QUERY,
            limit=2,
            threshold=0.5,
            workspace_id=workspace_id,
            exclude_story_id=str(uuid.uuid4()),
        )

        assert len(hits) == 2


class TestLiveStoredPoint:
    """The production write path against a real server — the last mocked-only check.

    These tests were born as ``TestLiveSeedJob``: ``run_seed`` used to write
    ``"{workspace_id}:{index}"`` point ids that a live Qdrant rejects outright,
    while still counting them as seeded, and every proof of the fix mocked
    ``VectorStorePort``, so a green run there was compatible with the server
    rejecting every point. The legacy ``few_shot_examples`` column and the seed
    job that read it are gone now, so the same live-server guarantees are
    exercised through ``VectorStorePort.store_extraction`` — the write path
    production actually uses: a valid UUID point id the server accepts, the
    workspace id in the payload, retrieval from the owning workspace, and an
    idempotent rewrite of the same point id.

    Scope note: the assertions run against the live server's own state (scroll +
    search), not against the adapter's return value alone.
    """

    @pytest.mark.asyncio(loop_scope="module")
    async def test_stored_point_has_valid_id_workspace_payload_and_is_retrievable(
        self, live_store: LiveVectorStore
    ) -> None:
        """One stored point lands with a server-acceptable UUID id and is retrievable."""
        workspace_id = uuid.uuid4()
        stored = await live_store.adapter.store_extraction(
            extraction_id=str(uuid.uuid4()),
            user_story_text=STORY_QUERY,
            tasks_summary=TASKS_SUMMARY,
            model_used="pytest-live",
            workspace_id=workspace_id,
            project_id=uuid.uuid4(),
            version_number=1,
        )
        assert stored is True, "the live store rejected the point"

        points = await _scroll_all(live_store)
        assert len(points) == 1, f"expected exactly one stored point, got {len(points)}"
        point = points[0]
        # Validity, not the derivation formula: the historic defect was a point id
        # Qdrant refused, and re-computing a formula here would pass against that
        # refusal.
        uuid.UUID(str(point.id))
        assert point.payload is not None
        assert point.payload["workspace_id"] == str(workspace_id)

        hits = await live_store.adapter.search_similar(
            STORY_QUERY,
            limit=3,
            threshold=0.5,
            workspace_id=workspace_id,
            exclude_story_id=str(uuid.uuid4()),
        )
        assert len(hits) == 1, "the stored point must be retrievable from its own workspace"
        assert hits[0].user_story_text == STORY_QUERY

    @pytest.mark.asyncio(loop_scope="module")
    async def test_rerun_with_the_same_point_id_overwrites_not_duplicates(
        self, live_store: LiveVectorStore
    ) -> None:
        """Re-storing the same extraction id overwrites the point instead of duplicating.

        This preserves the idempotence coverage the seed-job rerun test carried:
        a point id that already exists is overwritten by the server, never
        duplicated.
        """
        workspace_id = uuid.uuid4()
        point_id = str(uuid.uuid4())
        for _ in range(2):
            stored = await live_store.adapter.store_extraction(
                extraction_id=point_id,
                user_story_text=STORY_QUERY,
                tasks_summary=TASKS_SUMMARY,
                model_used="pytest-live",
                workspace_id=workspace_id,
                project_id=uuid.uuid4(),
                version_number=1,
            )
            assert stored is True, "the live store rejected the point"

        points = await _scroll_all(live_store)
        assert len(points) == 1, (
            f"a rewrite must overwrite, not duplicate; the collection holds {len(points)} points"
        )
        assert points[0].payload is not None
        assert points[0].payload["workspace_id"] == str(workspace_id)
        assert str(points[0].id) == point_id


class TestLivePromptRendering:
    """The rendered prompt carries the examples section exactly when configured."""

    @pytest.mark.asyncio(loop_scope="module")
    async def test_warm_retrieval_renders_exactly_one_example(
        self, live_store: LiveVectorStore
    ) -> None:
        """One stored similar example renders the section with that one example."""
        workspace_id = uuid.uuid4()
        await _store_live(
            live_store.adapter, workspace_id=workspace_id, user_story_text=STORY_QUERY
        )

        tasks, prompt = await _extract(
            live_store.adapter,
            story_text=STORY_SIMILAR,
            workspace_id=workspace_id,
            few_shot_config=FewShotConfig(enabled=True, limit=3, threshold=0.5),
        )

        assert len(tasks) == 1
        assert "## Few-Shot Examples" in prompt
        assert STORY_QUERY in prompt
        assert prompt.count("Example ") == 1

    @pytest.mark.asyncio(loop_scope="module")
    async def test_cold_start_omits_the_examples_section(self, live_store: LiveVectorStore) -> None:
        """A workspace with no stored points renders no examples section."""
        workspace_id = uuid.uuid4()

        tasks, prompt = await _extract(
            live_store.adapter,
            story_text=STORY_QUERY,
            workspace_id=workspace_id,
            few_shot_config=FewShotConfig(enabled=True, limit=3, threshold=0.5),
        )

        assert len(tasks) == 1
        assert "## Few-Shot Examples" not in prompt
        assert STORY_QUERY in prompt

    @pytest.mark.asyncio(loop_scope="module")
    async def test_disabled_retrieval_omits_the_section_despite_a_stored_hit(
        self, live_store: LiveVectorStore
    ) -> None:
        """enabled=False drops the section even when the workspace has a scoring hit."""
        workspace_id = uuid.uuid4()
        await _store_live(
            live_store.adapter, workspace_id=workspace_id, user_story_text=STORY_QUERY
        )

        _warm_tasks, warm_prompt = await _extract(
            live_store.adapter,
            story_text=STORY_SIMILAR,
            workspace_id=workspace_id,
            few_shot_config=FewShotConfig(enabled=True, limit=3, threshold=0.5),
        )
        assert "## Few-Shot Examples" in warm_prompt, (
            "precondition: the stored point must be a hit for this test to mean anything"
        )

        _cold_tasks, disabled_prompt = await _extract(
            live_store.adapter,
            story_text=STORY_SIMILAR,
            workspace_id=workspace_id,
            few_shot_config=FewShotConfig(enabled=False, limit=3, threshold=0.5),
        )

        assert "## Few-Shot Examples" not in disabled_prompt

    @pytest.mark.asyncio(loop_scope="module")
    async def test_high_threshold_against_an_unrelated_story_omits_the_section(
        self, live_store: LiveVectorStore
    ) -> None:
        """threshold=0.99 on an unrelated story yields no section."""
        workspace_id = uuid.uuid4()
        await _store_live(
            live_store.adapter, workspace_id=workspace_id, user_story_text=STORY_QUERY
        )

        tasks, prompt = await _extract(
            live_store.adapter,
            story_text=STORY_UNRELATED,
            workspace_id=workspace_id,
            few_shot_config=FewShotConfig(enabled=True, limit=3, threshold=0.99),
        )

        assert len(tasks) == 1
        assert "## Few-Shot Examples" not in prompt
        assert STORY_UNRELATED in prompt

    @pytest.mark.asyncio(loop_scope="module")
    async def test_limit_two_renders_exactly_two_examples(
        self, live_store: LiveVectorStore
    ) -> None:
        """Three stored points with limit=2 render exactly two examples."""
        workspace_id = uuid.uuid4()
        for story in STORY_VARIANTS:
            await _store_live(live_store.adapter, workspace_id=workspace_id, user_story_text=story)

        tasks, prompt = await _extract(
            live_store.adapter,
            story_text=STORY_QUERY,
            workspace_id=workspace_id,
            few_shot_config=FewShotConfig(enabled=True, limit=2, threshold=0.5),
        )

        assert len(tasks) == 1
        assert prompt.count("Example ") == 2


class TestDegradation:
    """An unreachable vector store degrades; it never fails an extraction."""

    @pytest.mark.asyncio(loop_scope="module")
    async def test_search_similar_returns_empty_without_raising(
        self, settings: Settings, embedding_port: EmbeddingPort
    ) -> None:
        """A dead Qdrant yields an empty result, not an exception."""
        adapter = _dead_adapter(settings, embedding_port)

        hits = await adapter.search_similar(
            STORY_QUERY,
            limit=3,
            threshold=0.85,
            workspace_id=uuid.uuid4(),
            exclude_story_id=str(uuid.uuid4()),
        )

        assert hits == []

    @pytest.mark.asyncio(loop_scope="module")
    async def test_store_extraction_returns_false_without_raising(
        self, settings: Settings, embedding_port: EmbeddingPort
    ) -> None:
        """A dead Qdrant reports the point as not stored, not as an exception."""
        adapter = _dead_adapter(settings, embedding_port)

        stored = await adapter.store_extraction(
            extraction_id=str(uuid.uuid4()),
            user_story_text=STORY_QUERY,
            tasks_summary=TASKS_SUMMARY,
            model_used="pytest-degradation",
            workspace_id=uuid.uuid4(),
            project_id=uuid.uuid4(),
            version_number=1,
        )

        assert stored is False

    @pytest.mark.asyncio(loop_scope="module")
    async def test_extraction_survives_a_dead_vector_store(
        self, settings: Settings, embedding_port: EmbeddingPort
    ) -> None:
        """A full extraction through the dead adapter still parses one task."""
        vector_store: VectorStorePort = _dead_adapter(settings, embedding_port)

        tasks, prompt = await _extract(
            vector_store,
            story_text=STORY_QUERY,
            workspace_id=uuid.uuid4(),
            few_shot_config=FewShotConfig(enabled=True, limit=3, threshold=0.5),
        )

        assert len(tasks) == 1
        assert "## Few-Shot Examples" not in prompt
        assert STORY_QUERY in prompt
