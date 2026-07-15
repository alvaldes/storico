"""User Pydantic schemas for Storico API."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class AuthSyncRequest(BaseModel):
    """Request body for the auth sync endpoint — called by Auth.js on login."""

    model_config = ConfigDict(extra="forbid")

    email: str
    name: str
    auth_provider: str
    auth_provider_id: str
    avatar_url: str | None = None


class UserResponse(BaseModel):
    """Response body representing a user."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: str
    name: str
    auth_provider: str
    auth_id: str
    avatar_url: str | None = None
    is_first_login: bool
    created_at: datetime


class OnboardingRequest(BaseModel):
    """Request body for completing onboarding."""

    model_config = ConfigDict(extra="forbid")

    workspace_name: str | None = Field(None, max_length=100)


class WorkspaceSummary(BaseModel):
    """Lightweight workspace reference for the user profile response."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    slug: str
    role: str
    created_at: datetime


class UserProfileResponse(BaseModel):
    """Full user profile including workspace memberships."""

    user: UserResponse
    workspaces: list[WorkspaceSummary]
