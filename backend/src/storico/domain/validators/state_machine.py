"""State machine validators for domain entities."""

from __future__ import annotations

from storico.domain.entities.task import TaskStatus
from storico.domain.entities.user_story import UserStoryStatus

# UserStoryStatus valid transitions
# PENDING_EXTRACTION -> EXTRACTING (only forward)
# EXTRACTING -> EXTRACTED (success) or FAILED_EXTRACTION (failure)
# EXTRACTED and FAILED_EXTRACTION are terminal (no outgoing transitions)
VALID_USER_STORY_TRANSITIONS: dict[UserStoryStatus, set[UserStoryStatus]] = {
    UserStoryStatus.PENDING_EXTRACTION: {UserStoryStatus.EXTRACTING},
    UserStoryStatus.EXTRACTING: {UserStoryStatus.EXTRACTED, UserStoryStatus.FAILED_EXTRACTION},
    UserStoryStatus.EXTRACTED: set(),
    UserStoryStatus.FAILED_EXTRACTION: set(),
}


def validate_user_story_transition(current: UserStoryStatus, next_status: UserStoryStatus) -> bool:
    """Validate if a UserStoryStatus transition is allowed."""
    return next_status in VALID_USER_STORY_TRANSITIONS.get(current, set())


def get_allowed_user_story_transitions(current: UserStoryStatus) -> set[UserStoryStatus]:
    """Get all allowed transitions from a UserStoryStatus."""
    return VALID_USER_STORY_TRANSITIONS.get(current, set())


# TaskStatus valid transitions (Kanban flow 1:1)
# BACKLOG <-> TODO (bidirectional)
# TODO -> IN_PROGRESS
# IN_PROGRESS -> REVIEW or IN_PROGRESS -> TODO (rework)
# REVIEW -> DONE (accept) or REVIEW -> IN_PROGRESS (request changes)
# DONE is terminal (no outgoing transitions)
#
# Staying in the current status is not a transition and is always allowed
# (see validate_task_transition): a task edit PUT may echo the current
# status. Keep only real transitions in this table.
VALID_TASK_TRANSITIONS: dict[TaskStatus, set[TaskStatus]] = {
    TaskStatus.BACKLOG: {TaskStatus.TODO},
    TaskStatus.TODO: {TaskStatus.IN_PROGRESS, TaskStatus.BACKLOG},
    TaskStatus.IN_PROGRESS: {TaskStatus.REVIEW, TaskStatus.TODO},
    TaskStatus.REVIEW: {TaskStatus.DONE, TaskStatus.IN_PROGRESS},
    TaskStatus.DONE: set(),
}


def validate_task_transition(current: TaskStatus, next_status: TaskStatus) -> bool:
    """Validate if a TaskStatus transition is allowed per Kanban flow.

    A no-op (current == next_status) is not a transition and is always
    valid: PUT /tasks/{id} echoes the current status when the client does
    not change it, and that must not be rejected as an invalid transition.
    """
    if current == next_status:
        return True
    return next_status in VALID_TASK_TRANSITIONS.get(current, set())


def get_allowed_task_transitions(current: TaskStatus) -> set[TaskStatus]:
    """Get all allowed transitions from a TaskStatus."""
    return VALID_TASK_TRANSITIONS.get(current, set())
