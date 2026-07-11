from __future__ import annotations

from abc import ABC, abstractmethod
from uuid import UUID

from uuid import UUID

from storico.domain.entities.user import User
from storico.domain.entities.user_account import UserAccount


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
        """Find a user by their OAuth provider and provider-specific user ID
        via a JOIN on user_accounts."""
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

    @abstractmethod
    async def link_account(self, user_id: UUID, provider: str, provider_id: str) -> UserAccount:
        """Create a user_account row linking a provider to a user.
        Raises DuplicateEntity on (provider, provider_id) conflict."""
        ...

    @abstractmethod
    async def find_accounts(self, user_id: UUID) -> list[UserAccount]:
        """Return all user_account rows for a given user."""
        ...
