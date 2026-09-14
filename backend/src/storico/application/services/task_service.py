"""TaskService — application service for task operations with state validation."""

from __future__ import annotations

from uuid import UUID

from storico.domain.entities import EntityNotFound, Task
from storico.domain.entities.task import TaskStatus
from storico.domain.ports import TaskRepository
from storico.domain.validators.state_machine import (
    VALID_TASK_TRANSITIONS,
    validate_task_transition,
)


class TaskService:
    """Application service for task operations with Kanban flow validation.

    Encapsulates business logic for task state transitions per Kanban flow:
    - BACKLOG ↔ TODO (bidirectional)
    - TODO → IN_PROGRESS
    - IN_PROGRESS → REVIEW or IN_PROGRESS → TODO (rework)
    - REVIEW → DONE (accept) or REVIEW → IN_PROGRESS (request changes)
    - DONE is terminal (no outgoing transitions)
    """

    def __init__(self, task_repo: TaskRepository) -> None:
        self._task_repo = task_repo

    async def update_status(
        self,
        task_id: UUID,
        new_status: TaskStatus,
    ) -> Task:
        """Update a task's status with Kanban flow validation.

        Args:
            task_id: UUID of the task to update.
            new_status: The new TaskStatus to transition to.

        Returns:
            The updated Task entity.

        Raises:
            EntityNotFound: If the task does not exist.
            InvalidStateTransition: If the transition is not allowed per Kanban flow.
        """
        task = await self._task_repo.find_by_id(task_id)
        if task is None:
            raise EntityNotFound("Task", str(task_id))

        if not validate_task_transition(task.status, new_status):
            allowed = VALID_TASK_TRANSITIONS.get(task.status, set())
            raise InvalidStateTransition(
                current_state=task.status,
                attempted_state=new_status,
                allowed_transitions=sorted(allowed, key=lambda s: s.value),
            )

        # Create updated task (Task is frozen dataclass, so we replace)
        from dataclasses import replace
        from datetime import UTC, datetime

        updated = replace(
            task,
            status=new_status,
            updated_at=datetime.now(UTC),
        )
        return await self._task_repo.save(updated)

    async def get_task(self, task_id: UUID) -> Task:
        """Get a task by ID."""
        task = await self._task_repo.find_by_id(task_id)
        if task is None:
            raise EntityNotFound("Task", str(task_id))
        return task

    async def list_tasks_by_story(self, user_story_id: UUID) -> list[Task]:
        """List all tasks for a user story."""
        return await self._task_repo.list_by_story(user_story_id)

    def get_allowed_transitions(self, current_status: TaskStatus) -> set[TaskStatus]:
        """Get all allowed transitions from a given status."""
        return VALID_TASK_TRANSITIONS.get(current_status, set())


class InvalidStateTransition(Exception):
    """Raised when a task state transition is not allowed per Kanban flow."""

    def __init__(
        self,
        current_state: TaskStatus,
        attempted_state: TaskStatus,
        allowed_transitions: list[TaskStatus],
    ) -> None:
        self.current_state = current_state
        self.attempted_state = attempted_state
        self.allowed_transitions = allowed_transitions
        super().__init__(
            f"Invalid state transition from {current_state.value} to {attempted_state.value}. "
            f"Allowed: {[s.value for s in allowed_transitions]}"
        )
