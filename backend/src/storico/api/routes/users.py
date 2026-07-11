"""User API routes."""

from typing import Annotated

from fastapi import APIRouter, Depends

from storico.api.dependencies import get_current_user, get_repository
from storico.api.schemas.user import UserResponse
from storico.domain.entities import User
from storico.infrastructure.database.repositories import SQLAlchemyUserRepository

router = APIRouter(prefix="/api/v1/users", tags=["users"])

CurrentUserDep = Annotated[User, Depends(get_current_user)]
UserRepoDep = Annotated[
    SQLAlchemyUserRepository,
    Depends(get_repository(SQLAlchemyUserRepository)),
]


@router.get("/me")
async def get_me(
    current_user: CurrentUserDep,
    repo: UserRepoDep,
) -> UserResponse:
    """Get the currently authenticated user's profile."""
    accounts = await repo.find_accounts(current_user.id)
    first = accounts[0] if accounts else None
    return UserResponse(
        id=current_user.id,
        email=current_user.email,
        name=current_user.name,
        auth_provider=first.provider if first else "",
        auth_id=first.provider_id if first else "",
        avatar_url=current_user.avatar_url or None,
        created_at=current_user.created_at,
    )
