from __future__ import annotations

from abc import ABC, abstractmethod
from uuid import UUID

from storico.domain.entities.user import User


class UserRepository(ABC):
    """Repository port for User entities."""

    @abstractmethod
    async def save(self, user: User) -> User:
        """Persist a user. Creates or updates as needed."""
        ...

    @abstractmethod
    async def find_by_id(self, user_id: UUID) -> User | None:
        """Find a user by their unique identifier."""
        ...

    @abstractmethod
    async def find_by_auth(self, provider: str, provider_id: str) -> User | None:
        """Find a user by their OAuth provider and provider-specific user ID."""
        ...

    @abstractmethod
    async def find_by_email(self, email: str) -> User | None:
        """Find a user by their email address."""
        ...

    @abstractmethod
    async def list(self) -> list[User]:
        """Return all users."""
        ...

    @abstractmethod
    async def delete(self, user_id: UUID) -> None:
        """Delete a user by their unique identifier."""
        ...
