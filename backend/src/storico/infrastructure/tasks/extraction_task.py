"""Background extraction — runs as ``asyncio.create_task`` in the API process.

Replaces the previous Celery task with an async function that runs in the
same event loop as the web server.  No Redis, no worker process.

Call pattern (in route handler)::

    asyncio.create_task(run_background_extraction(...))
    return 202 Accepted  # client polls GET /extractions/{id}

The function:

- Preserves the "pending → completed/failed" flow so the client's polling
  endpoint works without changes.
- Retries up to ``max_retries`` times with exponential backoff on transient
  errors (connection timeouts, 5xx).  Deterministic errors (bad story, bad
  LLM response) are not retried.
- On catastrophic failure (server crash mid-extraction), the extraction
  stays ``pending``.  Call ``recover_stuck_extractions()`` at startup to
  mark those as ``failed``.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta
from uuid import UUID

from storico.domain.entities import Extraction, Task
from storico.domain.entities.exceptions import LLMError, ParseError
from storico.domain.ports import LLMConfig, VectorStorePort
from storico.domain.services.extraction_judge_service import LLMJudgeService
from storico.domain.services.extraction_service import ExtractionService, RAGConfig
from storico.infrastructure.database.base import create_session_factory, get_engine
from storico.infrastructure.database.repositories import (
    SQLAlchemyExtractionRepository,
    SQLAlchemyTaskRepository,
    SQLAlchemyUserStoryRepository,
)
from storico.infrastructure.llm import GeminiAdapter, OllamaAdapter, PromptManager, TaskParser
from storico.infrastructure.vector import EmbeddingService, QdrantAdapter

logger = logging.getLogger(__name__)

# ── Public API ─────────────────────────────────────────────────────


async def run_background_extraction(
    extraction_id: UUID,
    story_id: UUID,
    model: str,
    temperature: float | None = None,
    validate: bool = False,
    provider: str = "ollama",
    api_key: str | None = None,
    base_url: str | None = None,
    max_retries: int = 2,
) -> None:
    """Run LLM extraction in the background and persist results.

    Designed to be launched via ``asyncio.create_task``.  The extraction
    record is expected to already exist with ``status="pending"`` — this
    function updates it to ``completed`` or ``failed``.

    Args:
        extraction_id: ID of the pending extraction record.
        story_id: ID of the user story to extract from.
        model: LLM model name (e.g. ``gemini-2.0-flash``, ``llama3.2``).
        temperature: Generation temperature (default: 0.1).
        validate: Whether to run LLM-as-a-Judge validation.
        provider: ``"ollama"`` or ``"gemini"``.
        api_key: API key for the provider (Gemini).
        base_url: Base URL for the provider (Ollama).
        max_retries: Number of retry attempts on transient errors.
    """
    retry_delay = 1  # seconds, doubles each attempt

    for attempt in range(max_retries + 1):
        try:
            await _run_extraction(
                extraction_id=extraction_id,
                story_id=story_id,
                model=model,
                temperature=temperature,
                validate=validate,
                provider=provider,
                api_key=api_key,
                base_url=base_url,
            )
            logger.info(
                "Extraction %s completed", extraction_id,
            )
            return  # success

        except (LLMError, ParseError) as exc:
            # Deterministic errors — don't retry
            logger.error(
                "Extraction %s failed (will NOT retry): %s", extraction_id, exc,
            )
            await _mark_extraction_failed(extraction_id, str(exc))
            return

        except Exception as exc:
            logger.exception(
                "Extraction %s failed with unexpected error (attempt %d/%d)",
                extraction_id,
                attempt + 1,
                max_retries + 1,
            )
            if attempt < max_retries:
                await asyncio.sleep(retry_delay)
                retry_delay *= 2
            else:
                await _mark_extraction_failed(
                    extraction_id,
                    f"Unexpected error after {max_retries + 1} attempts: {exc}",
                )


async def recover_stuck_extractions(max_age_minutes: int = 5) -> None:
    """Mark any ``pending`` extractions older than *max_age_minutes* as
    ``failed``.

    Call this once during application startup to clean up extractions
    that were abandoned when the server crashed.
    """
    factory = create_session_factory(get_engine())
    async with factory() as session:
        repo = SQLAlchemyExtractionRepository(session)
        deadline = datetime.now(UTC) - timedelta(minutes=max_age_minutes)
        try:
            all_extractions = await repo.list()
        except Exception:
            logger.warning("Could not list extractions for recovery")
            return

        recovered = 0
        for ext in all_extractions:
            if ext.status == "pending" and ext.created_at and ext.created_at < deadline:
                await repo.save(
                    Extraction(
                        id=ext.id,
                        user_story_id=ext.user_story_id,
                        model_used=ext.model_used or "",
                        raw_response=ext.raw_response or "",
                        status="failed",
                        error_info="Server restarted while extraction was pending",
                        prompt_config=ext.prompt_config,
                        created_at=ext.created_at,
                    )
                )
                recovered += 1

        if recovered:
            logger.warning("Recovered %d stuck pending extraction(s)", recovered)


# ── Internal extraction logic ─────────────────────────────────────


async def _run_extraction(
    extraction_id: UUID,
    story_id: UUID,
    model: str,
    temperature: float | None,
    validate: bool,
    provider: str = "ollama",
    api_key: str | None = None,
    base_url: str | None = None,
) -> None:
    """Core extraction — loads story, calls LLM, persists results.

    Creates a fresh database session and all required dependencies,
    then runs the full pipeline: load story → LLM call → parse →
    optional judge → persist tasks → store in vector store.
    """
    from storico.config.settings import Settings  # late import to avoid circular

    settings = Settings.load()

    factory = create_session_factory(get_engine())
    async with factory() as session:
        extraction_repo = SQLAlchemyExtractionRepository(session)
        task_repo = SQLAlchemyTaskRepository(session)
        story_repo = SQLAlchemyUserStoryRepository(session)

        # LLM adapter — API key MUST come from workspace config, not env
        if provider == "gemini":
            if not api_key:
                raise LLMError(
                    "Gemini API key is not configured for this workspace. "
                    "Set it in Workspace Settings before extracting."
                )
            llm_port = GeminiAdapter(api_key=api_key)
        else:
            url = base_url or settings.ollama_host
            llm_port = OllamaAdapter(base_url=url)

        prompt_manager = PromptManager()
        task_parser = TaskParser()

        embedding_service = EmbeddingService(
            base_url=settings.ollama_host,
            model=settings.embedding_model,
        )
        try:
            vector_store: VectorStorePort | None = QdrantAdapter(
                embedding_service=embedding_service,
                qdrant_url=settings.qdrant_url,
                collection_name=settings.qdrant_collection,
                vector_size=settings.embedding_dimensions,
            )
        except Exception:
            logger.warning("Qdrant unavailable, RAG disabled")
            vector_store = None

        extraction_service = ExtractionService(
            llm_port=llm_port,
            prompt_manager=prompt_manager,
            task_parser=task_parser,
            extraction_repo=extraction_repo,
            task_repo=task_repo,
            judge_service=LLMJudgeService(llm_port=llm_port, prompt_manager=prompt_manager),
            vector_store=vector_store,
            rag_config=RAGConfig(
                max_examples=settings.rag_max_examples,
                similarity_threshold=settings.rag_similarity_threshold,
            ),
        )

        # 1. Load user story
        story = await story_repo.find_by_id(story_id)
        if story is None:
            await _mark_failed(extraction_repo, extraction_id, "User story not found")
            return

        # 2. Build LLM config
        llm_config = LLMConfig(
            model=model,
            temperature=temperature if temperature is not None else 0.1,
            max_tokens=2048,
            timeout=120,
        )

        # 3. Run extraction (prompt → LLM → parse) — no persistence yet
        parsed_tasks, raw_response = await extraction_service.extract(story, llm_config)

        # 4. Optionally validate via LLM-as-a-Judge
        confidence: float | None = None
        if validate and extraction_service._judge_service is not None:
            try:
                judge_result = await extraction_service._judge_service.validate(
                    user_story=getattr(story, "raw_text", str(story)),
                    tasks=[
                        {"summary": pt.summary, "description": pt.description}
                        for pt in parsed_tasks
                    ],
                    config=llm_config,
                )
                confidence = judge_result.total_score / 50.0
                if not judge_result.approved and confidence is not None and confidence > 0.5:
                    confidence = 0.5
            except LLMError:
                logger.warning("Judge validation failed, skipping")

        # 5. Persist extraction — reuse the pending ID so the client's poll resolves
        created_at = await _get_created_at(extraction_repo, extraction_id)
        completed = Extraction(
            id=extraction_id,
            user_story_id=story_id,
            model_used=model,
            raw_response=raw_response,
            status="completed",
            confidence_score=confidence,
            prompt_config={"validate": validate, "temperature": temperature},
            created_at=created_at,
        )
        await extraction_repo.save(completed)

        # 6. Persist tasks
        for pt in parsed_tasks:
            task = Task(
                user_story_id=story_id,
                title=pt.summary,
                description=pt.description,
                labels=list(pt.labels),
                dependencies=list(pt.dependencies),
            )
            await task_repo.save(task)

        # 7. Store in vector store for future RAG
        await _store_rag(vector_store, story, extraction_id, parsed_tasks)


# ── Helpers ───────────────────────────────────────────────────────


async def _mark_failed(
    repo: SQLAlchemyExtractionRepository,
    extraction_id: UUID,
    error_info: str,
) -> None:
    """Update a pending extraction record to ``failed`` status."""
    pending = await repo.find_by_id(extraction_id)
    if pending is None:
        return
    failed = Extraction(
        id=extraction_id,
        user_story_id=pending.user_story_id,
        model_used=pending.model_used,
        raw_response=pending.raw_response,
        status="failed",
        error_info=error_info,
        prompt_config=pending.prompt_config,
        created_at=pending.created_at,
    )
    await repo.save(failed)


async def _get_created_at(
    repo: SQLAlchemyExtractionRepository,
    extraction_id: UUID,
) -> datetime:
    """Return the ``created_at`` of the pending extraction, or now as fallback."""
    pending = await repo.find_by_id(extraction_id)
    return pending.created_at if pending else datetime.now(UTC)


async def _store_rag(
    vector_store: VectorStorePort | None,
    story: object,
    extraction_id: UUID,
    parsed_tasks: list,
) -> None:
    """Store extraction result in vector store for future RAG searches."""
    if vector_store is None:
        return
    try:
        tasks_summary = "\n".join(
            f"{i + 1}. {t.summary}: {t.description}"
            for i, t in enumerate(parsed_tasks)
        )
        await vector_store.store_extraction(
            extraction_id=str(extraction_id),
            user_story_text=getattr(story, "raw_text", str(story)),
            tasks_summary=tasks_summary,
            model_used="",
            confidence_score=None,
            user_story_id=str(getattr(story, "id", "")),
        )
    except Exception:
        logger.warning("RAG store failed, extraction already saved")


async def _mark_extraction_failed(
    extraction_id: UUID,
    error_info: str,
) -> None:
    """Standalone helper to mark an extraction as failed.

    Creates its own session since the original one may be in a broken state.
    """
    factory = create_session_factory(get_engine())
    async with factory() as session:
        repo = SQLAlchemyExtractionRepository(session)
        await _mark_failed(repo, extraction_id, error_info)
