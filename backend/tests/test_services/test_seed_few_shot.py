"""Unit/integration tests for the legacy few-shot seed job — FR-VEC-5.

Covers idempotence, workspace tagging, and skipping blank/short examples.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from storico.cli.seed_few_shot import run_seed
from storico.domain.entities.workspace_prompt import WorkspacePrompt
from storico.domain.ports import VectorStorePort
from storico.infrastructure.database.repositories.workspace_prompt_repository import (
    SQLAlchemyWorkspacePromptRepository,
)
from tests._helpers import create_workspace


async def _seed_prompt(db_session: AsyncSession, *, examples, ws_id=None, enabled=True):
    """Upsert a workspace prompt row with given legacy examples."""
    if ws_id is None:
        ws = await create_workspace(db_session)
        ws_id = ws.id
    repo = SQLAlchemyWorkspacePromptRepository(db_session)
    prompt = WorkspacePrompt(
        workspace_id=ws_id,
        few_shot_enabled=enabled,
        few_shot_examples=examples,
    )
    saved = await repo.upsert(prompt)
    return saved, ws_id


@pytest.mark.asyncio
class TestSeedFewShot:
    """run_seed migrates legacy examples as workspace-scoped points."""

    async def test_seeds_workspace_scoped_points(self, db_session) -> None:
        """Each legacy example is stored tagged with the workspace id."""
        examples = [
            {"user_story": "As a user, I want login", "tasks": "1. summary: T\ndescription: D"},
        ]
        saved, ws_id = await _seed_prompt(db_session, examples=examples)

        vector_store = AsyncMock(spec=VectorStorePort)
        count = await run_seed(db_session, vector_store)

        assert count == 1
        vector_store.store_extraction.assert_called_once()
        call_kwargs = vector_store.store_extraction.call_args[1]
        assert call_kwargs["workspace_id"] == ws_id
        assert call_kwargs["user_story_text"] == examples[0]["user_story"]
        assert call_kwargs["tasks_summary"] == examples[0]["tasks"]
        # Qdrant accepts only an unsigned integer or a UUID as a point id, so the
        # asserted property is validity, not the exact derivation: a test that
        # re-computes the formula would pass against the server's rejection.
        uuid.UUID(call_kwargs["extraction_id"])
        assert call_kwargs["model_used"] == "seed"

    async def test_idempotent_rerun_uses_same_point_ids(self, db_session) -> None:
        """Re-running produces the same deterministic extraction ids."""
        examples = [
            {"user_story": "As a user, I want login", "tasks": "1. summary: T\ndescription: D"},
            {"user_story": "As an admin, I want audit", "tasks": "1. summary: A\ndescription: B"},
        ]
        await _seed_prompt(db_session, examples=examples)

        vector_store_v1 = AsyncMock(spec=VectorStorePort)
        await run_seed(db_session, vector_store_v1)

        vector_store_v2 = AsyncMock(spec=VectorStorePort)
        await run_seed(db_session, vector_store_v2)

        ids_v1 = [
            c.kwargs["extraction_id"] for c in vector_store_v1.store_extraction.await_args_list
        ]
        ids_v2 = [
            c.kwargs["extraction_id"] for c in vector_store_v2.store_extraction.await_args_list
        ]
        assert ids_v1 == ids_v2
        for point_id in ids_v1:
            uuid.UUID(point_id)
        assert len(set(ids_v1)) == 2

    async def test_skips_empty_example_list(self, db_session) -> None:
        """A prompt row with no legacy examples is not touched."""
        await _seed_prompt(db_session, examples=[])

        vector_store = AsyncMock(spec=VectorStorePort)
        count = await run_seed(db_session, vector_store)

        assert count == 0
        vector_store.store_extraction.assert_not_called()

    async def test_skips_blank_user_story_or_tasks(self, db_session) -> None:
        """Examples with a blank user story or tasks are skipped."""
        examples = [
            {"user_story": "", "tasks": "1. summary: T\ndescription: D"},
            {"user_story": "As a user, I want login", "tasks": ""},
            {"user_story": "Valid story", "tasks": "1. summary: V\ndescription: D"},
        ]
        await _seed_prompt(db_session, examples=examples)

        vector_store = AsyncMock(spec=VectorStorePort)
        count = await run_seed(db_session, vector_store)

        assert count == 1
        # Only the third (fully populated) example was seeded.
        call_kwargs = vector_store.store_extraction.call_args[1]
        uuid.UUID(call_kwargs["extraction_id"])
        assert call_kwargs["user_story_text"] == "Valid story"

    async def test_count_excludes_examples_the_store_rejected(self, db_session) -> None:
        """A rejected store must not be reported as a seeded example.

        This is the bug the live Qdrant probe caught: the adapter swallowed the
        rejection and the job still printed ``Seeded N``.
        """
        examples = [
            {"user_story": "As a user, I want login", "tasks": "1. summary: T\ndescription: D"},
            {"user_story": "As a user, I want logout", "tasks": "1. summary: U\ndescription: E"},
        ]
        await _seed_prompt(db_session, examples=examples)

        vector_store = AsyncMock(spec=VectorStorePort)
        vector_store.store_extraction.return_value = False
        count = await run_seed(db_session, vector_store)

        assert count == 0
        assert vector_store.store_extraction.await_count == 2

    async def test_count_includes_only_stored_examples(self, db_session) -> None:
        """A partial failure reports exactly what landed."""
        examples = [
            {"user_story": "As a user, I want login", "tasks": "1. summary: T\ndescription: D"},
            {"user_story": "As a user, I want logout", "tasks": "1. summary: U\ndescription: E"},
        ]
        await _seed_prompt(db_session, examples=examples)

        vector_store = AsyncMock(spec=VectorStorePort)
        vector_store.store_extraction.side_effect = [True, False]
        count = await run_seed(db_session, vector_store)

        assert count == 1

    async def test_multiple_workspaces_isolated(self, db_session) -> None:
        """Each workspace's examples are tagged with their own workspace id."""
        examples_a = [
            {"user_story": "As a user, I want X", "tasks": "1. summary: X\ndescription: D"}
        ]
        examples_b = [
            {"user_story": "As a user, I want Y", "tasks": "1. summary: Y\ndescription: D"}
        ]
        _, ws_a = await _seed_prompt(db_session, examples=examples_a)
        ws_b = await create_workspace(db_session, name="Second WS")
        await _seed_prompt(db_session, examples=examples_b, ws_id=ws_b.id)

        vector_store = AsyncMock(spec=VectorStorePort)
        await run_seed(db_session, vector_store)

        calls = [c.kwargs for c in vector_store.store_extraction.await_args_list]
        ws_ids = {c["workspace_id"] for c in calls}
        assert ws_ids == {ws_a, ws_b.id}
