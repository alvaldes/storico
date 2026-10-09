"""Unit tests for PyTrelloExportAdapter.

Every test runs against an injected fake client, so nothing touches the network.
The fakes record the calls they receive in a shared event list together with the
sleeps the adapter performs, which is what makes the ordering assertions
(column order, rate window waiting before the first request, retry backoff)
possible without real time passing.
"""

from __future__ import annotations

import logging
from types import SimpleNamespace
from uuid import uuid4

import pytest
from trello import TrelloClient
from trello.exceptions import ResourceUnavailable, Unauthorized

from storico.domain.entities import (
    TrelloBoardPlan,
    TrelloBoardRefusedError,
    TrelloCard,
    TrelloCardRefusedError,
    TrelloColumn,
    TrelloCredentialRejectedError,
    TrelloRateLimitExhaustedError,
    TrelloServiceUnavailableError,
)
from storico.domain.entities.workspace_trello_config import WorkspaceTrelloConfig
from storico.domain.ports import TrelloExportPort
from storico.infrastructure.export.trello_adapter import PyTrelloExportAdapter

# Sentinels that must never appear in an exception message or a log line.
API_KEY = "sentinel-api-key-ABC123"
TOKEN = "sentinel-token-XYZ789"


def _unavailable(message: str) -> ResourceUnavailable:
    """Build the py-trello exception the client raises for any non-200 response."""
    return ResourceUnavailable(message, SimpleNamespace(status_code=429))


def _unauthorized(message: str) -> Unauthorized:
    return Unauthorized(message, SimpleNamespace(status_code=401))


def _credentials() -> WorkspaceTrelloConfig:
    return WorkspaceTrelloConfig(workspace_id=uuid4(), api_key=API_KEY, token=TOKEN)


def _card(
    title: str,
    labels: tuple[str, ...] = (),
    deps: tuple[str, ...] = (),
) -> TrelloCard:
    return TrelloCard(
        title=title,
        description=f"description of {title}",
        labels=labels,
        dependency_titles=deps,
    )


class FakeClock:
    """Controllable monotonic clock; the fake sleep advances it."""

    def __init__(self) -> None:
        self.now = 1_000.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


class FakeLabel:
    def __init__(self, label_id: str, name: str, color: str) -> None:
        self.id = label_id
        self.name = name
        self.color = color


class FakeChecklist:
    def __init__(self, title: str, items: list[str]) -> None:
        self.title = title
        self.items = list(items)


class FakeCard:
    def __init__(
        self,
        card_id: str,
        name: str,
        desc: str | None,
        labels: list[FakeLabel],
    ) -> None:
        self.id = card_id
        self.name = name
        self.description = desc
        self.labels = list(labels)
        self.checklists: list[FakeChecklist] = []

    def add_checklist(self, title: str, items: list[str], itemstates=None) -> FakeChecklist:
        checklist = FakeChecklist(title, items)
        self.checklists.append(checklist)
        return checklist


class FakeList:
    def __init__(self, list_id: str, name: str, events: list) -> None:
        self.id = list_id
        self.name = name
        self.cards: list[FakeCard] = []
        self.add_card_failures: list = []
        self._events = events

    def add_card(self, name: str = "", desc=None, labels=None, position=None) -> FakeCard:
        self._events.append(("add_card", self.name, name))
        if self.add_card_failures:
            outcome = self.add_card_failures.pop(0)
            if isinstance(outcome, BaseException):
                raise outcome
        card = FakeCard(
            f"card-{len(self.cards) + 1}",
            name,
            desc,
            list(labels or []),
        )
        self.cards.append(card)
        return card


