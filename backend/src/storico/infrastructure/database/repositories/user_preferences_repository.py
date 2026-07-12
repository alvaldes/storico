"""SQLAlchemy implementation of the UserPreferencesRepository port."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from storico.domain.entities.user_preferences import UserPreferences
from storico.domain.ports.user_preferences_repository import UserPreferencesRepository
from storico.infrastructure.database.models.user_preferences import (
    UserPreferencesModel,
)


class SQLAlchemyUserPreferencesRepository(UserPreferencesRepository):
    """Repository implementation for UserPreferences using SQLAlchemy async sessions."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, user_id: UUID) -> UserPreferences | None:
        result = await self._session.get(UserPreferencesModel, user_id)
        if result is None:
            return None
        return self._to_domain(result)

    async def upsert(self, user_id: UUID, preferences: dict) -> UserPreferences:
        now = datetime.now(UTC)
        existing = await self._session.get(UserPreferencesModel, user_id)

        if existing:
            existing.preferences = preferences
            existing.updated_at = now
        else:
            self._session.add(
                UserPreferencesModel(
                    user_id=user_id,
                    preferences=preferences,
                    updated_at=now,
                )
            )

        await self._session.commit()
        return UserPreferences(
            user_id=user_id,
            preferences=preferences,
            updated_at=now,
        )

    def _to_domain(self, model: UserPreferencesModel) -> UserPreferences:
        return UserPreferences(
            user_id=model.user_id,
            preferences=model.preferences,
            updated_at=model.updated_at,
        )
