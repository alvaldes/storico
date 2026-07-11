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
    """Sync a user from OAuth login — 3-step linking flow.

    Step (a): find by (provider, provider_id) → update profile.
    Step (b): fallback to find_by_email → link accounts.
    Step (c): neither → create user + link account.
    """
    # Step (a) — returning user, same provider
    existing = await repo.find_by_auth(
        payload.auth_provider, payload.auth_provider_id
    )
    if existing:
        user = User(
            id=existing.id,
            email=payload.email,
            name=payload.name,
            avatar_url=payload.avatar_url or existing.avatar_url,
            created_at=existing.created_at,
        )
        await repo.save(user)
        return UserResponse(
            id=user.id,
            email=user.email,
            name=user.name,
            auth_provider=payload.auth_provider,
            auth_id=payload.auth_provider_id,
            avatar_url=payload.avatar_url or user.avatar_url or None,
            created_at=user.created_at,
        )

    # Step (b) — same email, different provider → link
    email_user = await repo.find_by_email(payload.email)
    if email_user:
        await repo.link_account(
            email_user.id, payload.auth_provider, payload.auth_provider_id
        )
        user = User(
            id=email_user.id,
            email=payload.email,
            name=payload.name,
            avatar_url=payload.avatar_url or email_user.avatar_url,
            created_at=email_user.created_at,
        )
        await repo.save(user)
        return UserResponse(
            id=user.id,
            email=user.email,
            name=user.name,
            auth_provider=payload.auth_provider,
            auth_id=payload.auth_provider_id,
            avatar_url=payload.avatar_url or user.avatar_url or None,
            created_at=user.created_at,
        )

    # Step (c) — new user
    user = User(
        email=payload.email,
        name=payload.name,
        avatar_url=payload.avatar_url or "",
    )
    saved = await repo.save(user)
    await repo.link_account(saved.id, payload.auth_provider, payload.auth_provider_id)
    return UserResponse(
        id=saved.id,
        email=saved.email,
        name=saved.name,
        auth_provider=payload.auth_provider,
        auth_id=payload.auth_provider_id,
        avatar_url=payload.avatar_url or saved.avatar_url or None,
        created_at=saved.created_at,
    )
