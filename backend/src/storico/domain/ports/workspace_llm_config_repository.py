"""WorkspaceLLMConfigRepository port — defines the contract for workspace LLM config persistence."""

from __future__ import annotations

from abc import ABC, abstractmethod
from uuid import UUID

from storico.domain.entities.workspace_llm_config import WorkspaceLLMConfig


class WorkspaceLLMConfigRepository(ABC):
    """Repository port for WorkspaceLLMConfig entities."""

    @abstractmethod
    async def get(self, workspace_id: UUID) -> WorkspaceLLMConfig | None:
        """Retrieve the LLM config for a workspace, if any."""
        ...

    @abstractmethod
    async def upsert(self, config: WorkspaceLLMConfig) -> WorkspaceLLMConfig:
        """Create or update the LLM config for a workspace."""
        ...
