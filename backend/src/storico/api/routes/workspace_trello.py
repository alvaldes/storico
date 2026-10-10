"""Workspace Trello credential settings routes.

Mirrors the LLM config module's split: ``GET`` and ``PUT /settings/trello`` are
admin-only and return the decrypted pair, while ``GET /settings/trello/status`` is
readable by any member and answers with the missing *field names* — never a value.
A member has no business reading the credentials, but they are the ones who trigger
the export that depends on them, so they need to learn the workspace is not ready
*before* the attempt fails.

Both routes are wired to the dedicated repository factory
(``get_trello_config_repository``) because the repository needs the cipher alongside
the session: it encrypts on write and decrypts on read, so no caller ever holds
ciphertext. A missing master key surfaces through the existing cipher error envelope
(``api/errors.py``) as a 500 with an actionable code, not a crash.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from storico.api.dependencies import (
    get_trello_config_repository,
    get_workspace_for_user,
    require_admin,
)
from storico.api.schemas.workspace_trello import (
    TrelloConfigRequest,
    TrelloConfigResponse,
    TrelloConfigStatusResponse,
)
from storico.domain.entities.workspace import Workspace
from storico.domain.entities.workspace_member import WorkspaceRole
from storico.domain.entities.workspace_trello_config import WorkspaceTrelloConfig
from storico.domain.services.llm_config_readiness import normalize_optional
from storico.infrastructure.database.repositories.workspace_trello_config_repository import (
    SQLAlchemyWorkspaceTrelloConfigRepository,
)

router = APIRouter(
    prefix="/api/v1/workspaces/{workspace_id}/settings",
    tags=["workspace-settings"],
)

# ``type`` rather than a plain assignment: PEP 695 declares the alias to the type
# checker, and FastAPI resolves it through ``get_type_hints`` like any other
# ``Annotated`` dependency. Same shape as the LLM config module's repo dependency.
type TrelloConfigRepoDep = Annotated[
    SQLAlchemyWorkspaceTrelloConfigRepository,
    Depends(get_trello_config_repository),
]

# The two fields the pair needs, in the order the status reports them.
_TRELLO_FIELDS = ("api_key", "token")


def _resolve_trello_config(
    config: WorkspaceTrelloConfig | None,
) -> TrelloConfigResponse:
    """Build the admin answer, normalizing a stored blank to absent.

    The repository already decrypts; a legacy row holding a value made of spaces is
    "not configured", which is what the write path stores for it — so the read hands
    the form ``None`` rather than a credential of spaces.
    """
    if config is None:
        return TrelloConfigResponse(api_key=None, token=None)
    return TrelloConfigResponse(
        api_key=normalize_optional(config.api_key),
        token=normalize_optional(config.token),
    )


def _missing_fields(config: WorkspaceTrelloConfig | None) -> list[str]:
    """The field names of the pair that are absent or blank."""
    if config is None:
        return list(_TRELLO_FIELDS)
    return [name for name in _TRELLO_FIELDS if not normalize_optional(getattr(config, name))]


@router.get("/trello")
async def get_trello_config(
    config_repo: TrelloConfigRepoDep,
    ctx: tuple[Workspace, WorkspaceRole] = Depends(require_admin),
) -> TrelloConfigResponse:
    """Get the workspace Trello credentials, decrypted. Admin only.

    Returns ``null`` fields for a workspace that has not configured the pair yet.
    """
    workspace, _ = ctx
    return _resolve_trello_config(await config_repo.get(workspace.id))


@router.put("/trello")
async def upsert_trello_config(
    body: TrelloConfigRequest,
    config_repo: TrelloConfigRepoDep,
    ctx: tuple[Workspace, WorkspaceRole] = Depends(require_admin),
) -> TrelloConfigResponse:
    """Upsert workspace Trello credentials. Admin only.

    Only the fields provided in the request body are updated. A blank credential is
    stored as ``None`` — the repository's encrypt path would otherwise spend a token
    storing a value that has to be decrypted back to nothing — and a value carried
    over from the existing row is normalized too, so any save also cleans a legacy
    blank. The repository encrypts on the way in; the response returns the decrypted
    pair, the same convention as the LLM config module.
    """
    workspace, _ = ctx

    existing = await config_repo.get(workspace.id)

    merged = WorkspaceTrelloConfig(
        workspace_id=workspace.id,
        api_key=normalize_optional(body.api_key)
        if body.api_key is not None
        else (normalize_optional(existing.api_key) if existing else None),
        token=normalize_optional(body.token)
        if body.token is not None
        else (normalize_optional(existing.token) if existing else None),
    )

    await config_repo.upsert(merged)
    return _resolve_trello_config(merged)


@router.get("/trello/status")
async def get_trello_config_status(
    config_repo: TrelloConfigRepoDep,
    ctx: tuple[Workspace, WorkspaceRole] = Depends(get_workspace_for_user),
) -> TrelloConfigStatusResponse:
    """Report whether this workspace has Trello credentials, and which it is missing.

    Readable by any member, unlike every other route in this module. The member who
    cannot read the credentials is exactly the one who meets the failed export, so
    this is the one piece of it they are entitled to: the missing field names, never
    the values those fields hold.
    """
    workspace, _ = ctx
    config = await config_repo.get(workspace.id)
    missing = _missing_fields(config)
    return TrelloConfigStatusResponse(
        configured=not missing,
        missing=list(missing),
    )