class FakeBoard:
    def __init__(self, board_id: str = "board-1", url: str = "https://trello.com/b/board-1"):
        self.id = board_id
        self.url = url
        self.lists: list[FakeList] = []
        self.labels: list[FakeLabel] = []
        self.add_list_failures: list = []
        self.add_label_failures: list = []
        self._events: list = []

    def add_list(self, name: str, pos=None) -> FakeList:
        self._events.append(("add_list", name, pos))
        if self.add_list_failures:
            outcome = self.add_list_failures.pop(0)
            if isinstance(outcome, BaseException):
                raise outcome
        trello_list = FakeList(f"list-{len(self.lists) + 1}", name, self._events)
        self.lists.append(trello_list)
        return trello_list

    def add_label(self, name: str, color: str) -> FakeLabel:
        self._events.append(("add_label", name, color))
        if self.add_label_failures:
            outcome = self.add_label_failures.pop(0)
            if isinstance(outcome, BaseException):
                raise outcome
        label = FakeLabel(f"label-{len(self.labels) + 1}", name, color)
        self.labels.append(label)
        return label


class FakeClient:
    def __init__(self, board: FakeBoard | None = None) -> None:
        self.board = board or FakeBoard()
        self.events: list = self.board._events
        self.add_board_failures: list = []
        self.received_credentials: list[WorkspaceTrelloConfig] = []

    def add_board(
        self,
        board_name: str,
        source_board=None,
        organization_id=None,
        permission_level: str = "private",
        default_lists: bool = True,
    ) -> FakeBoard:
        self.events.append(("add_board", board_name, default_lists))
        self.received_credentials_count = getattr(self, "received_credentials_count", 0) + 1
        if self.add_board_failures:
            outcome = self.add_board_failures.pop(0)
            if isinstance(outcome, BaseException):
                raise outcome
        return self.board


def _adapter(client: FakeClient, clock: FakeClock) -> tuple[PyTrelloExportAdapter, list]:
    """Build the adapter over ``client`` with a fake clock and fake sleep.

    The fake sleep records into the client's shared event list (so sleeps and
    client calls interleave in one timeline) and advances the fake clock, the
    way real waiting would advance real time.
    """
    events = client.events
    received: list[WorkspaceTrelloConfig] = []

    async def fake_sleep(seconds: float) -> None:
        events.append(("sleep", seconds))
        clock.advance(seconds)

    def factory(credentials: WorkspaceTrelloConfig) -> FakeClient:
        received.append(credentials)
        return client

    adapter = PyTrelloExportAdapter(
        client_factory=factory,
        sleep_func=fake_sleep,
        clock=clock,
    )
    adapter._test_received_credentials = received  # noqa: SLF001 - test evidence
    return adapter, events


def _three_column_plan() -> TrelloBoardPlan:
    return TrelloBoardPlan(
        name="Workspace board",
        columns=(
            TrelloColumn(name="Backlog", cards=(_card("Task A"),)),
            TrelloColumn(name="To Do", cards=(_card("Task B"), _card("Task C"))),
            TrelloColumn(name="Done", cards=(_card("Task D"),)),
        ),
    )


@pytest.mark.unit
class TestBoardStructure:
    async def test_columns_are_created_in_plan_order(self):
        client = FakeClient()
        clock = FakeClock()
        adapter, _ = _adapter(client, clock)

        await adapter.create_board(_three_column_plan(), _credentials())

        list_events = [event for event in client.events if event[0] == "add_list"]
        assert [event[1] for event in list_events] == ["Backlog", "To Do", "Done"]

    async def test_cards_land_in_their_own_column(self):
        client = FakeClient()
        clock = FakeClock()
        adapter, _ = _adapter(client, clock)

        await adapter.create_board(_three_column_plan(), _credentials())

        backlog = client.board.lists[0]
        to_do = client.board.lists[1]
        done = client.board.lists[2]
        assert [card.name for card in backlog.cards] == ["Task A"]
        assert [card.name for card in to_do.cards] == ["Task B", "Task C"]
        assert [card.name for card in done.cards] == ["Task D"]

    async def test_card_description_is_sent(self):
        client = FakeClient()
        clock = FakeClock()
        adapter, _ = _adapter(client, clock)

        await adapter.create_board(_three_column_plan(), _credentials())

        created = client.board.lists[0].cards[0]
        assert created.description == "description of Task A"

    async def test_board_is_created_without_trello_default_lists(self):
        client = FakeClient()
        clock = FakeClock()
        adapter, _ = _adapter(client, clock)

        await adapter.create_board(_three_column_plan(), _credentials())

        add_board_events = [event for event in client.events if event[0] == "add_board"]
        assert add_board_events == [("add_board", "Workspace board", False)]

    async def test_adapter_satisfies_the_port(self):
        client = FakeClient()
        clock = FakeClock()
        adapter, _ = _adapter(client, clock)

        assert isinstance(adapter, TrelloExportPort)

    async def test_credentials_reach_the_client_factory(self):
        client = FakeClient()
        clock = FakeClock()
        adapter, _ = _adapter(client, clock)
        credentials = _credentials()

        await adapter.create_board(_three_column_plan(), credentials)

        assert adapter._test_received_credentials == [credentials]  # noqa: SLF001


