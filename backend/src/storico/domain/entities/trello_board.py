"""Trello board plan value objects — what an export asks Trello to build.

These dataclasses describe a whole board in one immutable value: the columns in
the order they must appear, and the cards each column holds. They carry nothing
about Storico's database, scope rules or task model — the caller (the plan
builder) resolves dependencies and labels into plain titles and names, and the
adapter turns the plan into API calls without knowing where it came from.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class TrelloCard:
    """One card to create, with everything it needs resolved already.

    ``labels`` are label *names*; the adapter creates one board label per
    distinct name and attaches the board's label objects to the card.
    ``dependency_titles`` are already-resolved dependency titles (the same
    resolution rules the Markdown export applies); the adapter turns each one
    into a checklist item.
    """

    title: str
    description: str = ""
    labels: tuple[str, ...] = ()
    dependency_titles: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class TrelloColumn:
    """One board list, in the position the plan gives it."""

    name: str
    cards: tuple[TrelloCard, ...] = ()


@dataclass(frozen=True, slots=True)
class TrelloBoardPlan:
    """A whole board: its name and its columns, in order."""

    name: str
    columns: tuple[TrelloColumn, ...] = ()


@dataclass(frozen=True, slots=True)
class TrelloBoardRef:
    """The identity of a board that now exists on Trello.

    Created after ``create_board`` succeeds; also carried by the export errors
    raised after the board exists, so a partial failure never hides a board the
    member can go look at.
    """

    id: str
    url: str
