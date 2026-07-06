"""SQLAlchemy implementation of the UserRepository port."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from storico.domain.entities import DuplicateEntity, EntityNotFound, RepositoryError, User
from storico.domain.ports import UserRepository
from storico.infrastructure.database.models import UserModel


class SQLAlchemyUserRepository(UserRepository):
    """Repository implementation for User entities using SQLAlchemy async sessions."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save(self, user: User) -> User:
        try:
            existing = await self._session.get(UserModel, user.id)
            if existing:
                for key, value in self._to_orm_kwargs(user).items():
                    setattr(existing, key, value)
            else:
                self._session.add(UserModel(**self._to_orm_kwargs(user)))
            await self._session.commit()
            return user
        except IntegrityError as e:
            await self._session.rollback()
            if "email" in str(e.orig):
                raise DuplicateEntity("User", "email", user.email) from e
            raise DuplicateEntity("User", "auth_provider", user.auth_provider) from e
        except SQLAlchemyError as e:
            await self._session.rollback()
            raise RepositoryError("Database error saving user") from e

    async def find_by_id(self, user_id: UUID) -> User | None:
        result = await self._session.get(UserModel, user_id)
        return self._to_domain(result) if result else None

    async def find_by_auth(self, provider: str, provider_id: str) -> User | None:
        stmt = select(UserModel).where(
            UserModel.auth_provider == provider,
            UserModel.auth_id == provider_id,
        )
        result = await self._session.execute(stmt)
        row = result.scalar_one_or_none()
        return self._to_domain(row) if row else None

    async def find_by_email(self, email: str) -> User | None:
        stmt = select(UserModel).where(UserModel.email == email)
        result = await self._session.execute(stmt)
        row = result.scalar_one_or_none()
        return self._to_domain(row) if row else None

    async def list(self) -> list[User]:
        result = await self._session.execute(select(UserModel))
        return [self._to_domain(row) for row in result.scalars()]

    async def delete(self, user_id: UUID) -> None:
        stmt = delete(UserModel).where(UserModel.id == user_id)
        result = await self._session.execute(stmt)
        await self._session.commit()
        if result.rowcount == 0:
            raise EntityNotFound("User", str(user_id))

    def _to_domain(self, model: UserModel) -> User:
        return User(
            email=model.email,
            name=model.name,
            auth_provider=model.auth_provider,
            auth_id=model.auth_id,
            id=model.id,
            avatar_url=model.avatar_url or "",
            created_at=model.created_at,
        )

    @staticmethod
    def _to_orm_kwargs(user: User) -> dict:
        return {
            "id": user.id,
            "email": user.email,
            "name": user.name,
            "auth_provider": user.auth_provider,
            "auth_id": user.auth_id,
            "avatar_url": user.avatar_url or None,
            "created_at": user.created_at,
        }
