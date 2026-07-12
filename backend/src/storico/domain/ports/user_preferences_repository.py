"""UserPreferencesRepository — abstract port for user preference persistence."""

from __future__ import annotations

from abc import ABC, abstractmethod
from uuid import UUID

from storico.domain.entities.user_preferences import UserPreferences


class UserPreferencesRepository(ABC):
    """Repository port for UserPreferences entities."""

    @abstractmethod
    async def get(self, user_id: UUID) -> UserPreferences | None:
        """Return preferences for the given user, or None if not set."""
        ...

    @abstractmethod
    async def upsert(self, user_id: UUID, preferences: dict) -> UserPreferences:
        """Create or replace preferences for the given user.

        Returns the persisted ``UserPreferences`` (with updated_at).
        """
        ...
