"""Unit tests for the persisted Trello export job: entity, repository and the
background runner's lifecycle.

The runner mirrors ``run_background_extraction``: a pending row exists before
the work starts, the work runs against repositories built on its own session,
and the row is the only thing a polling client ever sees. A failure must store
both ``error_code`` and — when the port's error carried a ``board_ref`` — the
``board_url``, because a half-built board must stay reachable.
"""

from dataclasses import replace
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from storico.application.export.export_workspace_to_trello import execute_trello_export
from storico.domain.entities.exceptions import (
    TrelloBoardRefusedError,
    TrelloCardRefusedError,
    TrelloCredentialRejectedError,
    TrelloRateLimitExhaustedError,
    TrelloServiceUnavailableError,
)
from storico.domain.entities.extraction import Extraction, ExtractionStatus
from storico.domain.entities.project import Project
from storico.domain.entities.task import Task, TaskStatus
from storico.domain.entities.trello_board import TrelloBoardPlan, TrelloBoardRef
from storico.domain.entities.trello_export import (
    TrelloExport,
    TrelloExportScope,
    TrelloExportStatus,
)
from storico.domain.entities.user_story import UserStory
from storico.domain.entities.workspace import Workspace
from storico.domain.entities.workspace_trello_config import WorkspaceTrelloConfig
from storico.domain.ports.trello_export_port import TrelloExportPort
from storico.infrastructure.database.repositories import (
    SQLAlchemyExtractionRepository,
    SQLAlchemyProjectRepository,
    SQLAlchemyTaskRepository,
    SQLAlchemyUserStoryRepository,
    SQLAlchemyWorkspaceRepository,
)
from storico.infrastructure.database.repositories.trello_export_repository import (
    SQLAlchemyTrelloExportRepository,
)

# ── Fakes and fixtures ───────────────────────────────────────────────


class FakeTrelloPort(TrelloExportPort):
    """Records what the runner asked Trello to build; fails on demand."""

    def __init__(
        self,
        *,
        ref: TrelloBoardRef | None = None,
        error: Exception | None = None,
        on_call=None,
    ) -> None:
        self.plans: list[TrelloBoardPlan] = []
        self.credentials: list[WorkspaceTrelloConfig] = []
        self._ref = ref
        self._error = error
        self._on_call = on_call

    async def create_board(
        self, plan: TrelloBoardPlan, credentials: WorkspaceTrelloConfig
    ) -> TrelloBoardRef:
        self.plans.append(plan)
        self.credentials.append(credentials)
        if self._on_call is not None:
            await self._on_call()
        if self._error is not None:
            raise self._error
        assert self._ref is not None
        return self._ref


_BOARD_REF = TrelloBoardRef(id="board-1", url="https://trello.com/b/board-1")
_CREDENTIALS = WorkspaceTrelloConfig(workspace_id=uuid4(), api_key="key-123", token="tok-456")


async def seed_chain(
    session: AsyncSession, *, tasks: int = 1
) -> tuple[Workspace, Project, UserStory]:
    """A minimal workspace → project → story (+ completed extraction) chain."""
    workspace = await SQLAlchemyWorkspaceRepository(session).save(
        Workspace(name="Seeded WS", slug=f"ws-{uuid4().hex[:8]}", owner_id=uuid4())
    )
    project = await SQLAlchemyProjectRepository(session).save(
        Project(name="Seeded Project", workspace_id=workspace.id)
    )
    story = await SQLAlchemyUserStoryRepository(session).save(
        UserStory(
            project_id=project.id,
            actor="user",
            feature="log in",
            benefit="access account",
            raw_text="As a user, I want to log in so that I can access my account",
        )
    )
    if tasks:
        extraction = await SQLAlchemyExtractionRepository(session).create_next_version(
            Extraction(
                user_story_id=story.id,
                model_used="llama3.2",
                raw_response="",
                provider="ollama",
                temperature=0.1,
                status=ExtractionStatus.COMPLETED,
                completed_at=datetime.now(UTC),
            )
        )
        for index in range(tasks):
            await SQLAlchemyTaskRepository(session).save(
                Task(
                    user_story_id=story.id,
                    extraction_id=extraction.id,
                    title=f"Task {index + 1}",
                    description=f"Description {index + 1}",
                    status=TaskStatus.BACKLOG,
                    priority="medium",
                    labels=["backend"],
                )
            )
    return workspace, project, story


