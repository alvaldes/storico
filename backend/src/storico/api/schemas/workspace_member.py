"""Workspace member Pydantic schemas for Storico API."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class AddMemberRequest(BaseModel):
    """Request body for adding a member to a workspace."""

    model_config = ConfigDict(extra="forbid")

    user_email: str = Field(
        ...,
        min_length=5,
        max_length=255,
        description="Email of the user to add to the workspace",
    )


class TransferOwnershipRequest(BaseModel):
    """Request body for transferring workspace ownership."""

    model_config = ConfigDict(extra="forbid")

    new_owner_id: UUID


class UpdateMemberRoleRequest(BaseModel):
    """Request body for updating a member's role."""

    model_config = ConfigDict(extra="forbid")

    role: str = Field(..., pattern=r"^(admin|member)$")


class MemberResponse(BaseModel):
    """Response body representing a workspace member."""

    model_config = ConfigDict(from_attributes=True)

    user_id: UUID
    name: str
    email: str
    avatar_url: str | None = None
    role: str
    created_at: datetime


class MemberListResponse(BaseModel):
    """Response body for listing workspace members."""

    members: list[MemberResponse]
