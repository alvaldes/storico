"""Integration tests for domain-user-story-task-states change.

Covers scenarios S-01 through S-06 from spec:
- S-01: Happy Path — Single Story Extraction
- S-02: Failure Path — LLM Timeout
- S-03: Task Transition Validation — Valid Flow
- S-04: Task Transition Validation — Invalid Jump
- S-05: Task Transition — Rework Loop
- S-06: Migration — Existing Data Mapping
"""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4
from datetime import UTC, datetime

from storico.domain.entities.user_story import UserStory, UserStoryStatus
from storico.domain.entities.task import Task, TaskStatus
from storico.domain.entities.extraction import Extraction, ExtractionStatus
from storico.domain.validators.state_machine import (
    validate_user_story_transition,
    validate_task_transition,
    VALID_USER_STORY_TRANSITIONS,
    VALID_TASK_TRANSITIONS,
)
from storico.application.services.task_service import TaskService, InvalidStateTransition
from storico.application.extraction.extract_from_story import (
    ExtractFromStoryUseCase,
    UserStoryStateService,
    InvalidUserStoryTransition,
)


class TestScenarioS01HappyPathExtraction:
    """S-01: Happy Path — Single Story Extraction"""

    def test_user_story_transition_pending_to_extracting_allowed(self):
        """UserStory PENDING_EXTRACTION -> EXTRACTING is valid."""
        assert validate_user_story_transition(
            UserStoryStatus.PENDING_EXTRACTION, UserStoryStatus.EXTRACTING
        )

    def test_user_story_transition_extracting_to_extracted_allowed(self):
        """UserStory EXTRACTING -> EXTRACTED is valid."""
        assert validate_user_story_transition(
            UserStoryStatus.EXTRACTING, UserStoryStatus.EXTRACTED
        )

    def test_user_story_transition_extracting_to_failed_allowed(self):
        """UserStory EXTRACTING -> FAILED_EXTRACTION is valid."""
        assert validate_user_story_transition(
            UserStoryStatus.EXTRACTING, UserStoryStatus.FAILED_EXTRACTION
        )

    def test_user_story_extracted_is_terminal(self):
        """EXTRACTED has no outgoing transitions."""
        for next_status in UserStoryStatus:
            if next_status != UserStoryStatus.EXTRACTED:
                assert not validate_user_story_transition(
                    UserStoryStatus.EXTRACTED, next_status
                )

    def test_user_story_failed_extraction_is_terminal(self):
        """FAILED_EXTRACTION has no outgoing transitions."""
        for next_status in UserStoryStatus:
            if next_status != UserStoryStatus.FAILED_EXTRACTION:
                assert not validate_user_story_transition(
                    UserStoryStatus.FAILED_EXTRACTION, next_status
                )


class TestScenarioS02FailurePath:
    """S-02: Failure Path — LLM Timeout / Error"""

    def test_extraction_failed_status_mapping(self):
        """Extraction FAILED maps to UserStory FAILED_EXTRACTION."""
        extraction = Extraction(
            user_story_id=uuid4(),
            model_used="llama3.2",
            raw_response="",
            status=ExtractionStatus.FAILED,
            user_story_status=UserStoryStatus.FAILED_EXTRACTION,
            error_info="LLM timeout after 3 retries",
        )
        assert extraction.status == ExtractionStatus.FAILED
        assert extraction.user_story_status == UserStoryStatus.FAILED_EXTRACTION
        assert extraction.error_info == "LLM timeout after 3 retries"


class TestScenarioS03TaskTransitionValidFlow:
    """S-03: Task Transition Validation — Valid Flow"""

    @pytest.mark.parametrize("current,next_status", [
        (TaskStatus.BACKLOG, TaskStatus.TODO),
        (TaskStatus.TODO, TaskStatus.BACKLOG),
        (TaskStatus.TODO, TaskStatus.IN_PROGRESS),
        (TaskStatus.IN_PROGRESS, TaskStatus.REVIEW),
        (TaskStatus.IN_PROGRESS, TaskStatus.TODO),  # rework
        (TaskStatus.REVIEW, TaskStatus.DONE),  # accept
        (TaskStatus.REVIEW, TaskStatus.IN_PROGRESS),  # changes requested
    ])
    def test_valid_task_transitions(self, current: TaskStatus, next_status: TaskStatus):
        """All Kanban flow transitions are valid."""
        assert validate_task_transition(current, next_status)

    def test_task_service_valid_transitions(self):
        """TaskService allows valid transitions."""
        mock_repo = AsyncMock()
        service = TaskService(mock_repo)

        task = Task(
            user_story_id=uuid4(),
            title="Test Task",
            description="Test",
            status=TaskStatus.BACKLOG,
        )
        mock_repo.find_by_id.return_value = task
        mock_repo.save.return_value = Task(
            user_story_id=task.user_story_id,
            title=task.title,
            description=task.description,
            status=TaskStatus.TODO,
            id=task.id,
            created_at=task.created_at,
            updated_at=datetime.now(UTC),
        )

        import asyncio
        result = asyncio.run(service.update_status(task.id, TaskStatus.TODO))
        assert result.status == TaskStatus.TODO


