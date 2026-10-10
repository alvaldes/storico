"""The Trello board plan builder — rows in, ``TrelloBoardPlan`` out.

Pure and unit-testable: everything the adapter will later do to Trello is
decided here, so the adapter stays a dumb executor and the decisions — column
order, story attribution, dependency resolution — live next to the rules they
implement.

The five columns are the five Kanban states in the canonical order, taken from
``TaskStatus`` itself: the enum's declaration order *is* the flow order the
frontend's ``TASK_STATUSES`` mirrors, so the builder iterates the enum instead
of re-spelling the five names in a second list that could drift.

The card description carries the story attribution in csv2trello's metadata
shape (``csv2trello/core/mapper.py:217-228``): a ``---`` rule, a ``**Metadata:**``
header, then bullet lines — here the story's id and a preview of its text,
truncated at csv2trello's 100 characters with the same ellipsis. D2 chose
status lists rather than one list per story, so this block is the only place a
card still names the story it came from.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from uuid import UUID

from storico.domain.entities.task import Task, TaskStatus
from storico.domain.entities.trello_board import TrelloBoardPlan, TrelloCard, TrelloColumn
from storico.domain.services.dependency_resolution import (
    build_dependency_title_index,
    resolve_dependency,
)

# csv2trello's preview rule (core/mapper.py:225-228): the first 100 characters,
# plus an ellipsis when anything was cut.
_STORY_PREVIEW_LIMIT = 100


def _column_name(status: TaskStatus) -> str:
    """The human column name for a status value.

    The single carve-out is ``todo`` — Trello's column reads "To Do", and
    every other value reads as its own words with underscores widened.
    """
    if status is TaskStatus.TODO:
        return "To Do"
    return status.value.replace("_", " ").title()


def _story_metadata_block(task: Task, story_text_by_id: Mapping[UUID, str]) -> str:
    """The csv2trello-shaped attribution block, or ``""`` for an unknown story.

    A story whose row is gone must not fabricate an attribution: an unresolvable
    story renders nothing rather than a placeholder that looks like data.
    """
    story_text = story_text_by_id.get(task.user_story_id)
    if story_text is None:
        return ""
    preview = story_text[:_STORY_PREVIEW_LIMIT]
    if len(story_text) > _STORY_PREVIEW_LIMIT:
        preview += "..."
    return "\n".join(
        [
            "\n---",
            "**Metadata:**",
            f"- User Story ID: `{task.user_story_id}`",
            f"- User Story: _{preview}_",
        ]
    )


def build_trello_board_plan(
    *,
    board_name: str,
    tasks: Sequence[Task],
    story_text_by_id: Mapping[UUID, str],
) -> TrelloBoardPlan:
    """Build the whole board plan from the export's rows.

    ``tasks`` are the rows the scope resolved — already current-version-only,
    because that filter rides the read, not the builder. Columns always exist,
    in Kanban order, even when a column would be empty: an empty column is
    information about the workspace, and creating lists conditionally would
    make two exports of the same data structurally different.
    """
    title_index = build_dependency_title_index([(str(task.id), task.title) for task in tasks])

    cards_by_status: dict[TaskStatus, list[TrelloCard]] = {status: [] for status in TaskStatus}
    for task in tasks:
        dependency_titles = tuple(
            resolve_dependency(dependency, title_index) for dependency in task.dependencies
        )
        cards_by_status[task.status].append(
            TrelloCard(
                title=task.title,
                description=task.description + _story_metadata_block(task, story_text_by_id),
                labels=tuple(task.labels),
                dependency_titles=dependency_titles,
            )
        )

    columns = tuple(
        TrelloColumn(name=_column_name(status), cards=tuple(cards_by_status[status]))
        for status in TaskStatus
    )
    return TrelloBoardPlan(name=board_name, columns=columns)
