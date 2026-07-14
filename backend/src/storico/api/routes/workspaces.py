"""Workspace CRUD and member management API routes."""

from dataclasses import replace
from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Path, status

from storico.api.dependencies import (
    get_current_user,
    get_repository,
    get_workspace_for_user,
    require_admin,
    require_owner,
)
from storico.api.schemas.workspace import (
    CreateWorkspaceRequest,
    UpdateWorkspaceRequest,
    WorkspaceListResponse,
    WorkspaceResponse,
)
from storico.api.schemas.workspace_member import (
    AddMemberRequest,
    MemberListResponse,
    MemberResponse,
    TransferOwnershipRequest,
    UpdateMemberRoleRequest,
)
from storico.application.workspaces import (
    AddMemberUseCase,
    CreateWorkspaceUseCase,
    RemoveMemberUseCase,
    TransferOwnershipUseCase,
)
from storico.domain.entities import User, Workspace, WorkspaceMember, WorkspaceRole
from storico.infrastructure.database.repositories import SQLAlchemyUserRepository
from storico.infrastructure.database.repositories.workspace_member_repository import (
    SQLAlchemyWorkspaceMemberRepository,
)
from storico.infrastructure.database.repositories.workspace_repository import (
    SQLAlchemyWorkspaceRepository,
)

router = APIRouter(prefix="/api/v1/workspaces", tags=["workspaces"])

# ── Type aliases ────────────────────────────────────────────────────

WsRepoDep = Annotated[
    SQLAlchemyWorkspaceRepository,
    Depends(get_repository(SQLAlchemyWorkspaceRepository)),
]

MemberRepoDep = Annotated[
    SQLAlchemyWorkspaceMemberRepository,
    Depends(get_repository(SQLAlchemyWorkspaceMemberRepository)),
]

UserRepoDep = Annotated[
    SQLAlchemyUserRepository,
    Depends(get_repository(SQLAlchemyUserRepository)),
]

# ── Helpers ─────────────────────────────────────────────────────────


def _workspace_to_response(
    workspace: Workspace,
    role: str,
    member_count: int = 0,
) -> WorkspaceResponse:
    return WorkspaceResponse(
        id=workspace.id,
        name=workspace.name,
        slug=workspace.slug,
        owner_id=workspace.owner_id,
        role=role,
        member_count=member_count,
        created_at=workspace.created_at,
        updated_at=workspace.updated_at,
    )


async def _enrich_member(
    member: WorkspaceMember, user_repo: SQLAlchemyUserRepository
) -> MemberResponse:
    user = await user_repo.find_by_id(member.user_id)
    return MemberResponse(
        user_id=member.user_id,
        name=user.name if user else "Unknown",
        email=user.email if user else "unknown@unknown.com",
        avatar_url=user.avatar_url if user else None,
        role=member.role.value,
        created_at=member.created_at,
    )


# ── Workspace CRUD ──────────────────────────────────────────────────


@router.post("/", status_code=status.HTTP_201_CREATED)
async def create_workspace(
    body: CreateWorkspaceRequest,
    current_user: User = Depends(get_current_user),
    ws_repo: WsRepoDep = None,  # type: ignore[assignment]
    member_repo: MemberRepoDep = None,  # type: ignore[assignment]
) -> WorkspaceResponse:
    """Create a new workspace.

    The authenticated user becomes both admin and owner of the newly
    created workspace.
    """
    use_case = CreateWorkspaceUseCase(ws_repo, member_repo)
    workspace = await use_case.execute(
        name=body.name,
        user_id=current_user.id,
        slug=body.slug,
    )
    return _workspace_to_response(workspace, role="admin", member_count=1)


@router.get("/")
async def list_workspaces(
    current_user: User = Depends(get_current_user),
    ws_repo: WsRepoDep = None,  # type: ignore[assignment]
    member_repo: MemberRepoDep = None,  # type: ignore[assignment]
) -> WorkspaceListResponse:
    """List all workspaces the authenticated user is a member of."""
    members = await member_repo.list_by_user(current_user.id)
    workspaces: list[WorkspaceResponse] = []
    for member in members:
        workspace = await ws_repo.find_by_id(member.workspace_id)
        if workspace is None:
            continue
        member_count = await ws_repo.count_members(workspace.id)
        workspaces.append(
            _workspace_to_response(workspace, member.role.value, member_count)
        )
    return WorkspaceListResponse(workspaces=workspaces)


@router.get("/{workspace_id}")
async def get_workspace(
    ctx: tuple[Workspace, WorkspaceRole] = Depends(get_workspace_for_user),
    ws_repo: WsRepoDep = None,  # type: ignore[assignment]
) -> WorkspaceResponse:
    """Get workspace details.

    Uses ``get_workspace_for_user`` which returns 404 if the workspace
    does not exist (no 403 — avoids leaking existence).
    """
    workspace, role = ctx
    member_count = await ws_repo.count_members(workspace.id)
    return _workspace_to_response(workspace, role.value, member_count)


