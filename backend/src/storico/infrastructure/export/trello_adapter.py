"""PyTrelloExportAdapter — creates Trello boards over the synchronous ``py-trello`` client.

This adapter implements ``TrelloExportPort`` and owns the four Trello facts
csv2trello measured before it (see ``odd/tasks/trello-export.md``):

1. **Rate window** — 300 requests per rolling 10 seconds
   (csv2trello ``core/trello_client.py:231-232``).
2. **Retry** — exponential backoff ``2**n``, at most 3 attempts, applied *only*
   to the retryable failure kind. csv2trello refuses to retry a "workspace
   full"/quota message (``core/trello_client.py:317-346``) and that refusal is
   part of the policy, not an oversight: a quota refusal is a human-action
   problem on the Trello account, and retrying cannot lift it.
3. **Labels are actually sent** — csv2trello's ``create_card`` accepts a
   ``labels`` argument and never sends it (``core/trello_client.py:436``; its
   docstring at ``:444`` says "not implemented yet"). That gap is *not*
   inherited: decision D6 promises labels, so this adapter creates one board
   label per distinct name (``Board.add_label``, with a deterministic color
   from a fixed palette) and passes the resulting label objects to
   ``List.add_card(labels=...)``, which py-trello does send as ``idLabels``.
4. **Auth mode** — the token is passed as py-trello's ``api_secret``, the same
   trick csv2trello uses (``core/trello_client.py:246-258``). py-trello has two
   auth modes: OAuth1 (``token=...``) or query-parameter auth
   (``api_secret=...`` with ``oauth=None``). csv2trello measured that OAuth1
   breaks behind Trello's CloudFront, so this adapter needs the same trick —
   with ``oauth=None``, ``fetch_json`` appends ``key`` and ``token`` as query
   parameters. Verified in ``TestDefaultClientFactory``.

Two deliberate departures from csv2trello, both forced by D5 (the export runs
inside the API process, on the event loop, via ``asyncio.create_task``):

- **Never blocking the loop.** py-trello is synchronous, so every client call
  goes through ``asyncio.to_thread`` and every wait — the rate window and the
  retry backoff — goes through ``asyncio.sleep``. csv2trello used ``time.sleep``
  and ``print`` freely because a CLI with one job owns its process; here a
  blocking wait would stall every request the API is serving, not just the
  export.
- **No credential in any message.** The original py-trello exception is never
  chained (``raise ... from None``) and never interpolated. Measured on the
  installed 0.20.1: ``Unauthorized`` and ``ResourceUnavailable`` interpolate the
  **base** request URL and the response text, and the credentials travel in a
  separate ``params`` dict (``trelloclient.py:243-253``), so today's messages
  are credential-free — this adapter first claimed otherwise, and the
  verification refuted it against the package. The policy stays anyway, for a
  reason that does not rest on that measurement: a chained cause reaches every
  traceback a logger prints without passing through anything this module
  controls, and the message shape is a library detail with no promise attached
  to it.

Known limitation, recorded rather than buried: py-trello 0.20.1 exposes **no
request timeout**. ``TrelloClient.__init__`` takes no timeout parameter and
``fetch_json`` calls ``http_service.request(...)`` without one, so a hung
request waits on ``requests``' default (no timeout). The only escape hatch is a
custom ``http_service`` wrapper — csv2trello uses exactly that hook for its
User-Agent header — which this adapter deliberately does not build yet; a stuck
export would hold one worker thread and its ``asyncio.create_task``, not the
event loop.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar

from trello import TrelloClient
from trello.exceptions import ResourceUnavailable, Unauthorized

from storico.domain.entities.exceptions import (
    TrelloBoardRefusedError,
    TrelloCardRefusedError,
    TrelloCredentialRejectedError,
    TrelloExportError,
    TrelloRateLimitExhaustedError,
    TrelloServiceUnavailableError,
)
from storico.domain.entities.trello_board import TrelloBoardPlan, TrelloBoardRef
from storico.domain.entities.workspace_trello_config import WorkspaceTrelloConfig
from storico.domain.ports.trello_export_port import TrelloExportPort

_T = TypeVar("_T")

# The measured Trello facts (csv2trello core/trello_client.py:231-232).
_MAX_REQUESTS_PER_WINDOW = 300
_RATE_LIMIT_WINDOW_SECONDS = 10.0

# At most 3 attempts, backing off 2**n between them (1s, then 2s).
_MAX_ATTEMPTS = 3

# Trello's label palette; the color is chosen by order of first appearance, so
# exporting the same plan twice produces the same board. Trello's palette is
# small, so two different labels can share a color — recorded in the ODD record
# as a limitation, not buried.
_LABEL_PALETTE = (
    "green",
    "yellow",
    "orange",
    "red",
    "purple",
    "blue",
    "sky",
    "lime",
    "pink",
    "black",
)

_DEPENDENCIES_CHECKLIST_TITLE = "Dependencies"


def _is_quota_refusal(exc: ResourceUnavailable) -> bool:
    """Whether a non-200 answer is a quota/refusal that retrying cannot fix.

    Mirrors csv2trello's measured classification (``core/trello_client.py:317-346``):
    a "workspace full" message, or any "limit"/"quota" message, is an account
    limit — never retried.
    """
    message = str(exc).lower()
    return (
        ("workspace" in message and "full" in message) or "limit" in message or "quota" in message
    )


class PyTrelloExportAdapter(TrelloExportPort):
    """Implements ``TrelloExportPort`` over the synchronous ``py-trello`` client.

    ``client_factory``, ``sleep_func`` and ``clock`` are injection seams for the
    tests: the default factory builds the real ``TrelloClient`` with the
    query-param auth trick, the default sleep is ``asyncio.sleep`` and the
    default clock is ``time.monotonic``.
    """

    def __init__(
        self,
        client_factory: Callable[[WorkspaceTrelloConfig], Any] | None = None,
        sleep_func: Callable[[float], Awaitable[None]] | None = None,
        clock: Callable[[], float] | None = None,
    ) -> None:
        self._client_factory = client_factory or self._build_client
        self._sleep = sleep_func or asyncio.sleep
        self._clock = clock or time.monotonic
        self._request_times: list[float] = []

    # -- TrelloExportPort ---------------------------------------------------

    async def create_board(
        self,
        plan: TrelloBoardPlan,
        credentials: WorkspaceTrelloConfig,
    ) -> TrelloBoardRef:
        client = self._client_factory(credentials)

        # The board first; a failure here has no reference to carry. The board
        # is created without Trello's default lists: the plan's columns are the
        # board's lists, and Trello's own defaults would pollute it.
        board = await self._call(
            client.add_board,
            refusal=TrelloBoardRefusedError,
            board_ref=None,
            args=(plan.name,),
            kwargs={"permission_level": "private", "default_lists": False},
        )
        board_ref = TrelloBoardRef(
            id=str(board.id),
            url=getattr(board, "url", "") or "",
        )

        # One board label per distinct name, in order of first appearance, so
        # the same plan always produces the same board (D6, sent — not
        # accepted-and-dropped like csv2trello's create_card).
        distinct_names: list[str] = []
        for column in plan.columns:
            for card in column.cards:
                for name in card.labels:
                    if name not in distinct_names:
                        distinct_names.append(name)
        label_objects: dict[str, Any] = {}
        for offset, name in enumerate(distinct_names):
            color = _LABEL_PALETTE[offset % len(_LABEL_PALETTE)]
            label_objects[name] = await self._call(
                board.add_label,
                refusal=TrelloCardRefusedError,
                board_ref=board_ref,
                args=(name, color),
            )

        # Columns in the plan's order, then each column's cards in its list.
        for position, column in enumerate(plan.columns, start=1):
            trello_list = await self._call(
                board.add_list,
                refusal=TrelloCardRefusedError,
                board_ref=board_ref,
                args=(column.name, position),
            )
            for card in column.cards:
                created = await self._call(
                    trello_list.add_card,
                    refusal=TrelloCardRefusedError,
                    board_ref=board_ref,
                    kwargs={
                        "name": card.title,
                        "desc": card.description,
                        "labels": [label_objects[name] for name in card.labels],
                    },
                )
                if card.dependency_titles:
                    await self._call(
                        created.add_checklist,
                        refusal=TrelloCardRefusedError,
                        board_ref=board_ref,
                        args=(_DEPENDENCIES_CHECKLIST_TITLE, list(card.dependency_titles)),
                    )

        return board_ref

    # -- plumbing -----------------------------------------------------------

    def _build_client(self, credentials: WorkspaceTrelloConfig) -> TrelloClient:
        """Build the py-trello client in csv2trello's measured auth mode.

        The token is passed as ``api_secret`` — *not* as ``token`` — so
        ``oauth`` stays ``None`` and ``fetch_json`` sends ``key`` and ``token``
        as query parameters (csv2trello ``core/trello_client.py:246-258``):
        py-trello's OAuth1 mode is what misbehaves behind Trello's CloudFront.
        """
        return TrelloClient(
            api_key=credentials.api_key or "",
            api_secret=credentials.token or "",
        )

    async def _call(
        self,
        fn: Callable[..., _T],
        *,
        refusal: type[TrelloExportError],
        board_ref: TrelloBoardRef | None,
        args: tuple = (),
        kwargs: dict[str, Any] | None = None,
    ) -> _T:
        """Run one synchronous client call, off the loop, with the full policy.

        Rate window before every attempt (each retry is a real request and
        counts against the window), bounded exponential backoff on the
        retryable failure kind, and typed non-retryable errors otherwise. The
        ``refusal`` class says what a quota refusal maps to from this call
        site: ``TrelloBoardRefusedError`` while creating the board,
        ``TrelloCardRefusedError`` for everything after it exists — which is
        how the board reference survives a partial failure.
        """
        kwargs = kwargs or {}
        attempt = 0
        while True:
            await self._respect_rate_window()
            try:
                # py-trello is synchronous; D5 runs this inside the API's event
                # loop, so the call must be offloaded, never awaited inline.
                return await asyncio.to_thread(fn, *args, **kwargs)
            except Unauthorized:
                # Non-retryable: the credential is wrong or revoked. The cause
                # is deliberately dropped (`from None`): py-trello's message
                # embeds the request URL, which carries the token.
                raise TrelloCredentialRejectedError(board_ref=board_ref) from None
            except ResourceUnavailable as exc:
                if _is_quota_refusal(exc):
                    # csv2trello's measured refusal: quota messages are never
                    # retried (core/trello_client.py:317-346).
                    raise refusal(board_ref=board_ref) from None
                attempt += 1
                if attempt >= _MAX_ATTEMPTS:
                    raise TrelloRateLimitExhaustedError(board_ref=board_ref) from None
                await self._sleep(2.0 ** (attempt - 1))
            except Exception as exc:
                # Anything else (connection errors, unexpected SDK failures) is
                # not retried — matching csv2trello — and its message is not
                # trusted to be credential-free.
                raise TrelloServiceUnavailableError(
                    f"Trello failed unexpectedly during the export ({type(exc).__name__})",
                    board_ref=board_ref,
                ) from None

    async def _respect_rate_window(self) -> None:
        """Hold back until the rolling 10-second window has room.

        The wait is ``asyncio.sleep``, never ``time.sleep``: csv2trello could
        block its whole process because it is a CLI with one job; this wait
        happens on the API's event loop and must not stall the requests it is
        serving.
        """
        now = self._clock()
        self._request_times = [
            stamp for stamp in self._request_times if now - stamp < _RATE_LIMIT_WINDOW_SECONDS
        ]
        if len(self._request_times) >= _MAX_REQUESTS_PER_WINDOW:
            wait = _RATE_LIMIT_WINDOW_SECONDS - (now - self._request_times[0])
            if wait > 0:
                await self._sleep(wait)
        self._request_times.append(self._clock())
