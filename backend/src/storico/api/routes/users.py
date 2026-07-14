"""User API routes."""

from typing import Annotated

from fastapi import APIRouter, Depends

from storico.api.dependencies import get_current_user, get_repository
from storico.api.schemas.user import UserProfileResponse, UserResponse, WorkspaceSummary
from storico.domain.entities import User
from storico.infrastructure.database.repositories import SQLAlchemyUserRepository
from storico.infrastructure.database.repositories.workspace_member_repository import (
    SQLAlchemyWorkspaceMemberRepository,
)
from storico.infrastructure.database.repositories.workspace_repository import (
    SQLAlchemyWorkspaceRepository,
)

router = APIRouter(prefix="/api/v1/users", tags=["users"])

CurrentUserDep = Annotated[User, Depends(get_current_user)]
UserRepoDep = Annotated[
    SQLAlchemyUserRepository,
    Depends(get_repository(SQLAlchemyUserRepository)),
]
WorkspaceRepoDep = Annotated[
    SQLAlchemyWorkspaceRepository,
    Depends(get_repository(SQLAlchemyWorkspaceRepository)),
]
MemberRepoDep = Annotated[
    SQLAlchemyWorkspaceMemberRepository,
    Depends(get_repository(SQLAlchemyWorkspaceMemberRepository)),
]


@router.get("/me", response_model=UserProfileResponse)
async def get_me(
    current_user: CurrentUserDep,
    repo: UserRepoDep,
    ws_repo: WorkspaceRepoDep,
    member_repo: MemberRepoDep,
) -> UserProfileResponse:
    """Get the currently authenticated user's profile with workspace memberships."""
    accounts = await repo.find_accounts(current_user.id)
    first = accounts[0] if accounts else None

    user = UserResponse(
        id=current_user.id,
        email=current_user.email,
        name=current_user.name,
        auth_provider=first.provider if first else "",
        auth_id=first.provider_id if first else "",
        avatar_url=current_user.avatar_url or None,
        created_at=current_user.created_at,
    )

    # Fetch workspace memberships with roles
    memberships = await member_repo.list_by_user(current_user.id)
    workspaces_raw = await ws_repo.list_by_user(current_user.id)
    role_map = {m.workspace_id: m.role for m in memberships}

    workspaces = [
        WorkspaceSummary(
            id=w.id,
            name=w.name,
            slug=w.slug,
            role=role_map[w.id].value,
            created_at=w.created_at,
        )
        for w in workspaces_raw
    ]

    return UserProfileResponse(user=user, workspaces=workspaces)