async def seed_current_tasks(
    session: AsyncSession, story_id, count: int, prefix: str = "Current"
) -> list[Task]:
    """Tasks hanging off one *new* completed run — the story's current version."""
    extraction = await SQLAlchemyExtractionRepository(session).create_next_version(
        Extraction(
            user_story_id=story_id,
            model_used="llama3.2",
            raw_response="",
            provider="ollama",
            temperature=0.1,
            status=ExtractionStatus.COMPLETED,
            completed_at=datetime.now(UTC),
        )
    )
    saved: list[Task] = []
    for index in range(count):
        saved.append(
            await SQLAlchemyTaskRepository(session).save(
                Task(
                    user_story_id=story_id,
                    extraction_id=extraction.id,
                    title=f"{prefix} {index + 1}",
                    description="d",
                    status=TaskStatus.TODO,
                    priority="medium",
                )
            )
        )
    return saved


def make_job(workspace_id, scope=TrelloExportScope.WORKSPACE, **kwargs) -> TrelloExport:
    return TrelloExport(workspace_id=workspace_id, scope=scope, **kwargs)


# ── The repository ───────────────────────────────────────────────────


class TestTrelloExportRepository:
    @pytest.mark.asyncio
    async def test_save_then_find_roundtrips_the_job(self, db_session: AsyncSession) -> None:
        workspace, _project, _story = await seed_chain(db_session, tasks=0)
        repo = SQLAlchemyTrelloExportRepository(db_session)

        saved = await repo.save(
            make_job(workspace.id, TrelloExportScope.PROJECT, project_id=uuid4())
        )

        found = await repo.find_by_id(saved.id)
        assert found is not None
        assert found.status.value == "pending"
        assert found.scope.value == "project"
        assert found.board_url is None
        assert found.error_code is None
        assert found.completed_at is None

    @pytest.mark.asyncio
    async def test_update_persists_the_terminal_state(self, db_session: AsyncSession) -> None:
        workspace, _project, _story = await seed_chain(db_session, tasks=0)
        repo = SQLAlchemyTrelloExportRepository(db_session)
        job = await repo.save(make_job(workspace.id))

        await repo.save(
            replace(
                job,
                status=TrelloExportStatus.COMPLETED,
                board_id=_BOARD_REF.id,
                board_url=_BOARD_REF.url,
                cards_created=3,
                completed_at=datetime.now(UTC),
            )
        )

        found = await repo.find_by_id(job.id)
        assert found is not None
        assert found.status.value == "completed"
        assert found.board_url == _BOARD_REF.url
        assert found.cards_created == 3

    @pytest.mark.asyncio
    async def test_find_by_id_unknown_returns_none(self, db_session: AsyncSession) -> None:
        assert await SQLAlchemyTrelloExportRepository(db_session).find_by_id(uuid4()) is None


# ── The lifecycle ────────────────────────────────────────────────────


