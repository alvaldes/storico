"""Tests for SQLAlchemyUserRepository."""

from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from storico.domain.entities import DuplicateEntity, EntityNotFound, User
from storico.infrastructure.database.repositories import SQLAlchemyUserRepository


@pytest.mark.asyncio
async def test_save_and_find_by_id(db_session: AsyncSession) -> None:
    """Save a user and retrieve it by id."""
    repo = SQLAlchemyUserRepository(db_session)
    user = User(email="alice@example.com", name="Alice", auth_provider="google", auth_id="g001")

    saved = await repo.save(user)
    assert saved == user

    found = await repo.find_by_id(user.id)
    assert found is not None
    assert found.email == "alice@example.com"
    assert found.name == "Alice"
    assert found.auth_provider == "google"
    assert found.auth_id == "g001"


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
    user = User(email="bob@example.com", name="Bob", auth_provider="github", auth_id="g001")

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
    user1 = User(email="dup@example.com", name="First", auth_provider="google", auth_id="g001")
    await repo.save(user1)

    user2 = User(email="dup@example.com", name="Second", auth_provider="github", auth_id="g002")
    with pytest.raises(DuplicateEntity) as exc:
        await repo.save(user2)
    assert "email" in str(exc.value)


@pytest.mark.asyncio
async def test_find_by_auth(db_session: AsyncSession) -> None:
    """Find a user by OAuth provider and provider ID."""
    repo = SQLAlchemyUserRepository(db_session)
    user = User(
        email="test@test.com",
        name="Test",
        auth_provider="google",
        auth_id="g-1",
    )
    await repo.save(user)

    found = await repo.find_by_auth("google", "g-1")
    assert found is not None
    assert found.email == "test@test.com"
    assert found.auth_provider == "google"
    assert found.auth_id == "g-1"

    not_found = await repo.find_by_auth("google", "nonexistent")
    assert not_found is None


@pytest.mark.asyncio
async def test_list_users(db_session: AsyncSession) -> None:
    """list returns all users."""
    repo = SQLAlchemyUserRepository(db_session)
    user1 = User(email="a@example.com", name="A", auth_provider="google", auth_id="a1")
    user2 = User(email="b@example.com", name="B", auth_provider="github", auth_id="b1")
    await repo.save(user1)
    await repo.save(user2)

    users = await repo.list()
    assert len(users) == 2
    emails = {u.email for u in users}
    assert emails == {"a@example.com", "b@example.com"}