@pytest.mark.unit
class TestLabels:
    async def test_one_board_label_per_distinct_name(self):
        plan = TrelloBoardPlan(
            name="Workspace board",
            columns=(
                TrelloColumn(
                    name="Backlog",
                    cards=(
                        _card("Task A", labels=("backend", "api")),
                        _card("Task B", labels=("backend",)),
                    ),
                ),
                TrelloColumn(
                    name="To Do",
                    cards=(_card("Task C", labels=("ui/ux",)),),
                ),
            ),
        )
        client = FakeClient()
        clock = FakeClock()
        adapter, _ = _adapter(client, clock)

        await adapter.create_board(plan, _credentials())

        label_events = [event for event in client.events if event[0] == "add_label"]
        assert [event[1] for event in label_events] == ["backend", "api", "ui/ux"]

    async def test_each_card_gets_its_own_labels_attached(self):
        plan = TrelloBoardPlan(
            name="Workspace board",
            columns=(
                TrelloColumn(
                    name="Backlog",
                    cards=(
                        _card("Task A", labels=("backend", "api")),
                        _card("Task B", labels=("backend",)),
                    ),
                ),
                TrelloColumn(
                    name="To Do",
                    cards=(_card("Task C", labels=("ui/ux",)),),
                ),
            ),
        )
        client = FakeClient()
        clock = FakeClock()
        adapter, _ = _adapter(client, clock)

        await adapter.create_board(plan, _credentials())

        board_labels = {label.name: label for label in client.board.labels}
        backlog_cards = client.board.lists[0].cards
        to_do_cards = client.board.lists[1].cards
        assert [label.name for label in backlog_cards[0].labels] == ["backend", "api"]
        assert [label.name for label in backlog_cards[1].labels] == ["backend"]
        assert [label.name for label in to_do_cards[0].labels] == ["ui/ux"]
        # The attached labels are the board labels that were created, not new ones.
        assert backlog_cards[0].labels[0] is board_labels["backend"]
        assert backlog_cards[0].labels[1] is board_labels["api"]

    async def test_label_colors_are_deterministic_from_the_palette(self):
        plan = TrelloBoardPlan(
            name="Workspace board",
            columns=(
                TrelloColumn(
                    name="Backlog",
                    cards=(
                        _card("Task A", labels=("backend", "api")),
                        _card("Task B", labels=("backend",)),
                    ),
                ),
            ),
        )
        client = FakeClient()
        clock = FakeClock()
        adapter, _ = _adapter(client, clock)

        await adapter.create_board(plan, _credentials())

        colors = [(label.name, label.color) for label in client.board.labels]
        assert colors[0] == ("backend", colors[0][1])
        assert colors[1] == ("api", colors[1][1])
        assert colors[0][1] != colors[1][1]
        # Exporting the same plan again picks the same colors.
        client2 = FakeClient()
        adapter2, _ = _adapter(client2, FakeClock())
        await adapter2.create_board(plan, _credentials())
        colors2 = [(label.name, label.color) for label in client2.board.labels]
        assert colors2 == colors


