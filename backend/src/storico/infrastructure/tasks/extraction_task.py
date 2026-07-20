"""Celery task for background LLM extraction.

Migrated from ``asyncio.create_task`` (inline background function in
``extraction.py``) to a proper Celery task. The worker runs in a separate
process and the task survives API server restarts.

Run the worker::

    celery -A storico.infrastructure.tasks worker --loglevel=info
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
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
from storico.infrastructure.tasks import celery_app
from storico.infrastructure.vector import EmbeddingService, QdrantAdapter

logger = logging.getLogger(__name__)


@celery_app.task(
    bind=True,
    max_retries=2,
    default_retry_delay=60,
    acks_late=True,
    track_started=True,
)
def extract_from_story_task(
    self,
    extraction_id: str,
    user_story_id: str,
    model: str,
    temperature: float | None = None,
    validate: bool = False,
    provider: str = "ollama",
    api_key: str | None = None,
    base_url: str | None = None,
) -> dict:
    """Celery task: run LLM extraction and persist results.

    Accepts string UUIDs (Celery serialisation requirement) and converts
    them internally.

    Returns a dict with ``{"extraction_id": ..., "status": ..., "task_count": ...}``
    on success, or raises on failure (Celery retries up to ``max_retries``).
    """
    extraction_uuid = UUID(extraction_id)
    story_uuid = UUID(user_story_id)

    try:
        asyncio.run(
            _run_celery_extraction(
                extraction_id=extraction_uuid,
                story_id=story_uuid,
                model=model,
                temperature=temperature,
                validate=validate,
                provider=provider,
                api_key=api_key,
                base_url=base_url,
            )
        )
    except (LLMError, ParseError) as exc:
        logger.error("Celery extraction %s failed (will NOT retry): %s", extraction_id, exc)
        asyncio.run(
            _mark_extraction_failed_async(
                extraction_id=extraction_uuid,
                error_info=str(exc),
            )
        )
        # Don't retry — these errors are deterministic (bad story, bad LLM response)
        return {"extraction_id": extraction_id, "status": "failed", "error": str(exc)}
    except Exception as exc:
        logger.exception(
            "Celery extraction %s failed with unexpected error (will retry)", extraction_id
        )
        # Mark failed in DB before retrying
        asyncio.run(
            _mark_extraction_failed_async(
                extraction_id=extraction_uuid,
                error_info=f"Unexpected error: {exc}",
            )
        )
        raise self.retry(exc=exc)

    return {"extraction_id": extraction_id, "status": "completed"}


# ── Async core — mirrors the original _run_background_extraction ──────


async def _run_celery_extraction(
    extraction_id: UUID,
    story_id: UUID,
    model: str,
    temperature: float | None,
    validate: bool,
    provider: str = "ollama",
    api_key: str | None = None,
    base_url: str | None = None,
) -> None:
    """Async core of the Celery extraction task.

    Creates a fresh database session and all required dependencies, then
    runs the full extraction pipeline: load story → LLM call → parse →
    optional judge → persist tasks → store in vector store for RAG.
    """
    from storico.config.settings import Settings  # late import to avoid circular

    settings = Settings.load()

    # Build dependencies with a fresh session
    factory = create_session_factory(get_engine())
    async with factory() as session:
        extraction_repo = SQLAlchemyExtractionRepository(session)
        task_repo = SQLAlchemyTaskRepository(session)
        story_repo = SQLAlchemyUserStoryRepository(session)

        # Create the appropriate LLM adapter based on the workspace's provider.
        # The API key and base_url come from the workspace config (DB), not from
        # environment variables (settings.py fallbacks are only for development).
        if provider == "gemini":
            key = api_key or settings.gemini_api_key
            llm_port = GeminiAdapter(api_key=key)
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
            logger.warning("Qdrant unavailable in Celery task, RAG disabled")
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

        try:
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

            logger.info(
                "Celery extraction %s completed — %d tasks generated",
                extraction_id,
                len(parsed_tasks),
            )

        except (LLMError, ParseError) as exc:
            logger.error("Celery extraction %s failed: %s", extraction_id, exc)
            await _mark_failed(extraction_repo, extraction_id, str(exc))
            raise  # re-raise so the Celery task handler catches it
        except Exception as exc:
            logger.exception("Unexpected error in Celery extraction %s", extraction_id)
            await _mark_failed(extraction_repo, extraction_id, f"Unexpected error: {exc}")
            raise


# ── Helpers ───────────────────────────────────────────────────────────


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
        logger.warning("RAG store failed in Celery task, extraction already saved")


async def _mark_extraction_failed_async(
    extraction_id: UUID,
    error_info: str,
) -> None:
    """Standalone helper to mark an extraction as failed (for Celery retry path).

    Creates its own session since the original one may be closed.
    """
    from storico.infrastructure.database.base import create_session_factory, get_engine

    factory = create_session_factory(get_engine())
    async with factory() as session:
        repo = SQLAlchemyExtractionRepository(session)
        await _mark_failed(repo, extraction_id, error_info)
