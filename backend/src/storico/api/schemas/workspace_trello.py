"""Workspace Trello credential Pydantic schemas for Storico API."""

from pydantic import BaseModel, ConfigDict, Field


class TrelloConfigRequest(BaseModel):
    """Request body for upserting workspace Trello credentials — both fields optional.

    An omitted field keeps the stored value; a blank one is normalized to ``None``
    by the route before the write, so "not configured" has one representation.
    """

    model_config = ConfigDict(extra="forbid")

    api_key: str | None = Field(None, max_length=500)
    token: str | None = Field(None, max_length=500)


class TrelloConfigResponse(BaseModel):
    """Response body for the admin-readable Trello credentials — the decrypted pair."""

    model_config = ConfigDict(from_attributes=True)

    api_key: str | None = None
    token: str | None = None


class TrelloConfigStatusResponse(BaseModel):
    """Whether this workspace has Trello credentials, and which fields it is missing.

    Deliberately narrow, because it is deliberately member-readable: it answers with
    the missing *field names* and never with the credential those fields hold. A
    member can learn the workspace cannot export yet without being handed the
    credentials that would let it.
    """

    model_config = ConfigDict(extra="forbid")

    configured: bool
    missing: list[str]