@pytest.mark.unit
class TestDependencyChecklists:
    async def test_checklist_items_carry_the_resolved_titles(self):
        plan = TrelloBoardPlan(
            name="Workspace board",
            columns=(
                TrelloColumn(
                    name="Backlog",
                    cards=(
                        _card("Task A", deps=("Task B", "Task C")),
                        _card("Task B"),
                    ),
                ),
            ),
        )
        client = FakeClient()
        clock = FakeClock()
        adapter, _ = _adapter(client, clock)

        await adapter.create_board(plan, _credentials())

        task_a = client.board.lists[0].cards[0]
        task_b = client.board.lists[0].cards[1]
        assert len(task_a.checklists) == 1
        assert task_a.checklists[0].items == ["Task B", "Task C"]
        assert task_b.checklists == []

    async def test_a_card_without_dependencies_gets_no_checklist(self):
        plan = TrelloBoardPlan(
            name="Workspace board",
            columns=(TrelloColumn(name="Backlog", cards=(_card("Task A"),)),),
        )
        client = FakeClient()
        clock = FakeClock()
        adapter, _ = _adapter(client, clock)

        await adapter.create_board(plan, _credentials())

        assert client.board.lists[0].cards[0].checklists == []


@pytest.mark.unit
class TestRetryPolicy:
    async def test_retryable_failure_is_retried_with_exponential_backoff(self):
        client = FakeClient()
        clock = FakeClock()
        adapter, _ = _adapter(client, clock)
        plan = TrelloBoardPlan(
            name="Workspace board",
            columns=(TrelloColumn(name="Backlog", cards=(_card("Task A"),)),),
        )
        # Arm the single list after it exists: its first card fails twice with
        # a transient error before succeeding.
        original_add_list = client.board.add_list

        def add_list_and_arm(name, pos=None):
            trello_list = original_add_list(name, pos)
            trello_list.add_card_failures = [
                _unavailable("temporarily unavailable"),
                _unavailable("temporarily unavailable"),
            ]
            return trello_list

        client.board.add_list = add_list_and_arm  # type: ignore[method-assign]

        ref = await adapter.create_board(plan, _credentials())

        add_card_events = [event for event in client.events if event[0] == "add_card"]
        assert len(add_card_events) == 3  # 1 card + 2 failed attempts
        sleeps = [event[1] for event in client.events if event[0] == "sleep"]
        assert sleeps == [1.0, 2.0]  # 2**0, 2**1
        assert ref.id == "board-1"
        assert [card.name for card in client.board.lists[0].cards] == ["Task A"]

    async def test_retries_are_exhausted_into_a_rate_limit_error(self):
        client = FakeClient()
        clock = FakeClock()
        adapter, _ = _adapter(client, clock)
        original_add_list = client.board.add_list

        def add_list_and_arm(name, pos=None):
            trello_list = original_add_list(name, pos)
            trello_list.add_card_failures = [
                _unavailable("temporarily unavailable") for _ in range(10)
            ]
            return trello_list

        client.board.add_list = add_list_and_arm  # type: ignore[method-assign]

        with pytest.raises(TrelloRateLimitExhaustedError) as exc_info:
            await adapter.create_board(_three_column_plan(), _credentials())

        add_card_events = [event for event in client.events if event[0] == "add_card"]
        assert len(add_card_events) == 3  # at most 3 attempts
        sleeps = [event[1] for event in client.events if event[0] == "sleep"]
        assert sleeps == [1.0, 2.0]
        # The board exists, so the failure must carry its reference.
        assert exc_info.value.board_ref is not None
        assert exc_info.value.board_ref.id == "board-1"
        assert exc_info.value.board_ref.url == "https://trello.com/b/board-1"

    async def test_credential_rejection_is_never_retried(self):
        client = FakeClient()
        clock = FakeClock()
        adapter, _ = _adapter(client, clock)
        client.add_board_failures = [
            _unauthorized(
                "Invalid credentials at https://api.trello.com/1/boards"
                f"?key={API_KEY}&token={TOKEN}"
            )
        ]

        with pytest.raises(TrelloCredentialRejectedError):
            await adapter.create_board(_three_column_plan(), _credentials())

        assert [event for event in client.events if event[0] == "add_board"] == [
            ("add_board", "Workspace board", False)
        ]
        assert [event for event in client.events if event[0] == "sleep"] == []

    @pytest.mark.parametrize(
        "message",
        [
            "your workspace is full",
            "board limit reached for this account",
            "quota exceeded for this organization",
        ],
    )
    async def test_quota_refusal_at_board_stage_is_never_retried(self, message: str):
        client = FakeClient()
        clock = FakeClock()
        adapter, _ = _adapter(client, clock)
        client.add_board_failures = [_unavailable(message)]

        with pytest.raises(TrelloBoardRefusedError) as exc_info:
            await adapter.create_board(_three_column_plan(), _credentials())

        assert [event for event in client.events if event[0] == "add_board"] == [
            ("add_board", "Workspace board", False)
        ]
        assert [event for event in client.events if event[0] == "sleep"] == []
        # The board never existed, so there is no reference to carry.
        assert exc_info.value.board_ref is None

    async def test_generic_failure_is_not_retried(self):
        client = FakeClient()
        clock = FakeClock()
        adapter, _ = _adapter(client, clock)

        def broken_add_board(*args, **kwargs):
            raise RuntimeError("connection reset")

        client.add_board = broken_add_board  # type: ignore[method-assign]

        with pytest.raises(TrelloServiceUnavailableError):
            await adapter.create_board(_three_column_plan(), _credentials())

        assert [event for event in client.events if event[0] == "sleep"] == []


