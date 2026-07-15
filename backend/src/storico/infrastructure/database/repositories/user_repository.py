"""SQLAlchemy implementation of the UserRepository port."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from storico.domain.entities import DuplicateEntity, EntityNotFound, RepositoryError, User
from storico.domain.entities.user_account import UserAccount
from storico.domain.ports import UserRepository
from storico.infrastructure.database.models import UserAccountModel, UserModel


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
            raise DuplicateEntity("User", str(e)) from e
        except SQLAlchemyError as e:
            await self._session.rollback()
            raise RepositoryError("Database error saving user") from e

    async def find_by_id(self, user_id: UUID) -> User | None:
        result = await self._session.get(UserModel, user_id)
        return self._to_domain(result) if result else None

    async def find_by_auth(self, provider: str, provider_id: str) -> User | None:
        stmt = (
            select(UserModel)
            .join(UserAccountModel, UserAccountModel.user_id == UserModel.id)
            .where(
                UserAccountModel.provider == provider,
                UserAccountModel.provider_id == provider_id,
            )
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

    async def link_account(
        self, user_id: UUID, provider: str, provider_id: str
    ) -> UserAccount:
        try:
            account = UserAccount(user_id=user_id, provider=provider, provider_id=provider_id)
            self._session.add(
                UserAccountModel(
                    id=account.id,
                    user_id=account.user_id,
                    provider=account.provider,
                    provider_id=account.provider_id,
                    created_at=account.created_at,
                )
            )
            await self._session.commit()
            return account
        except IntegrityError as e:
            await self._session.rollback()
            raise DuplicateEntity("UserAccount", "provider:provider_id", f"{provider}:{provider_id}") from e
        except SQLAlchemyError as e:
            await self._session.rollback()
            raise RepositoryError("Database error linking account") from e

    async def find_accounts(self, user_id: UUID) -> list[UserAccount]:
        stmt = select(UserAccountModel).where(UserAccountModel.user_id == user_id)
        result = await self._session.execute(stmt)
        return [
            UserAccount(
                id=row.id,
                user_id=row.user_id,
                provider=row.provider,
                provider_id=row.provider_id,
                created_at=row.created_at,
            )
            for row in result.scalars()
        ]

    def _to_domain(self, model: UserModel) -> User:
        return User(
            email=model.email,
            name=model.name,
            id=model.id,
            avatar_url=model.avatar_url or "",
            is_first_login=model.is_first_login,
            created_at=model.created_at,
        )

    @staticmethod
    def _to_orm_kwargs(user: User) -> dict:
        return {
            "id": user.id,
            "email": user.email,
            "name": user.name,
            "avatar_url": user.avatar_url or None,
            "is_first_login": user.is_first_login,
            "created_at": user.created_at,
        }
