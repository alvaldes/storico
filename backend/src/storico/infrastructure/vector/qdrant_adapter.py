"""QdrantAdapter — VectorStorePort implementation using Qdrant vector database."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from uuid import UUID

from qdrant_client import AsyncQdrantClient
from qdrant_client.http import models as qdrant_models

from storico.domain.entities.exceptions import VectorStoreError
from storico.domain.ports import EmbeddingPort, ExtractionExample, VectorStorePort

logger = logging.getLogger(__name__)


class QdrantAdapter(VectorStorePort):
    """VectorStorePort implementation backed by Qdrant.

    Features:
    - Lazy async client initialization (first use, not constructor)
    - Auto-creates collection on first use if missing, and ensures payload
      indexes on the three filtered fields (``workspace_id``, ``project_id``,
      ``has_invalid_tasks``) so filtered searches stay fast.
    - Workspace isolation: every search sends a ``workspace_id`` filter and
      every stored point carries ``workspace_id`` in its payload.
    - Graceful degradation: empty results on failure — except the destructive
      operations ``delete_by_story`` and ``set_has_invalid_tasks``, which raise
      ``VectorStoreError`` because their callers must not proceed on an
      unverified result.

    Collection schema (storico_extractions):
        - vector: ``vector_size``d float array
        - payload: user_story_text, tasks_summary, model_used,
                   confidence_score, created_at, user_story_id, workspace_id,
                   project_id, version_number, has_invalid_tasks
    """

    def __init__(
        self,
        embedding_port: EmbeddingPort,
        qdrant_url: str = "http://localhost:6333",
        qdrant_api_key: str | None = None,
        collection_name: str = "storico_extractions",
        vector_size: int = 768,
        distance: qdrant_models.Distance = qdrant_models.Distance.COSINE,
    ) -> None:
        self._embedding_port = embedding_port
        self._qdrant_url = qdrant_url
        self._qdrant_api_key = qdrant_api_key
        self._collection_name = collection_name
        self._vector_size = vector_size
        self._distance = distance
        self._client: AsyncQdrantClient | None = None
        self._indexes_ensured = False

    def _check_dimensions(self) -> None:
        """Fail fast when the embedding dimensions do not match the collection.

        Prevents silently storing vectors that cannot be searched against the
        configured collection vector size.
        """
        provider_dimensions = self._embedding_port.dimensions
        if provider_dimensions != self._vector_size:
            raise ValueError(
                "Embedding provider dimensions "
                f"({provider_dimensions}) do not match the Qdrant collection "
                f"vector size ({self._vector_size}). "
                "Configure STORICO_EMBEDDING_PROVIDER/DIMENSIONS consistently."
            )

    async def _get_client(self) -> AsyncQdrantClient | None:
        """Lazy init — creates client + ensures collection on first call.

        Returns None if connection fails (graceful degradation).
        """
        if self._client is not None:
            return self._client

        self._check_dimensions()

        try:
            self._client = AsyncQdrantClient(
                url=self._qdrant_url,
                api_key=self._qdrant_api_key,
                timeout=10,
            )
            # Check if collection exists, create if not
            collections = await self._client.get_collections()
            existing = {c.name for c in collections.collections}

            if self._collection_name not in existing:
                await self._client.create_collection(
                    collection_name=self._collection_name,
                    vectors_config=qdrant_models.VectorParams(
                        size=self._vector_size,
                        distance=self._distance,
                    ),
                )
                logger.info("Created Qdrant collection '%s'", self._collection_name)

            await self._ensure_payload_indexes(self._client)
            return self._client
        except Exception as e:
            logger.warning("Failed to initialize Qdrant client: %s", e)
            self._client = None
            return None

    async def _ensure_payload_indexes(self, client: AsyncQdrantClient) -> None:
        """Create the payload indexes on the three filtered fields, once.

        ``workspace_id`` and ``project_id`` are stored as strings (``KEYWORD``);
        ``has_invalid_tasks`` is a JSON boolean, given ``PayloadSchemaType.BOOL``
        — the schema the pinned ``qdrant_client`` accepts (verified against the
        installed client's ``PayloadSchemaType`` enum, so no literal ``KEYWORD``
        fallback was needed).

        Idempotent: after the first success the flag is set so repeated lazy
        inits do not re-issue the index requests. A failure is logged but is not
        fatal — searches still work, just without the index acceleration.
        """
        if self._indexes_ensured:
            return
        fields = (
            ("workspace_id", qdrant_models.PayloadSchemaType.KEYWORD),
            ("project_id", qdrant_models.PayloadSchemaType.KEYWORD),
            ("has_invalid_tasks", qdrant_models.PayloadSchemaType.BOOL),
        )
        try:
            for field_name, field_schema in fields:
                await client.create_payload_index(
                    collection_name=self._collection_name,
                    field_name=field_name,
                    field_schema=field_schema,
                    wait=True,
                )
            self._indexes_ensured = True
            logger.info(
                "Ensured payload indexes on %s for '%s'",
                [name for name, _ in fields],
                self._collection_name,
            )
        except Exception as e:
            logger.warning("Failed to ensure payload indexes: %s", e)

    def _build_workspace_filter(
        self, workspace_id: UUID, exclude_story_id: str
    ) -> qdrant_models.Filter:
        """Build the unified exclusion expression every search is issued with.

        Three conditions, all of them unconditional rules of retrieval:

        - ``must`` ``workspace_id`` — workspace isolation; legacy points without
          the payload key are excluded because the filter matches the value.
        - ``must`` ``has_invalid_tasks == False`` — the validity rule, expressed
          as a **positive ``must`` on ``False``, never a ``must_not`` on
          ``True``. ``must_not`` on ``True`` still admits a point with no
          ``has_invalid_tasks`` key at all, so a point written before this
          slice existed would sail through the validity rule and be retrieved
          as if it were valid. ``must`` on ``False`` is fail-closed: a legacy
          point without the key matches neither branch and is never retrieved.
        - ``must_not`` ``user_story_id`` — the story's own point, so a story is
          never retrieved as its own few-shot example.
        """
        return qdrant_models.Filter(
            must=[
                qdrant_models.FieldCondition(
                    key="workspace_id",
                    match=qdrant_models.MatchValue(value=str(workspace_id)),
                ),
                qdrant_models.FieldCondition(
                    key="has_invalid_tasks",
                    match=qdrant_models.MatchValue(value=False),
                ),
            ],
            must_not=[
                qdrant_models.FieldCondition(
                    key="user_story_id",
                    match=qdrant_models.MatchValue(value=str(exclude_story_id)),
                ),
            ],
        )

    async def search_similar(
        self,
        text: str,
        limit: int = 3,
        threshold: float = 0.85,
        *,
        workspace_id: UUID,
        exclude_story_id: str,
    ) -> list[ExtractionExample]:
        """Search for similar extractions by embedding the input text.

        The query always carries the unified exclusion expression — the
        ``workspace_id`` scope, the fail-closed ``has_invalid_tasks == False``
        validity condition, and the ``user_story_id`` ``must_not`` — so a search
        can never widen into a cross-workspace read, never return an
        invalid-marked extraction, and never return the story's own run. Graceful
        degradation: returns empty list on any failure.
        """
        # Generate embedding
        embedding = await self._embedding_port.embed(text)
        if not embedding:
            return []

        # Get Qdrant client (lazy init)
        client = await self._get_client()
        if client is None:
            return []

        # Search
        try:
            query_filter = self._build_workspace_filter(workspace_id, exclude_story_id)
            search_result = await client.query_points(
                collection_name=self._collection_name,
                query=embedding,
                limit=limit,
                score_threshold=threshold,
                query_filter=query_filter,
                with_payload=True,
            )
        except Exception as e:
            logger.warning("Qdrant search failed: %s", e)
            return []

        # Map results
        examples: list[ExtractionExample] = []
        for point in search_result.points:
            payload = point.payload or {}
            examples.append(
                ExtractionExample(
                    user_story_text=payload.get("user_story_text", ""),
                    tasks_summary=payload.get("tasks_summary", ""),
                    model_used=payload.get("model_used", ""),
                    confidence_score=payload.get("confidence_score"),
                    similarity_score=point.score if point.score is not None else 0.0,
                )
            )

        return examples

    async def store_extraction(
        self,
        *,
        extraction_id: str,
        user_story_text: str,
        tasks_summary: str,
        model_used: str,
        workspace_id: UUID,
        project_id: UUID,
        version_number: int,
        confidence_score: float | None = None,
        user_story_id: str = "",
    ) -> bool:
        """Store an extraction with its embedding for future RAG searches.

        ``workspace_id`` is written into the point payload so the point is
        discoverable by workspace-scoped searches, alongside ``project_id`` and
        ``version_number`` (the route-minted run number, D22). A point is born
        valid: ``has_invalid_tasks`` is written ``False`` here — a task cannot
        be marked before it exists, and the point is stored after its run's
        tasks — and only ``set_has_invalid_tasks`` flips it later.

        Returns ``True`` only when Qdrant accepted the point; every skip or
        failure path returns ``False`` (graceful degradation, never raises).
        Note the contrast with ``delete_by_story``, which raises on failure:
        same client, opposite error postures, both deliberate.
        Every skip or failure is logged at ERROR with a shared field shape
        (``extraction_id``, ``collection``, ``reason``) so a lost RAG point can be
        correlated with its cause from the log alone — an empty embedding once made
        the point vanish with nothing observable anywhere, because the embedding
        service degrades connection errors to ``[]``.
        """
        # Generate embedding
        embedding = await self._embedding_port.embed(user_story_text)
        if not embedding:
            # The embedding port degrades its own failures to ``[]``, so an empty
            # vector here usually means the embedding call failed, not that the
            # story was empty. Loud, structured, and still non-raising: the port's
            # graceful-degradation contract is deliberate.
            logger.error(
                "Empty embedding returned by the embedding port; RAG point not stored",
                extra={
                    "extraction_id": extraction_id,
                    "collection": self._collection_name,
                    "reason": "empty_embedding",
                },
            )
            return False

        # Get Qdrant client (lazy init)
        client = await self._get_client()
        if client is None:
            logger.error(
                "Qdrant client unavailable; RAG point not stored",
                extra={
                    "extraction_id": extraction_id,
                    "collection": self._collection_name,
                    "reason": "client_unavailable",
                },
            )
            return False

        # Upsert point
        try:
            await client.upsert(
                collection_name=self._collection_name,
                points=[
                    qdrant_models.PointStruct(
                        id=extraction_id,
                        vector=embedding,
                        payload={
                            "user_story_text": user_story_text,
                            "tasks_summary": tasks_summary,
                            "model_used": model_used,
                            "workspace_id": str(workspace_id),
                            "project_id": str(project_id),
                            "version_number": version_number,
                            "has_invalid_tasks": False,
                            "confidence_score": confidence_score,
                            "user_story_id": user_story_id,
                            "created_at": datetime.now(UTC).isoformat(),
                        },
                    )
                ],
            )
        except Exception as e:
            # ERROR, not the former warning: a lost point silently degraded future
            # few-shot prompts for this workspace, which is incident-shaped.
            logger.error(
                "Qdrant upsert failed; RAG point not stored: %s",
                e,
                extra={
                    "extraction_id": extraction_id,
                    "collection": self._collection_name,
                    "reason": "upsert_failed",
                },
            )
            return False

        return True

    async def delete_by_story(self, *, workspace_id: UUID, user_story_id: str) -> None:
        """Delete every point of one story in one workspace.

        Unlike ``store_extraction``/``search_similar`` — which degrade gracefully
        and never raise — this method raises ``VectorStoreError`` on failure: the
        caller is a destructive operation (story deletion) that must not proceed
        on an unverified cleanup. A lost upsert costs one future RAG example; a
        cleanup that was believed to happen but didn't leaves orphan points for a
        story that no longer exists, answering future similarity searches with
        content whose owner was deleted.

        "Client unavailable" here means ``_get_client()`` returned ``None`` —
        lazy init failed (e.g. the connection attempt to Qdrant raised, so no
        client object exists to issue the delete with). That is a *configured*
        store that cannot be reached, which raises; it is distinct from "no
        vector store configured at all", where the service skips this call
        entirely as a legitimate completion because no points exist to clean.

        The filter reuses the payload keys ``store_extraction`` already persists
        (``workspace_id`` as ``str(workspace_id)``, ``user_story_id`` as a
        string) so the match types are exactly the stored types — a mismatch
        would delete nothing and still look like success. ``wait=True`` makes
        "no points remain retrievable" true when the call returns.

        Raises:
            VectorStoreError: when the client is unavailable or the delete fails.
        """
        client = await self._get_client()
        if client is None:
            raise VectorStoreError(
                "Qdrant client unavailable; story point cleanup cannot be verified"
            )

        try:
            await client.delete(
                collection_name=self._collection_name,
                points_selector=qdrant_models.FilterSelector(
                    filter=qdrant_models.Filter(
                        must=[
                            qdrant_models.FieldCondition(
                                key="workspace_id",
                                match=qdrant_models.MatchValue(value=str(workspace_id)),
                            ),
                            qdrant_models.FieldCondition(
                                key="user_story_id",
                                match=qdrant_models.MatchValue(value=user_story_id),
                            ),
                        ]
                    )
                ),
                wait=True,
            )
        except Exception as e:
            logger.error(
                "Qdrant delete_by_story failed; story point cleanup not verified: %s",
                e,
                extra={
                    "workspace_id": str(workspace_id),
                    "user_story_id": user_story_id,
                    "collection": self._collection_name,
                    "reason": "delete_failed",
                },
            )
            raise VectorStoreError(f"Qdrant delete_by_story failed: {e}") from e

    async def set_has_invalid_tasks(self, *, extraction_id: str, has_invalid_tasks: bool) -> None:
        """Set the validity flag on the point whose id IS ``extraction_id``.

        No search is involved: ``store_extraction`` upserts with
        ``id=extraction_id``, so the point is addressable by the extraction id
        directly. A point that does not exist is a no-op — nothing was ever
        stored, so nothing can be retrieved, so there is nothing to flag and
        not an error.

        Unlike ``store_extraction``/``search_similar`` — which degrade gracefully
        and never raise — this method raises ``VectorStoreError`` on failure: its
        caller is a destructive-adjacent operation (the mark handlers' refresh,
        which runs before the relational write per the accepted ``(correction)``)
        that must not proceed — and must not persist the mark — on an unverified
        result.

        ``set_payload`` without a ``key`` merges the mapping into the stored
        payload, so the other nine payload keys survive; this is not a re-embed
        and not a re-upsert. ``wait=True`` makes the flag observable when the
        call returns.

        Raises:
            VectorStoreError: when the client is unavailable or the flag write fails.
        """
        client = await self._get_client()
        if client is None:
            raise VectorStoreError("Qdrant client unavailable; validity flag cannot be verified")

        try:
            await client.set_payload(
                collection_name=self._collection_name,
                payload={"has_invalid_tasks": has_invalid_tasks},
                points=[extraction_id],
                wait=True,
            )
        except Exception as e:
            logger.error(
                "Qdrant set_payload failed; validity flag not verified: %s",
                e,
                extra={
                    "extraction_id": extraction_id,
                    "collection": self._collection_name,
                    "reason": "set_payload_failed",
                },
            )
            raise VectorStoreError(f"Qdrant set_has_invalid_tasks failed: {e}") from e
