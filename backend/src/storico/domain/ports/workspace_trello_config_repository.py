"""WorkspaceTrelloConfigRepository port — the contract for workspace Trello credential persistence."""

from __future__ import annotations

from abc import ABC, abstractmethod
from uuid import UUID

from storico.domain.entities.workspace_trello_config import WorkspaceTrelloConfig


class WorkspaceTrelloConfigRepository(ABC):
    """Repository port for WorkspaceTrelloConfig entities."""

    @abstractmethod
    async def get(self, workspace_id: UUID) -> WorkspaceTrelloConfig | None:
        """Retrieve the Trello config for a workspace, if any."""
        ...

    @abstractmethod
    async def upsert(self, config: WorkspaceTrelloConfig) -> WorkspaceTrelloConfig:
        """Create or update the Trello config for a workspace."""
        ...
