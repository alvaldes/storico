"""WorkspacePromptRepository port — defines the contract for workspace prompt persistence."""

from __future__ import annotations

from abc import ABC, abstractmethod
from uuid import UUID

from storico.domain.entities.workspace_prompt import WorkspacePrompt


class WorkspacePromptRepository(ABC):
    """Repository port for WorkspacePrompt entities."""

    @abstractmethod
    async def get(self, workspace_id: UUID) -> WorkspacePrompt | None:
        """Retrieve the prompt config for a workspace, if any."""
        ...

    @abstractmethod
    async def upsert(self, prompt: WorkspacePrompt) -> WorkspacePrompt:
        """Create or update the prompt config for a workspace."""
        ...
