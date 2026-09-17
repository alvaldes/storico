"""CustomProviderRepository port — the contract for workspace custom providers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from uuid import UUID

from storico.domain.entities.custom_provider import CustomProvider


class CustomProviderRepository(ABC):
    """Repository port for workspace-scoped custom provider names.

    Every method is scoped by ``workspace_id`` or by a provider id whose row must
    be resolved before it can be trusted, so a caller can never reach another
    workspace's providers by guessing an id.
    """

    @abstractmethod
    async def list_by_workspace(self, workspace_id: UUID) -> list[CustomProvider]:
        """List the workspace's custom providers, ordered by name."""
        ...

    @abstractmethod
    async def get(self, provider_id: UUID) -> CustomProvider | None:
        """Retrieve one custom provider by id, regardless of workspace."""
        ...

    @abstractmethod
    async def find_by_workspace_and_name(
        self, workspace_id: UUID, name: str
    ) -> CustomProvider | None:
        """Retrieve the workspace's custom provider with this exact name, if any."""
        ...

    @abstractmethod
    async def create(self, provider: CustomProvider) -> CustomProvider:
        """Persist a new custom provider."""
        ...

    @abstractmethod
    async def rename(self, provider_id: UUID, name: str) -> CustomProvider | None:
        """Rename one custom provider, returning the updated row (or ``None``)."""
        ...
