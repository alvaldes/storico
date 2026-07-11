"""Tests for SQLAlchemyUserRepository."""

from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from storico.domain.entities import DuplicateEntity, EntityNotFound, User
from storico.domain.entities.user_account import UserAccount
from storico.infrastructure.database.repositories import SQLAlchemyUserRepository


@pytest.mark.asyncio
async def test_save_and_find_by_id(db_session: AsyncSession) -> None:
    """Save a user and retrieve it by id."""
    repo = SQLAlchemyUserRepository(db_session)
    user = User(email="alice@example.com", name="Alice")

    saved = await repo.save(user)
    assert saved == user

    found = await repo.find_by_id(user.id)
    assert found is not None
    assert found.email == "alice@example.com"
    assert found.name == "Alice"


@pytest.mark.asyncio
async def test_find_by_id_returns_none(db_session: AsyncSession) -> None:
    """find_by_id returns None for a non-existent user."""
    repo = SQLAlchemyUserRepository(db_session)
    result = await repo.find_by_id(uuid4())
    assert result is None


@pytest.mark.asyncio
async def test_find_by_email(db_session: AsyncSession) -> None:
    """Find a user by their email address."""
    repo = SQLAlchemyUserRepository(db_session)
    user = User(email="bob@example.com", name="Bob")

    await repo.save(user)

    found = await repo.find_by_email("bob@example.com")
    assert found is not None
    assert found.id == user.id
    assert found.name == "Bob"

    missing = await repo.find_by_email("nobody@example.com")
    assert missing is None


@pytest.mark.asyncio
async def test_delete_raises_entity_not_found(db_session: AsyncSession) -> None:
    """delete raises EntityNotFound when the user does not exist."""
    repo = SQLAlchemyUserRepository(db_session)
    with pytest.raises(EntityNotFound) as exc:
        await repo.delete(uuid4())
    assert "User" in str(exc.value)


@pytest.mark.asyncio
async def test_duplicate_email_raises_duplicate_entity(db_session: AsyncSession) -> None:
    """Saving a user with a duplicate email raises DuplicateEntity."""
    repo = SQLAlchemyUserRepository(db_session)
    user1 = User(email="dup@example.com", name="First")
    await repo.save(user1)

    user2 = User(email="dup@example.com", name="Second")
    with pytest.raises(DuplicateEntity) as exc:
        await repo.save(user2)
    assert "email" in str(exc.value)


@pytest.mark.asyncio
async def test_find_by_auth(db_session: AsyncSession) -> None:
    """Find a user by OAuth provider and provider ID via user_accounts JOIN."""
    repo = SQLAlchemyUserRepository(db_session)
    user = User(email="test@test.com", name="Test")
    await repo.save(user)
    await repo.link_account(user.id, "google", "g-1")

    found = await repo.find_by_auth("google", "g-1")
    assert found is not None
    assert found.email == "test@test.com"

    not_found = await repo.find_by_auth("google", "nonexistent")
    assert not_found is None


@pytest.mark.asyncio
async def test_list_users(db_session: AsyncSession) -> None:
    """list returns all users."""
    repo = SQLAlchemyUserRepository(db_session)
    user1 = User(email="a@example.com", name="A")
    user2 = User(email="b@example.com", name="B")
    await repo.save(user1)
    await repo.save(user2)

    users = await repo.list()
    assert len(users) == 2
    emails = {u.email for u in users}
    assert emails == {"a@example.com", "b@example.com"}


@pytest.mark.asyncio
async def test_link_account_success(db_session: AsyncSession) -> None:
    """link_account creates a UserAccount row and returns it."""
    repo = SQLAlchemyUserRepository(db_session)
    user = User(email="link@example.com", name="Link")
    await repo.save(user)

    account = await repo.link_account(user.id, "github", "gh-link")
    assert isinstance(account, UserAccount)
    assert account.user_id == user.id
    assert account.provider == "github"
    assert account.provider_id == "gh-link"
    assert account.id is not None

    # Verify via find_by_auth
    found = await repo.find_by_auth("github", "gh-link")
    assert found is not None
    assert found.id == user.id


@pytest.mark.asyncio
async def test_link_account_duplicate(db_session: AsyncSession) -> None:
    """link_account raises DuplicateEntity on duplicate (provider, provider_id)."""
    repo = SQLAlchemyUserRepository(db_session)
    user1 = User(email="user1@example.com", name="User1")
    user2 = User(email="user2@example.com", name="User2")
    await repo.save(user1)
    await repo.save(user2)

    await repo.link_account(user1.id, "google", "dup-id")
    with pytest.raises(DuplicateEntity) as exc:
        await repo.link_account(user2.id, "google", "dup-id")
    assert "UserAccount" in str(exc.value)


@pytest.mark.asyncio
async def test_find_accounts(db_session: AsyncSession) -> None:
    """find_accounts returns all accounts for a user."""
    repo = SQLAlchemyUserRepository(db_session)
    user = User(email="multi@example.com", name="Multi")
    await repo.save(user)

    a1 = await repo.link_account(user.id, "google", "g-multi")
    a2 = await repo.link_account(user.id, "github", "gh-multi")

    accounts = await repo.find_accounts(user.id)
    assert len(accounts) == 2
    providers = {a.provider for a in accounts}
    assert providers == {"google", "github"}

    # Other user has no accounts
    other_accounts = await repo.find_accounts(uuid4())
    assert other_accounts == []
