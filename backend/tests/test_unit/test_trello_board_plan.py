"""Unit tests for the Trello board plan builder and the shared dependency rule.

The plan builder is pure: rows in, ``TrelloBoardPlan`` out. Everything the
adapter later does to Trello is decided here, so these tests pin the decisions
the record binds: the five Kanban columns in the canonical order (reused from
``TaskStatus``'s declaration order, never re-spelled), the story attribution in
csv2trello's metadata shape, labels carried, dependencies resolved with the
same rule the Markdown export applies — and an unresolvable reference rendered
as the reference, never dropped.

The export scope resolver's tests live beside the rule now, in
``test_export_scope.py``.
"""

from uuid import UUID, uuid4

from storico.domain.entities.task import Task, TaskStatus
from storico.domain.entities.trello_board import TrelloBoardPlan
from storico.domain.services.dependency_resolution import (
    build_dependency_title_index,
    resolve_dependency,
)
from storico.domain.services.trello_board_plan import build_trello_board_plan

# csv2trello truncates the story preview at 100 characters and marks it with an
# ellipsis (core/mapper.py:225-228) — the shape the metadata block inherits.
_STORY_PREVIEW_LIMIT = 100


def make_task(
    title: str,
    *,
    status: TaskStatus = TaskStatus.BACKLOG,
    labels: list[str] | None = None,
    dependencies: list[str] | None = None,
    description: str = "",
    story_id: UUID | None = None,
) -> Task:
    """An in-memory Task — no database; the plan builder is pure."""
    return Task(
        user_story_id=story_id or uuid4(),
        extraction_id=uuid4(),
        title=title,
        description=description,
        status=status,
        priority="medium",
        labels=labels or [],
        dependencies=dependencies or [],
    )


# ── The plan: columns ────────────────────────────────────────────────


class TestBoardPlanColumns:
    def test_five_columns_in_kanban_order_even_when_empty(self) -> None:
        plan = build_trello_board_plan(board_name="WS", tasks=[], story_text_by_id={})

        assert isinstance(plan, TrelloBoardPlan)
        assert [column.name for column in plan.columns] == [
            "Backlog",
            "To Do",
            "In Progress",
            "Review",
            "Done",
        ]
        assert all(column.cards == () for column in plan.columns)

    def test_each_card_lands_in_its_status_column(self) -> None:
        story = uuid4()
        tasks = [
            make_task("A", status=TaskStatus.TODO, story_id=story),
            make_task("B", status=TaskStatus.DONE, story_id=story),
            make_task("C", status=TaskStatus.TODO, story_id=story),
        ]

        plan = build_trello_board_plan(board_name="WS", tasks=tasks, story_text_by_id={})

        by_name = {column.name: column for column in plan.columns}
        assert [card.title for card in by_name["To Do"].cards] == ["A", "C"]
        assert [card.title for card in by_name["Done"].cards] == ["B"]
        assert [card.title for card in by_name["Backlog"].cards] == []

    def test_plan_name_is_the_board_name(self) -> None:
        plan = build_trello_board_plan(board_name="Export WS", tasks=[], story_text_by_id={})
        assert plan.name == "Export WS"


# ── The plan: cards ──────────────────────────────────────────────────


class TestBoardPlanCards:
    def test_card_carries_its_labels(self) -> None:
        task = make_task("T", labels=["backend", "api"])

        plan = build_trello_board_plan(board_name="WS", tasks=[task], story_text_by_id={})

        card = plan.columns[0].cards[0]
        assert card.labels == ("backend", "api")

    def test_card_description_keeps_the_task_description_first(self) -> None:
        task = make_task("T", description="Do the thing")

        plan = build_trello_board_plan(board_name="WS", tasks=[task], story_text_by_id={})

        assert plan.columns[0].cards[0].description.startswith("Do the thing")

    def test_description_carries_story_attribution_in_csv2trello_shape(self) -> None:
        story = uuid4()
        task = make_task("T", story_id=story)

        plan = build_trello_board_plan(
            board_name="WS",
            tasks=[task],
            story_text_by_id={story: "As a user, I want to log in"},
        )

        description = plan.columns[0].cards[0].description
        assert "\n---\n**Metadata:**" in description
        assert f"- User Story ID: `{story}`" in description
        assert "- User Story: _As a user, I want to log in_" in description

    def test_story_preview_truncates_at_100_characters_like_csv2trello(self) -> None:
        story = uuid4()
        long_story = "x" * 140
        task = make_task("T", story_id=story)

        plan = build_trello_board_plan(
            board_name="WS",
            tasks=[task],
            story_text_by_id={story: long_story},
        )

        description = plan.columns[0].cards[0].description
        expected_preview = long_story[:_STORY_PREVIEW_LIMIT] + "..."
        assert f"- User Story: _{expected_preview}_" in description

    def test_unknown_story_renders_no_attribution_lines(self) -> None:
        task = make_task("T", story_id=uuid4())

        plan = build_trello_board_plan(board_name="WS", tasks=[task], story_text_by_id={})

        description = plan.columns[0].cards[0].description
        assert "**Metadata:**" not in description


# ── The dependency rule (shared with the Markdown export) ────────────


class TestDependencyResolution:
    def test_resolves_a_dependency_by_task_id(self) -> None:
        referenced = make_task("Real title")
        index = build_dependency_title_index([(str(referenced.id), "Real title")])

        assert resolve_dependency(str(referenced.id), index) == "Real title"

    def test_resolves_a_dependency_by_casefolded_title(self) -> None:
        index = build_dependency_title_index([("id-1", "Set Up Database")])

        assert resolve_dependency("  set up database ", index) == "Set Up Database"

    def test_unresolvable_reference_renders_as_the_reference(self) -> None:
        index = build_dependency_title_index([])

        assert resolve_dependency("some vanished task", index) == "some vanished task"

    def test_resolution_covers_the_whole_export_not_one_column(self) -> None:
        """A dependency may point at a task sitting in another status column."""
        story = uuid4()
        referenced = make_task("Auth API", status=TaskStatus.DONE, story_id=story)
        dependent = make_task(
            "Use auth",
            status=TaskStatus.TODO,
            story_id=story,
            dependencies=[str(referenced.id)],
        )

        plan = build_trello_board_plan(
            board_name="WS",
            tasks=[referenced, dependent],
            story_text_by_id={},
        )

        by_name = {column.name: column for column in plan.columns}
        assert by_name["To Do"].cards[0].dependency_titles == ("Auth API",)