class TestExecuteTrelloExportLifecycle:
    @pytest.mark.asyncio
    async def test_pending_to_running_to_completed(self, db_session: AsyncSession) -> None:
        workspace, _project, _story = await seed_chain(db_session)
        repo = SQLAlchemyTrelloExportRepository(db_session)
        job = await repo.save(make_job(workspace.id))

        observed: list[str] = []

        async def note_running() -> None:
            row = await repo.find_by_id(job.id)
            assert row is not None
            observed.append(row.status.value)

        port = FakeTrelloPort(ref=_BOARD_REF, on_call=note_running)
        await execute_trello_export(
            export_id=job.id,
            workspace_id=workspace.id,
            board_name=workspace.name,
            scope=TrelloExportScope.WORKSPACE,
            project_id=None,
            user_story_id=None,
            credentials=_CREDENTIALS,
            task_repo=SQLAlchemyTaskRepository(db_session),
            story_repo=SQLAlchemyUserStoryRepository(db_session),
            export_repo=repo,
            port=port,
        )

        assert observed == ["running"]
        finished = await repo.find_by_id(job.id)
        assert finished is not None
        assert finished.status.value == "completed"
        assert finished.board_id == _BOARD_REF.id
        assert finished.board_url == _BOARD_REF.url
        assert finished.cards_created == 1
        assert finished.completed_at is not None
        assert finished.error_code is None

    @pytest.mark.asyncio
    async def test_the_port_receives_the_plan_and_the_credentials(
        self, db_session: AsyncSession
    ) -> None:
        workspace, _project, _story = await seed_chain(db_session)
        repo = SQLAlchemyTrelloExportRepository(db_session)
        job = await repo.save(make_job(workspace.id))

        port = FakeTrelloPort(ref=_BOARD_REF)
        await execute_trello_export(
            export_id=job.id,
            workspace_id=workspace.id,
            board_name=workspace.name,
            scope=TrelloExportScope.WORKSPACE,
            project_id=None,
            user_story_id=None,
            credentials=_CREDENTIALS,
            task_repo=SQLAlchemyTaskRepository(db_session),
            story_repo=SQLAlchemyUserStoryRepository(db_session),
            export_repo=repo,
            port=port,
        )

        assert port.plans[0].name == workspace.name
        assert port.credentials[0] is _CREDENTIALS

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("error", "expected_code"),
        [
            (TrelloCredentialRejectedError(), "TRELLO_CREDENTIAL_REJECTED"),
            (TrelloServiceUnavailableError(), "TRELLO_SERVICE_UNAVAILABLE"),
            (TrelloRateLimitExhaustedError(), "TRELLO_RATE_LIMIT_EXHAUSTED"),
            (TrelloBoardRefusedError(), "TRELLO_BOARD_REFUSED"),
            (TrelloCardRefusedError(), "TRELLO_CARD_REFUSED"),
        ],
    )
    async def test_typed_failures_store_their_error_code(
        self, db_session: AsyncSession, error: Exception, expected_code: str
    ) -> None:
        workspace, _project, _story = await seed_chain(db_session)
        repo = SQLAlchemyTrelloExportRepository(db_session)
        job = await repo.save(make_job(workspace.id))

        await execute_trello_export(
            export_id=job.id,
            workspace_id=workspace.id,
            board_name=workspace.name,
            scope=TrelloExportScope.WORKSPACE,
            project_id=None,
            user_story_id=None,
            credentials=_CREDENTIALS,
            task_repo=SQLAlchemyTaskRepository(db_session),
            story_repo=SQLAlchemyUserStoryRepository(db_session),
            export_repo=repo,
            port=FakeTrelloPort(error=error),
        )

        failed = await repo.find_by_id(job.id)
        assert failed is not None
        assert failed.status.value == "failed"
        assert failed.error_code == expected_code
        assert failed.completed_at is not None

    @pytest.mark.asyncio
    async def test_a_failure_carrying_a_board_ref_keeps_the_board_reachable(
        self, db_session: AsyncSession
    ) -> None:
        workspace, _project, _story = await seed_chain(db_session)
        repo = SQLAlchemyTrelloExportRepository(db_session)
        job = await repo.save(make_job(workspace.id))

        await execute_trello_export(
            export_id=job.id,
            workspace_id=workspace.id,
            board_name=workspace.name,
            scope=TrelloExportScope.WORKSPACE,
            project_id=None,
            user_story_id=None,
            credentials=_CREDENTIALS,
            task_repo=SQLAlchemyTaskRepository(db_session),
            story_repo=SQLAlchemyUserStoryRepository(db_session),
            export_repo=repo,
            port=FakeTrelloPort(error=TrelloCardRefusedError(board_ref=_BOARD_REF)),
        )

        failed = await repo.find_by_id(job.id)
        assert failed is not None
        assert failed.board_url == _BOARD_REF.url
        assert failed.board_id == _BOARD_REF.id

    @pytest.mark.asyncio
    async def test_a_failure_without_a_board_ref_stores_no_url(
        self, db_session: AsyncSession
    ) -> None:
        workspace, _project, _story = await seed_chain(db_session)
        repo = SQLAlchemyTrelloExportRepository(db_session)
        job = await repo.save(make_job(workspace.id))

        await execute_trello_export(
            export_id=job.id,
            workspace_id=workspace.id,
            board_name=workspace.name,
            scope=TrelloExportScope.WORKSPACE,
            project_id=None,
            user_story_id=None,
            credentials=_CREDENTIALS,
            task_repo=SQLAlchemyTaskRepository(db_session),
            story_repo=SQLAlchemyUserStoryRepository(db_session),
            export_repo=repo,
            port=FakeTrelloPort(error=TrelloBoardRefusedError()),
        )

        failed = await repo.find_by_id(job.id)
        assert failed is not None
        assert failed.board_url is None
        assert failed.board_id is None

    @pytest.mark.asyncio
    async def test_an_unexpected_failure_is_a_coded_failed_job_not_a_crash(
        self, db_session: AsyncSession
    ) -> None:
        workspace, _project, _story = await seed_chain(db_session)
        repo = SQLAlchemyTrelloExportRepository(db_session)
        job = await repo.save(make_job(workspace.id))

        await execute_trello_export(
            export_id=job.id,
            workspace_id=workspace.id,
            board_name=workspace.name,
            scope=TrelloExportScope.WORKSPACE,
            project_id=None,
            user_story_id=None,
            credentials=_CREDENTIALS,
            task_repo=SQLAlchemyTaskRepository(db_session),
            story_repo=SQLAlchemyUserStoryRepository(db_session),
            export_repo=repo,
            port=FakeTrelloPort(error=RuntimeError("exploded")),
        )

        failed = await repo.find_by_id(job.id)
        assert failed is not None
        assert failed.status.value == "failed"
        assert failed.error_code == "INTERNAL_ERROR"

    @pytest.mark.asyncio
    async def test_no_credential_reaches_the_job_row_or_the_log(
        self, db_session: AsyncSession, caplog: pytest.LogCaptureFixture
    ) -> None:
        workspace, _project, _story = await seed_chain(db_session)
        repo = SQLAlchemyTrelloExportRepository(db_session)
        job = await repo.save(make_job(workspace.id))

        with caplog.at_level("DEBUG"):
            await execute_trello_export(
                export_id=job.id,
                workspace_id=workspace.id,
                board_name=workspace.name,
                scope=TrelloExportScope.WORKSPACE,
                project_id=None,
                user_story_id=None,
                credentials=_CREDENTIALS,
                task_repo=SQLAlchemyTaskRepository(db_session),
                story_repo=SQLAlchemyUserStoryRepository(db_session),
                export_repo=repo,
                port=FakeTrelloPort(error=TrelloCardRefusedError(board_ref=_BOARD_REF)),
            )

        failed = await repo.find_by_id(job.id)
        assert failed is not None
        row_text = repr(failed)
        assert "key-123" not in row_text
        assert "tok-456" not in row_text
        assert "key-123" not in caplog.text
        assert "tok-456" not in caplog.text


