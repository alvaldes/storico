"""Auth sync endpoint — called by Auth.js jwt callback on OAuth login."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status

from storico.api.dependencies import get_repository
from storico.api.schemas.user import AuthSyncRequest, UserResponse
from storico.config.settings import Settings
from storico.domain.entities import User
from storico.infrastructure.database.repositories import SQLAlchemyUserRepository

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

UserRepoDep = Annotated[
    SQLAlchemyUserRepository,
    Depends(get_repository(SQLAlchemyUserRepository)),
]


async def verify_sync_token(request: Request) -> None:
    """Verify the internal token on /auth/sync — loopback-only is not enough."""
    settings = Settings.load()
    token = request.headers.get("X-Storico-Internal-Token")
    if not token or token != settings.auth_internal_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid internal token",
        )


@router.post("/sync", response_model=UserResponse)
async def sync_user(
    payload: AuthSyncRequest,
    repo: UserRepoDep,
    _: None = Depends(verify_sync_token),
) -> UserResponse:
    """Sync a user from OAuth login — creates or updates by auth_provider + auth_id.

    Returns 200 for existing users and 201 for newly created ones.
    """
    existing = await repo.find_by_auth(
        payload.auth_provider, payload.auth_provider_id
    )
    if existing:
        user = User(
            id=existing.id,
            email=payload.email,
            name=payload.name,
            avatar_url=payload.avatar_url or existing.avatar_url,
            auth_provider=payload.auth_provider,
            auth_id=payload.auth_provider_id,
            created_at=existing.created_at,
        )
    else:
        user = User(
            email=payload.email,
            name=payload.name,
            avatar_url=payload.avatar_url or "",
            auth_provider=payload.auth_provider,
            auth_id=payload.auth_provider_id,
        )

    saved = await repo.save(user)
    return UserResponse(
        id=saved.id,
        email=saved.email,
        name=saved.name,
        auth_provider=saved.auth_provider,
        auth_id=saved.auth_id,
        avatar_url=saved.avatar_url or None,
        created_at=saved.created_at,
    )
