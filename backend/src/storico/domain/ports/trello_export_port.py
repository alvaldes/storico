"""TrelloExportPort — the contract for turning a board plan into a Trello board."""

from __future__ import annotations

from abc import ABC, abstractmethod

from storico.domain.entities.trello_board import TrelloBoardPlan, TrelloBoardRef
from storico.domain.entities.workspace_trello_config import WorkspaceTrelloConfig


class TrelloExportPort(ABC):
    """Creates a Trello board from a plan, using a workspace's credentials.

    The port knows nothing about where the plan came from (which tasks, whose
    scope, which dependencies): the caller hands over an already-built
    ``TrelloBoardPlan`` and the workspace's decrypted ``WorkspaceTrelloConfig``,
    and gets back the identity of the board that now exists.

    The method is async because the export runs inside the API process's event
    loop (`asyncio.create_task`): a synchronous client must be offloaded, never
    awaited inline.
    """

    @abstractmethod
    async def create_board(
        self,
        plan: TrelloBoardPlan,
        credentials: WorkspaceTrelloConfig,
    ) -> TrelloBoardRef:
        """Create the board the plan describes and return its reference.

        Implementations create the board, then the columns in the plan's order,
        then each column's cards with their labels and dependency checklists.
        Raises a subclass of ``TrelloExportError`` on failure; errors raised
        after the board was created carry its ``TrelloBoardRef`` so a partial
        failure never hides a board the member can go look at.
        """
        ...