# ── Scope and version reads ──────────────────────────────────────────


class TestExportReads:
    @pytest.mark.asyncio
    async def test_workspace_scope_reads_the_whole_workspace(
        self, db_session: AsyncSession
    ) -> None:
        workspace, project, story = await seed_chain(db_session)
        other_story = await SQLAlchemyUserStoryRepository(db_session).save(
            UserStory(
                project_id=project.id,
                actor="user",
                feature="sign up",
                benefit="have an account",
                raw_text="As a user, I want to sign up",
            )
        )
        await seed_current_tasks(db_session, story.id, 1)
        await seed_current_tasks(db_session, other_story.id, 1)
        repo = SQLAlchemyTrelloExportRepository(db_session)
        job = await repo.save(make_job(workspace.id))

        port = FakeTrelloPort(ref=_BOARD_REF)
        await execute_trello_export(
            export_id=job.id,
            workspace_id=workspace.id,
            board_name=workspace.name,
            scope=TrelloExportScope.WORKSPACE,
            project_id=None,
            user_story_id=None,
            credentials=_CREDENTIALS,
            task_repo=SQLAlchemyTaskRepository(db_session),
            story_repo=SQLAlchemyUserStoryRepository(db_session),
            export_repo=repo,
            port=port,
        )

        titles = [card.title for column in port.plans[0].columns for card in column.cards]
        assert sorted(titles) == ["Current 1", "Current 1"]

    @pytest.mark.asyncio
    async def test_project_scope_reads_only_that_project(self, db_session: AsyncSession) -> None:
        workspace, project, _story = await seed_chain(db_session)
        other_project = await SQLAlchemyProjectRepository(db_session).save(
            Project(name="Other Project", workspace_id=workspace.id)
        )
        other_story = await SQLAlchemyUserStoryRepository(db_session).save(
            UserStory(
                project_id=other_project.id,
                actor="user",
                feature="sign up",
                benefit="have an account",
                raw_text="As a user, I want to sign up",
            )
        )
        await seed_current_tasks(db_session, other_story.id, 1)
        current = await seed_current_tasks(db_session, _story.id, 1)
        repo = SQLAlchemyTrelloExportRepository(db_session)
        job = await repo.save(
            make_job(workspace.id, TrelloExportScope.PROJECT, project_id=project.id)
        )

        port = FakeTrelloPort(ref=_BOARD_REF)
        await execute_trello_export(
            export_id=job.id,
            workspace_id=workspace.id,
            board_name=workspace.name,
            scope=TrelloExportScope.PROJECT,
            project_id=project.id,
            user_story_id=None,
            credentials=_CREDENTIALS,
            task_repo=SQLAlchemyTaskRepository(db_session),
            story_repo=SQLAlchemyUserStoryRepository(db_session),
            export_repo=repo,
            port=port,
        )

        titles = [card.title for column in port.plans[0].columns for card in column.cards]
        assert titles == [current[0].title]

    @pytest.mark.asyncio
    async def test_story_scope_and_current_version_only(self, db_session: AsyncSession) -> None:
        """A superseded version's tasks never reach the board."""
        workspace, _project, story = await seed_chain(db_session)
        superseded = await seed_current_tasks(db_session, story.id, 1, prefix="Superseded")
        current = await seed_current_tasks(db_session, story.id, 1)
        repo = SQLAlchemyTrelloExportRepository(db_session)
        job = await repo.save(
            make_job(workspace.id, TrelloExportScope.STORY, user_story_id=story.id)
        )

        port = FakeTrelloPort(ref=_BOARD_REF)
        await execute_trello_export(
            export_id=job.id,
            workspace_id=workspace.id,
            board_name=workspace.name,
            scope=TrelloExportScope.STORY,
            project_id=None,
            user_story_id=story.id,
            credentials=_CREDENTIALS,
            task_repo=SQLAlchemyTaskRepository(db_session),
            story_repo=SQLAlchemyUserStoryRepository(db_session),
            export_repo=repo,
            port=port,
        )

        titles = [card.title for column in port.plans[0].columns for card in column.cards]
        assert titles == [current[0].title]
        assert superseded[0].title not in titles

    @pytest.mark.asyncio
    async def test_story_scope_attributes_its_own_story(self, db_session: AsyncSession) -> None:
        workspace, _project, story = await seed_chain(db_session)
        await seed_current_tasks(db_session, story.id, 1)
        repo = SQLAlchemyTrelloExportRepository(db_session)
        job = await repo.save(
            make_job(workspace.id, TrelloExportScope.STORY, user_story_id=story.id)
        )

        port = FakeTrelloPort(ref=_BOARD_REF)
        await execute_trello_export(
            export_id=job.id,
            workspace_id=workspace.id,
            board_name=workspace.name,
            scope=TrelloExportScope.STORY,
            project_id=None,
            user_story_id=story.id,
            credentials=_CREDENTIALS,
            task_repo=SQLAlchemyTaskRepository(db_session),
            story_repo=SQLAlchemyUserStoryRepository(db_session),
            export_repo=repo,
            port=port,
        )

        cards = [card for column in port.plans[0].columns for card in column.cards]
        assert len(cards) == 1
        assert f"- User Story ID: `{story.id}`" in cards[0].description