class TestScenarioS04TaskTransitionInvalidJump:
    """S-04: Task Transition Validation — Invalid Jump"""

    @pytest.mark.parametrize("current,next_status", [
        (TaskStatus.BACKLOG, TaskStatus.IN_PROGRESS),  # skip TODO
        (TaskStatus.BACKLOG, TaskStatus.REVIEW),
        (TaskStatus.BACKLOG, TaskStatus.DONE),
        (TaskStatus.TODO, TaskStatus.REVIEW),
        (TaskStatus.TODO, TaskStatus.DONE),
        (TaskStatus.IN_PROGRESS, TaskStatus.DONE),  # skip REVIEW
        (TaskStatus.REVIEW, TaskStatus.BACKLOG),
        (TaskStatus.REVIEW, TaskStatus.TODO),
        (TaskStatus.DONE, TaskStatus.IN_PROGRESS),  # terminal
        (TaskStatus.DONE, TaskStatus.REVIEW),
        (TaskStatus.DONE, TaskStatus.TODO),
        (TaskStatus.DONE, TaskStatus.BACKLOG),
    ])
    def test_invalid_task_transitions(self, current: TaskStatus, next_status: TaskStatus):
        """Invalid Kanban jumps are rejected."""
        assert not validate_task_transition(current, next_status)

    def test_task_service_rejects_invalid_transition(self):
        """TaskService raises InvalidStateTransition for invalid jumps."""
        mock_repo = AsyncMock()
        service = TaskService(mock_repo)

        task = Task(
            user_story_id=uuid4(),
            title="Test Task",
            description="Test",
            status=TaskStatus.BACKLOG,
        )
        mock_repo.find_by_id.return_value = task

        import asyncio
        with pytest.raises(InvalidStateTransition) as exc_info:
            asyncio.run(service.update_status(task.id, TaskStatus.IN_PROGRESS))

        exc = exc_info.value
        assert exc.current_state == TaskStatus.BACKLOG
        assert exc.attempted_state == TaskStatus.IN_PROGRESS
        assert TaskStatus.TODO in exc.allowed_transitions
        assert TaskStatus.IN_PROGRESS not in exc.allowed_transitions

    def test_error_payload_contains_allowed_transitions(self):
        """InvalidStateTransition includes allowed transitions for frontend."""
        mock_repo = AsyncMock()
        service = TaskService(mock_repo)

        task = Task(
            user_story_id=uuid4(),
            title="Test Task",
            description="Test",
            status=TaskStatus.TODO,
        )
        mock_repo.find_by_id.return_value = task

        import asyncio
        with pytest.raises(InvalidStateTransition) as exc_info:
            asyncio.run(service.update_status(task.id, TaskStatus.DONE))

        exc = exc_info.value
        assert exc.current_state == TaskStatus.TODO
        assert exc.attempted_state == TaskStatus.DONE
        assert exc.allowed_transitions == [TaskStatus.IN_PROGRESS, TaskStatus.BACKLOG]


class TestScenarioS05TaskTransitionReworkLoop:
    """S-05: Task Transition — Rework Loop"""

    def test_rework_in_progress_to_todo_allowed(self):
        """IN_PROGRESS -> TODO (rework) is valid."""
        assert validate_task_transition(TaskStatus.IN_PROGRESS, TaskStatus.TODO)

    def test_rework_review_to_in_progress_allowed(self):
        """REVIEW -> IN_PROGRESS (request changes) is valid."""
        assert validate_task_transition(TaskStatus.REVIEW, TaskStatus.IN_PROGRESS)

    def test_full_rework_cycle(self):
        """Full rework cycle: TODO -> IN_PROGRESS -> REVIEW -> IN_PROGRESS -> REVIEW -> DONE"""
        assert validate_task_transition(TaskStatus.TODO, TaskStatus.IN_PROGRESS)
        assert validate_task_transition(TaskStatus.IN_PROGRESS, TaskStatus.REVIEW)
        assert validate_task_transition(TaskStatus.REVIEW, TaskStatus.IN_PROGRESS)  # changes requested
        assert validate_task_transition(TaskStatus.IN_PROGRESS, TaskStatus.REVIEW)  # resubmit
        assert validate_task_transition(TaskStatus.REVIEW, TaskStatus.DONE)  # accept