@router.put("/{workspace_id}")
async def update_workspace(
    body: UpdateWorkspaceRequest,
    ctx: tuple[Workspace, WorkspaceRole] = Depends(require_admin),
    ws_repo: WsRepoDep = None,  # type: ignore[assignment]
) -> WorkspaceResponse:
    """Update workspace name and/or slug. Admin only."""
    workspace, role = ctx

    kwargs: dict = {"updated_at": datetime.now(UTC)}
    if body.name is not None:
        kwargs["name"] = body.name
    if body.slug is not None:
        if body.slug != workspace.slug:
            existing = await ws_repo.find_by_slug(body.slug)
            if existing is not None:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Workspace with slug '{body.slug}' already exists",
                )
        kwargs["slug"] = body.slug

    updated = replace(workspace, **kwargs)
    result = await ws_repo.save(updated)
    member_count = await ws_repo.count_members(workspace.id)
    return _workspace_to_response(result, role.value, member_count)


@router.delete("/{workspace_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_workspace(
    ctx: tuple[Workspace, WorkspaceRole] = Depends(require_admin),
    ws_repo: WsRepoDep = None,  # type: ignore[assignment]
) -> None:
    """Delete a workspace and all associated data. Admin only."""
    workspace, _ = ctx
    await ws_repo.delete(workspace.id)


# ── Member management ──────────────────────────────────────────────


@router.get("/{workspace_id}/members")
async def list_members(
    ctx: tuple[Workspace, WorkspaceRole] = Depends(require_admin),
    member_repo: MemberRepoDep = None,  # type: ignore[assignment]
    user_repo: UserRepoDep = None,  # type: ignore[assignment]
) -> MemberListResponse:
    """List all members of a workspace. Admin only."""
    workspace, _ = ctx
    members = await member_repo.list_by_workspace(workspace.id)
    enriched = [
        await _enrich_member(member, user_repo) for member in members
    ]
    return MemberListResponse(members=enriched)


@router.post(
    "/{workspace_id}/members",
    status_code=status.HTTP_201_CREATED,
)
async def add_member(
    body: AddMemberRequest,
    ctx: tuple[Workspace, WorkspaceRole] = Depends(require_admin),
    ws_repo: WsRepoDep = None,  # type: ignore[assignment]
    member_repo: MemberRepoDep = None,  # type: ignore[assignment]
    user_repo: UserRepoDep = None,  # type: ignore[assignment]
) -> MemberResponse:
    """Add a user as a member of the workspace. Admin only."""
    workspace, _ = ctx
    use_case = AddMemberUseCase(ws_repo, member_repo, user_repo)
    new_member = await use_case.execute(workspace.id, body.user_id)
    return await _enrich_member(new_member, user_repo)


@router.put("/{workspace_id}/members/{user_id}")
async def update_member_role(
    body: UpdateMemberRoleRequest,
    user_id: UUID = Path(...),
    ctx: tuple[Workspace, WorkspaceRole] = Depends(require_admin),
    member_repo: MemberRepoDep = None,  # type: ignore[assignment]
    user_repo: UserRepoDep = None,  # type: ignore[assignment]
) -> MemberResponse:
    """Change a member's role. Admin only.

    The workspace owner's role cannot be changed. Transfer ownership
    first if you need to change the owner's role.
    """
    workspace, _ = ctx

    if user_id == workspace.owner_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The workspace owner's role cannot be changed. "
            "Transfer ownership first.",
        )

    new_role = WorkspaceRole(body.role)
    updated_member = await member_repo.update_role(
        workspace.id, user_id, new_role
    )
    return await _enrich_member(updated_member, user_repo)


@router.delete(
    "/{workspace_id}/members/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def remove_member(
    user_id: UUID = Path(...),
    ctx: tuple[Workspace, WorkspaceRole] = Depends(require_admin),
    current_user: User = Depends(get_current_user),
    ws_repo: WsRepoDep = None,  # type: ignore[assignment]
    member_repo: MemberRepoDep = None,  # type: ignore[assignment]
) -> None:
    """Remove a member from the workspace. Admin only.

    The workspace owner cannot be removed. An admin cannot remove
    themselves if they are the last admin.
    """
    workspace, _ = ctx
    use_case = RemoveMemberUseCase(ws_repo, member_repo)
    await use_case.execute(workspace.id, current_user.id, user_id)


@router.post("/{workspace_id}/transfer")
async def transfer_ownership(
    body: TransferOwnershipRequest,
    workspace: Workspace = Depends(require_owner),
    member_repo: MemberRepoDep = None,  # type: ignore[assignment]
) -> dict:
    """Transfer workspace ownership to another admin. Owner only."""
    use_case = TransferOwnershipUseCase(member_repo)
    await use_case.execute(
        workspace_id=workspace.id,
        current_owner_id=workspace.owner_id,
        new_owner_id=body.new_owner_id,
    )
    return {
        "message": "Ownership transferred",
        "previous_owner_id": str(workspace.owner_id),
        "new_owner_id": str(body.new_owner_id),
    }
