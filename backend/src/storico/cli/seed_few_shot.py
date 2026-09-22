"""One-time seed job: migrate legacy ``few_shot_examples`` into Qdrant.

Reads every ``workspace_prompts`` row that still has a non-empty legacy
``few_shot_examples`` value, embeds each example's user story with the active
``EmbeddingPort``, and upserts it into the vector store as a workspace-scoped
point. Point ids are derived from ``workspace_id`` and the example's index in
that workspace's list, which makes the job idempotent: for the same input list
re-running overwrites the same points instead of duplicating them. The mapping
is index-derived, so it is stable only while the input list order is stable.

The ids are UUIDv5 values because Qdrant accepts only an unsigned integer or a
UUID as a point id; a ``"{workspace_id}:{index}"`` string is rejected by the
server.

Run::

    conda run -n storico python -m storico.cli.seed_few_shot

The legacy ``few_shot_examples`` column is intentionally NOT dropped here — it
is retained read-only until this job has run; a follow-up migration drops it.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from storico.config.settings import Settings
from storico.domain.ports import VectorStorePort
from storico.infrastructure.database.base import create_session_factory, get_engine
from storico.infrastructure.database.models import WorkspacePromptModel
from storico.infrastructure.vector import QdrantAdapter, get_embedding_port

if TYPE_CHECKING:
    from storico.domain.ports import EmbeddingPort

logger = logging.getLogger(__name__)

SEED_MODEL_USED = "seed"


async def run_seed(session: AsyncSession, vector_store: VectorStorePort) -> int:
    """Iterate workspaces with legacy examples and upsert them into Qdrant.

    Idempotent: point ids derive from the workspace id and the example index, so
    re-running overwrites existing points. Examples with a blank user story or
    blank tasks are skipped, and an example the store rejected is not counted.
    Returns the number of examples that actually landed.
    """
    result = await session.execute(select(WorkspacePromptModel))
    rows = result.scalars().all()

    count = 0
    for row in rows:
        raw = row.few_shot_examples or {}
        examples = raw.get("items", []) if isinstance(raw, dict) else []
        if not examples:
            continue

        for index, example in enumerate(examples):
            if not isinstance(example, dict):
                continue
            user_story = example.get("user_story", "")
            tasks = example.get("tasks", "")
            if not user_story.strip() or not tasks.strip():
                logger.info(
                    "Skipping blank/short example %s:%s (workspace %s)",
                    row.workspace_id,
                    index,
                    row.workspace_id,
                )
                continue

            point_id = str(uuid5(NAMESPACE_URL, f"storico:seed:{row.workspace_id}:{index}"))
            stored = await vector_store.store_extraction(
                extraction_id=point_id,
                user_story_text=user_story,
                tasks_summary=tasks,
                model_used=SEED_MODEL_USED,
                workspace_id=row.workspace_id,
            )
            if stored:
                count += 1
            else:
                logger.warning(
                    "Store rejected example %s (workspace %s); not counted as seeded",
                    index,
                    row.workspace_id,
                )

    return count


async def _run_seed_with_deps(settings: Settings, vector_store: VectorStorePort) -> int:
    """Open a DB session and run ``run_seed``."""
    factory = create_session_factory(get_engine())
    async with factory() as session:
        count = await run_seed(session, vector_store)
    return count


def main() -> None:
    """Entrypoint for ``python -m storico.cli.seed_few_shot``."""
    logging.basicConfig(level=logging.INFO)
    settings = Settings.load()
    embedding_port: EmbeddingPort = get_embedding_port(settings)
    vector_store = QdrantAdapter(
        embedding_port=embedding_port,
        qdrant_url=settings.qdrant_url,
        qdrant_api_key=settings.qdrant_api_key,
        collection_name=settings.qdrant_collection,
        vector_size=settings.embedding_dimensions,
    )
    count = asyncio.run(_run_seed_with_deps(settings, vector_store))
    logger.info("Seeded %d few-shot example(s)", count)
    print(f"Seeded {count} few-shot example(s)", flush=True)


if __name__ == "__main__":
    main()
