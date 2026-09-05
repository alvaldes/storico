"""Unit tests for domain state machines."""

from __future__ import annotations

import pytest

from storico.domain.entities.task import TaskStatus
from storico.domain.entities.user_story import UserStoryStatus
from storico.domain.validators.state_machine import (
    VALID_TASK_TRANSITIONS,
    VALID_USER_STORY_TRANSITIONS,
    get_allowed_task_transitions,
    get_allowed_user_story_transitions,
    validate_task_transition,
    validate_user_story_transition,
)


class TestUserStoryStateMachine:
    """Tests for UserStoryStatus state machine (extraction lifecycle)."""

    def test_pending_extraction_to_extracting_allowed(self) -> None:
        assert validate_user_story_transition(
            UserStoryStatus.PENDING_EXTRACTION, UserStoryStatus.EXTRACTING
        )

    def test_extracting_to_extracted_allowed(self) -> None:
        assert validate_user_story_transition(
            UserStoryStatus.EXTRACTING, UserStoryStatus.EXTRACTED
        )

    def test_extracting_to_failed_extraction_allowed(self) -> None:
        assert validate_user_story_transition(
            UserStoryStatus.EXTRACTING, UserStoryStatus.FAILED_EXTRACTION
        )

    def test_extracted_is_terminal(self) -> None:
        for next_status in UserStoryStatus:
            if next_status != UserStoryStatus.EXTRACTED:
                assert not validate_user_story_transition(
                    UserStoryStatus.EXTRACTED, next_status
                )

    def test_failed_extraction_is_terminal(self) -> None:
        for next_status in UserStoryStatus:
            if next_status != UserStoryStatus.FAILED_EXTRACTION:
                assert not validate_user_story_transition(
                    UserStoryStatus.FAILED_EXTRACTION, next_status
                )

    def test_no_backward_transitions(self) -> None:
        assert not validate_user_story_transition(
            UserStoryStatus.EXTRACTING, UserStoryStatus.PENDING_EXTRACTION
        )
        assert not validate_user_story_transition(
            UserStoryStatus.EXTRACTED, UserStoryStatus.EXTRACTING
        )
        assert not validate_user_story_transition(
            UserStoryStatus.FAILED_EXTRACTION, UserStoryStatus.EXTRACTING
        )

    def test_get_allowed_transitions_returns_correct_sets(self) -> None:
        assert get_allowed_user_story_transitions(UserStoryStatus.PENDING_EXTRACTION) == {
            UserStoryStatus.EXTRACTING
        }
        assert get_allowed_user_story_transitions(UserStoryStatus.EXTRACTING) == {
            UserStoryStatus.EXTRACTED,
            UserStoryStatus.FAILED_EXTRACTION,
        }
        assert get_allowed_user_story_transitions(UserStoryStatus.EXTRACTED) == set()
        assert get_allowed_user_story_transitions(UserStoryStatus.FAILED_EXTRACTION) == set()

    def test_all_user_story_statuses_have_entry_in_transitions_dict(self) -> None:
        for status in UserStoryStatus:
            assert status in VALID_USER_STORY_TRANSITIONS


class TestTaskStateMachine:
    """Tests for TaskStatus state machine (Kanban flow)."""

    @pytest.mark.parametrize(
        "current,next_status",
        [
            (TaskStatus.BACKLOG, TaskStatus.TODO),
            (TaskStatus.TODO, TaskStatus.BACKLOG),
            (TaskStatus.TODO, TaskStatus.IN_PROGRESS),
            (TaskStatus.IN_PROGRESS, TaskStatus.REVIEW),
            (TaskStatus.IN_PROGRESS, TaskStatus.TODO),  # rework
            (TaskStatus.REVIEW, TaskStatus.DONE),  # accept
            (TaskStatus.REVIEW, TaskStatus.IN_PROGRESS),  # changes requested
        ],
    )
    def test_valid_transitions(self, current: TaskStatus, next_status: TaskStatus) -> None:
        assert validate_task_transition(current, next_status)

    @pytest.mark.parametrize(
        "current,next_status",
        [
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
        ],
    )
    def test_invalid_transitions(self, current: TaskStatus, next_status: TaskStatus) -> None:
        assert not validate_task_transition(current, next_status)

    def test_done_is_terminal(self) -> None:
        for next_status in TaskStatus:
            if next_status != TaskStatus.DONE:
                assert not validate_task_transition(TaskStatus.DONE, next_status)

    def test_get_allowed_transitions_returns_correct_sets(self) -> None:
        assert get_allowed_task_transitions(TaskStatus.BACKLOG) == {
            TaskStatus.TODO,
            TaskStatus.BACKLOG,
        }
        assert get_allowed_task_transitions(TaskStatus.TODO) == {
            TaskStatus.IN_PROGRESS,
            TaskStatus.BACKLOG,
        }
        assert get_allowed_task_transitions(TaskStatus.IN_PROGRESS) == {
            TaskStatus.REVIEW,
            TaskStatus.TODO,
        }
        assert get_allowed_task_transitions(TaskStatus.REVIEW) == {
            TaskStatus.DONE,
            TaskStatus.IN_PROGRESS,
        }
        assert get_allowed_task_transitions(TaskStatus.DONE) == set()

    def test_all_task_statuses_have_entry_in_transitions_dict(self) -> None:
        for status in TaskStatus:
            assert status in VALID_TASK_TRANSITIONS

    def test_self_loop_on_backlog_allowed(self) -> None:
        """Idempotent transition BACKLOG -> BACKLOG should be allowed."""
        assert validate_task_transition(TaskStatus.BACKLOG, TaskStatus.BACKLOG)

    def test_self_loop_on_todo_not_allowed_by_default(self) -> None:
        """TODO -> TODO not explicitly allowed (would need explicit design decision)."""
        # Current design doesn't include self-loops except BACKLOG
        assert not validate_task_transition(TaskStatus.TODO, TaskStatus.TODO)