@pytest.mark.unit
class TestRateWindow:
    async def test_the_window_waits_instead_of_firing(self):
        client = FakeClient()
        clock = FakeClock()
        adapter, events = _adapter(client, clock)
        # The window is already full: 300 requests within the last second.
        adapter._request_times = [clock.now - 1.0] * 300  # noqa: SLF001

        await adapter.create_board(_three_column_plan(), _credentials())

        assert events[0] == ("sleep", pytest.approx(9.0))
        assert events[1][0] == "add_board"

    async def test_a_window_with_room_never_waits(self):
        client = FakeClient()
        clock = FakeClock()
        adapter, events = _adapter(client, clock)

        await adapter.create_board(_three_column_plan(), _credentials())

        assert [event for event in events if event[0] == "sleep"] == []


@pytest.mark.unit
class TestPartialFailure:
    async def test_failure_after_the_board_carries_the_board_reference(self):
        client = FakeClient()
        clock = FakeClock()
        adapter, _ = _adapter(client, clock)
        original_add_list = client.board.add_list

        def add_list_and_arm(name, pos=None):
            trello_list = original_add_list(name, pos)
            if name == "To Do":
                trello_list.add_card_failures = [_unavailable("your workspace is full")]
            return trello_list

        client.board.add_list = add_list_and_arm  # type: ignore[method-assign]

        with pytest.raises(TrelloCardRefusedError) as exc_info:
            await adapter.create_board(_three_column_plan(), _credentials())

        board_ref = exc_info.value.board_ref
        assert board_ref is not None
        assert board_ref.id == "board-1"
        assert board_ref.url == "https://trello.com/b/board-1"
        # The half-built board is real: the first column's card was created.
        assert [card.name for card in client.board.lists[0].cards] == ["Task A"]

    async def test_failure_during_list_creation_carries_the_board_reference(self):
        client = FakeClient()
        clock = FakeClock()
        adapter, _ = _adapter(client, clock)
        client.board.add_list_failures = [_unavailable("quota exceeded")]

        with pytest.raises(TrelloCardRefusedError) as exc_info:
            await adapter.create_board(_three_column_plan(), _credentials())

        assert exc_info.value.board_ref is not None
        assert exc_info.value.board_ref.id == "board-1"