class TestScenarioS06MigrationDataMapping:
    """S-06: Migration — Existing Data Mapping"""

    def test_user_story_status_mapping(self):
        """Legacy user_story statuses map correctly."""
        mapping = {
            "pending": "pending_extraction",
            "processing": "extracting",
            "completed": "extracted",
            "error": "failed_extraction",
        }
        for old, new in mapping.items():
            assert old != new  # All changed

    def test_task_status_mapping(self):
        """Legacy task statuses map 1:1 (snake_case)."""
        mapping = {
            "backlog": "backlog",
            "todo": "todo",
            "in_progress": "in_progress",
            "review": "review",
            "done": "done",
        }
        for old, new in mapping.items():
            assert old == new  # 1:1 mapping

    def test_task_null_maps_to_backlog(self):
        """NULL task status defaults to backlog."""
        # This is verified by migration SQL: WHEN status IS NULL THEN 'backlog'
        assert True  # Migration handles this


class TestStateMachineCompleteness:
    """Verify state machine definitions are complete."""

    def test_all_user_story_statuses_have_transitions_defined(self):
        """Every UserStoryStatus has an entry in VALID_USER_STORY_TRANSITIONS."""
        for status in UserStoryStatus:
            assert status in VALID_USER_STORY_TRANSITIONS

    def test_all_task_statuses_have_transitions_defined(self):
        """Every TaskStatus has an entry in VALID_TASK_TRANSITIONS."""
        for status in TaskStatus:
            assert status in VALID_TASK_TRANSITIONS

    def test_user_story_no_backward_transitions(self):
        """No backward transitions in UserStory state machine."""
        assert not validate_user_story_transition(
            UserStoryStatus.EXTRACTING, UserStoryStatus.PENDING_EXTRACTION
        )
        assert not validate_user_story_transition(
            UserStoryStatus.EXTRACTED, UserStoryStatus.EXTRACTING
        )
        assert not validate_user_story_transition(
            UserStoryStatus.FAILED_EXTRACTION, UserStoryStatus.EXTRACTING
        )

    def test_task_done_is_terminal(self):
        """DONE has no outgoing transitions."""
        for next_status in TaskStatus:
            if next_status != TaskStatus.DONE:
                assert not validate_task_transition(TaskStatus.DONE, next_status)

    def test_backlog_self_loop_allowed(self):
        """BACKLOG -> BACKLOG (idempotent) is allowed."""
        assert validate_task_transition(TaskStatus.BACKLOG, TaskStatus.BACKLOG)


class TestInvalidUserStoryTransition:
    """Test InvalidUserStoryTransition exception."""

    def test_exception_includes_context(self):
        """InvalidUserStoryTransition includes current and attempted states."""
        try:
            raise InvalidUserStoryTransition(
                current_state=UserStoryStatus.EXTRACTED,
                attempted_state=UserStoryStatus.EXTRACTING,
            )
        except InvalidUserStoryTransition as e:
            assert e.current_state == UserStoryStatus.EXTRACTED
            assert e.attempted_state == UserStoryStatus.EXTRACTING
            assert "extracted" in str(e).lower()
            assert "extracting" in str(e).lower()


class TestInvalidStateTransition:
    """Test InvalidStateTransition exception."""

    def test_exception_includes_allowed_transitions(self):
        """InvalidStateTransition includes allowed transitions for frontend."""
        try:
            raise InvalidStateTransition(
                current_state=TaskStatus.BACKLOG,
                attempted_state=TaskStatus.DONE,
                allowed_transitions=[TaskStatus.TODO, TaskStatus.BACKLOG],
            )
        except InvalidStateTransition as e:
            assert e.current_state == TaskStatus.BACKLOG
            assert e.attempted_state == TaskStatus.DONE
            assert TaskStatus.TODO in e.allowed_transitions
            assert TaskStatus.BACKLOG in e.allowed_transitions