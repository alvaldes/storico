"""Tests for ``DELETE /api/v1/users/me`` — the account-deletion contract (D-a-4, task 5.14).

A new file rather than an append to ``test_user_settings.py``, whose docstring
scopes it to the settings endpoints (the preferences CRUD under ``/settings``):
the account-delete verb is a different contract. Before the invalidation mark
existed, ``UserRepository.delete``'s bare ``delete(UserModel)`` never met a
refusal; once ``task_invalidations.revoked_by`` (``ON DELETE RESTRICT``) can be
populated, the delete of an account whose revocations still stand must be
designed — 409 ``ACCOUNT_DELETE_BLOCKED`` naming the blocking marks — instead
of falling through to the generic handler as a 500.

The FK refusal itself is a Postgres behaviour, but the unit suite can witness
it too: the in-memory engine is a StaticPool (one shared connection per test),
so ``PRAGMA foreign_keys=ON`` set here holds for the route's own session — the
same pattern ``test_stories.py`` uses for its cascade witness.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from httpx import AsyncClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from storico.api.dependencies import get_vector_store
from storico.domain.entities.extraction import ExtractionStatus
from storico.domain.entities.task_invalidation import TaskInvalidation
from storico.domain.entities.user import User
from storico.infrastructure.database.models import TaskInvalidationModel, TaskModel
from storico.infrastructure.database.repositories import SQLAlchemyUserRepository
from storico.infrastructure.database.repositories.task_invalidation_repository import (
    SQLAlchemyTaskInvalidationRepository,
)
from tests._helpers import seed_extraction, seed_task

URL = "/api/v1/users/me"


async def _enforce_sqlite_fks(db_session: AsyncSession) -> None:
    """Turn SQLite FK enforcement on for the shared in-memory connection.

    Without the pragma the ``ON DELETE RESTRICT`` refusal is silent and the
    block test would prove nothing — see the same-named helper in
    ``test_stories.py`` for the StaticPool reasoning.
    """
    await db_session.execute(text("PRAGMA foreign_keys=ON"))


async def _seed_standing_revocation(
    db_session: AsyncSession,
    story_id,
    revoker: User,
) -> TaskInvalidationModel:
    """Seed one completed version, one task, one mark and one revoke by ``revoker``.

    Seeded through the repository birth paths — the same statements the mark
    endpoints use — so the standing revocation the route's pre-check reads is
    the real row shape, not a fixture shortcut.
    """
    extraction = await seed_extraction(
        db_session,
        story_id,
        status=ExtractionStatus.COMPLETED,
        completed_at=datetime(2026, 10, 2, 10, 0, tzinfo=UTC),
    )
    task = await seed_task(db_session, story_id, "Implement login", extraction=extraction)
    repo = SQLAlchemyTaskInvalidationRepository(db_session)
    mark = await repo.create(
        TaskInvalidation(
            task_id=task.id,
            reason="overlaps the export task",
            marked_by=revoker.id,
            marked_at=datetime(2026, 10, 2, 12, 0, tzinfo=UTC),
        )
    )
    await repo.revoke(
        mark.id, revoked_by=revoker.id, revoked_at=datetime(2026, 10, 2, 13, 0, tzinfo=UTC)
    )
    return (await db_session.execute(select(TaskInvalidationModel))).scalars().one()


class TestDeleteAccount:
    """DELETE /api/v1/users/me — the route's first DELETE-verb coverage."""

    @pytest.mark.asyncio
    async def test_it_requires_a_session(self, async_client: AsyncClient) -> None:
        """An unauthenticated delete is refused, as every other verb here."""
        response = await async_client.delete(URL)

        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_an_account_with_no_revocations_is_deleted_as_before(
        self, authed_client: AsyncClient, db_session: AsyncSession, authed_user: User
    ) -> None:
        """No standing revokes: the delete succeeds and the account is gone.

        This pins the unchanged success contract — the pre-check only ever
        answers when a standing revocation exists.
        """
        response = await authed_client.delete(URL)

        assert response.status_code == 200, response.text
        assert response.json()["message"] == "Account deleted successfully"
        assert await SQLAlchemyUserRepository(db_session).find_by_id(authed_user.id) is None

    @pytest.mark.asyncio
    async def test_a_standing_revocation_blocks_the_delete_with_409(
        self,
        authed_client: AsyncClient,
        authed_user: User,
        db_session: AsyncSession,
        seed_workspace,
    ) -> None:
        """One standing revoke: 409 ``ACCOUNT_DELETE_BLOCKED`` and nothing deleted.

        The envelope's ``detail`` carries a readable sentence, the count and one
        entry per blocking mark (story id, version number, task title); the
        account, its revocation row and the marked task are all still there
        afterwards — the refusal refuses, it does not partially delete.
        """
        await _enforce_sqlite_fks(db_session)
        seeded = await seed_workspace(stories=1)
        await _seed_standing_revocation(db_session, seeded.story_id, authed_user)

        response = await authed_client.delete(URL)

        assert response.status_code == 409, response.text
        body = response.json()
        assert body["error_code"] == "ACCOUNT_DELETE_BLOCKED"
        detail = body["detail"]
        assert "revocation" in detail["message"].lower()
        assert detail["count"] == 1
        assert detail["revocations"] == [
            {
                "user_story_id": str(seeded.story_id),
                "version_number": 1,
                "task_title": "Implement login",
            }
        ]
        # The account, its revocation and the marked rows all survive.
        assert await SQLAlchemyUserRepository(db_session).find_by_id(authed_user.id) is not None
        marks = list((await db_session.execute(select(TaskInvalidationModel))).scalars())
        assert len(marks) == 1
        assert marks[0].revoked_by == authed_user.id
        assert marks[0].revoked_at is not None
        tasks = (
            (
                await db_session.execute(
                    select(TaskModel).where(TaskModel.user_story_id == seeded.story_id)
                )
            )
            .scalars()
            .all()
        )
        assert len(tasks) == 1

    @pytest.mark.asyncio
    async def test_the_block_clears_when_the_marking_story_is_deleted(
        self,
        app,
        authed_client: AsyncClient,
        authed_user: User,
        db_session: AsyncSession,
        seed_workspace,
    ) -> None:
        """Once the marking story is gone, the same account deletes cleanly.

        There is no endpoint that un-revokes a revoke — the revoke history is
        the record (D12) — so the actionable clearing path is the sanctioned
        one: deleting the story cascades its marks away and the pre-check's
        list empties. A bare ``uuid4()`` story would also clear the list, but
        only by never having held a mark; this pins the real path.
        """
        app.dependency_overrides[get_vector_store] = lambda: None
        await _enforce_sqlite_fks(db_session)
        seeded = await seed_workspace(stories=1)
        await _seed_standing_revocation(db_session, seeded.story_id, authed_user)

        blocked = await authed_client.delete(URL)
        assert blocked.status_code == 409

        story_deleted = await authed_client.delete(f"/api/v1/stories/{seeded.story_id}")
        assert story_deleted.status_code == 204, story_deleted.text

        response = await authed_client.delete(URL)

        assert response.status_code == 200, response.text
        assert await SQLAlchemyUserRepository(db_session).find_by_id(authed_user.id) is None