@pytest.mark.unit
class TestCredentialHygiene:
    async def test_no_credential_reaches_a_message_or_a_log_line(self, caplog):
        scenarios = []

        # Credential rejection.
        client = FakeClient()
        clock = FakeClock()
        adapter, _ = _adapter(client, clock)
        client.add_board_failures = [
            _unauthorized(
                "Invalid credentials at https://api.trello.com/1/boards"
                f"?key={API_KEY}&token={TOKEN}"
            )
        ]
        scenarios.append((adapter, client))

        # Quota refusal after the board exists.
        client2 = FakeClient()
        clock2 = FakeClock()
        adapter2, _ = _adapter(client2, clock2)
        original_add_list = client2.board.add_list

        def add_list_and_arm(name, pos=None):
            trello_list = original_add_list(name, pos)
            trello_list.add_card_failures = [_unavailable("your workspace is full")]
            return trello_list

        client2.board.add_list = add_list_and_arm  # type: ignore[method-assign]
        scenarios.append((adapter2, client2))

        # Retry exhaustion after the board exists.
        client3 = FakeClient()
        clock3 = FakeClock()
        adapter3, _ = _adapter(client3, clock3)
        original_add_list3 = client3.board.add_list

        def add_list_and_arm3(name, pos=None):
            trello_list = original_add_list3(name, pos)
            trello_list.add_card_failures = [
                _unavailable("temporarily unavailable") for _ in range(10)
            ]
            return trello_list

        client3.board.add_list = add_list_and_arm3  # type: ignore[method-assign]
        scenarios.append((adapter3, client3))

        # Generic service failure after the board exists.
        client4 = FakeClient()
        clock4 = FakeClock()
        adapter4, _ = _adapter(client4, clock4)
        original_add_list4 = client4.board.add_list

        def add_list_and_arm4(name, pos=None):
            trello_list = original_add_list4(name, pos)

            def broken_add_card(*args, **kwargs):
                raise RuntimeError(f"connection reset while sending {TOKEN}")

            trello_list.add_card = broken_add_card  # type: ignore[method-assign]
            return trello_list

        client4.board.add_list = add_list_and_arm4  # type: ignore[method-assign]
        scenarios.append((adapter4, client4))

        with caplog.at_level(logging.DEBUG):
            raised = []
            for adapter_under_test, client_under_test in scenarios:
                with pytest.raises(Exception) as exc_info:
                    await adapter_under_test.create_board(_three_column_plan(), _credentials())
                raised.append(exc_info.value)

        blob = " ".join(str(exc) for exc in raised)
        blob += " " + " ".join(record.getMessage() for record in caplog.records)
        blob += " " + " ".join(repr(exc) for exc in raised)
        assert API_KEY not in blob
        assert TOKEN not in blob

        # The blob above only sees ``str`` and ``repr``. A cause would reach a
        # traceback without passing through either, so the policy is asserted
        # directly: flipping ``from None`` to ``from exc`` leaves the blob clean
        # and still hands the token to whatever logs the next traceback.
        assert all(exc.__cause__ is None for exc in raised)
        assert all(exc.__suppress_context__ for exc in raised)


@pytest.mark.unit
class TestDefaultClientFactory:
    def test_token_is_passed_as_api_secret_to_force_query_param_auth(self):
        adapter = PyTrelloExportAdapter()

        client = adapter._build_client(_credentials())  # noqa: SLF001

        assert isinstance(client, TrelloClient)
        # oauth stays None: fetch_json then sends key and token as query params,
        # which is the auth mode csv2trello measured to work behind CloudFront.
        assert client.oauth is None
        assert client.api_key == API_KEY
        assert client.api_secret == TOKEN
