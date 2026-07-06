"""User API routes."""

from typing import Annotated

from fastapi import APIRouter, Depends

from storico.api.dependencies import get_current_user
from storico.api.schemas.user import UserResponse
from storico.domain.entities import User

router = APIRouter(prefix="/api/v1/users", tags=["users"])

CurrentUserDep = Annotated[User, Depends(get_current_user)]


@router.get("/me")
async def get_me(
    current_user: CurrentUserDep,
) -> UserResponse:
    """Get the currently authenticated user's profile."""
    return UserResponse(
        id=current_user.id,
        email=current_user.email,
        name=current_user.name,
        auth_provider=current_user.auth_provider,
        auth_id=current_user.auth_id,
        avatar_url=current_user.avatar_url or None,
        created_at=current_user.created_at,
    )
