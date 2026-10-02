"""Extraction API routes — real LLM-based task extraction.

This module provides two routers:

1. ``router`` (prefix ``/api/v1/extract``) — legacy route that returns
   410 Gone, directing clients to the workspace-scoped endpoint.
2. ``extraction_router`` (prefix ``/api/v1/workspaces/{workspace_id}/extract``)
   — workspace-scoped extraction routes.

The POST endpoint is **asynchronous**: it creates a pending extraction record,
launches a background ``asyncio.create_task`` for the LLM call, and responds
immediately with ``202 Accepted``.  The client polls
``GET /api/v1/extractions/{extraction_id}`` to get the final status.

No Celery, no Redis — the background task runs in the same process.
"""

import asyncio
import logging
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status

from storico.api.dependencies import (
    get_llm_config_repository,
    get_repository,
    get_workspace_for_user,
    require_owner_or_admin,
)
from storico.api.error_codes import (
    EXTRACTION_ENDPOINT_REMOVED,
    EXTRACTION_NOT_FOUND,
    STORY_NOT_IN_WORKSPACE,
)
from storico.api.errors import ApiError
from storico.api.schemas.extraction import (
    ExtractionResponse,
    ExtractRequest,
    ExtractResponse,
)
from storico.domain.entities import EntityNotFound, Extraction, Workspace, WorkspaceRole
from storico.domain.entities.extraction import ExtractionStatus
from storico.domain.entities.user_story import UserStoryStatus
from storico.domain.ports.llm_port import DEFAULT_TEMPERATURE
from storico.domain.services.llm_config_readiness import (
    LLM_CONFIG_INCOMPLETE_CODE,
    missing_llm_config_fields,
    normalize_optional,
)
from storico.infrastructure.database.repositories import (
    SQLAlchemyExtractionRepository,
    SQLAlchemyProjectRepository,
    SQLAlchemyUserStoryRepository,
)
from storico.infrastructure.database.repositories.workspace_llm_config_repository import (
    SQLAlchemyWorkspaceLLMConfigRepository,
)
from storico.infrastructure.tasks.extraction_task import run_background_extraction

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════════
# Legacy router — 410 Gone
# ═══════════════════════════════════════════════════════════════════

router = APIRouter(prefix="/api/v1/extract", tags=["extract"])


@router.api_route(
    "/{path:path}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"],
    status_code=status.HTTP_410_GONE,
    include_in_schema=False,
)
async def deprecated_extract() -> None:
    """Legacy extraction endpoint — permanently removed.

    Extraction is now scoped to workspaces. Use:
      POST /api/v1/workspaces/{workspace_id}/extract
      GET  /api/v1/workspaces/{workspace_id}/extract/status/{extraction_id}
    """
    raise ApiError(
        status_code=status.HTTP_410_GONE,
        error_code=EXTRACTION_ENDPOINT_REMOVED,
        detail=(
            "This endpoint has been removed. "
            "Extraction is now scoped to workspaces. "
            "Use /api/v1/workspaces/{workspace_id}/extract instead."
        ),
    )


# ═══════════════════════════════════════════════════════════════════
# New workspace-scoped router
# ═══════════════════════════════════════════════════════════════════

extraction_router = APIRouter(
    prefix="/api/v1/workspaces/{workspace_id}/extract",
    tags=["extract"],
    redirect_slashes=False,
)

ExtractionRepoDep = Annotated[
    SQLAlchemyExtractionRepository,
    Depends(get_repository(SQLAlchemyExtractionRepository)),
]

StoryRepoDep = Annotated[
    SQLAlchemyUserStoryRepository,
    Depends(get_repository(SQLAlchemyUserStoryRepository)),
]

ProjectRepoDep = Annotated[
    SQLAlchemyProjectRepository,
    Depends(get_repository(SQLAlchemyProjectRepository)),
]

LLMConfigRepoDep = Annotated[
    SQLAlchemyWorkspaceLLMConfigRepository,
    Depends(get_llm_config_repository),
]


async def _validate_story_belongs_to_workspace(
    user_story_id: UUID,
    workspace_id: UUID,
    story_repo: SQLAlchemyUserStoryRepository,
    project_repo: SQLAlchemyProjectRepository,
) -> None:
    """Validate that a user story belongs to the given workspace.

    Raises ``EntityNotFound`` (404) if the story or its project is missing.
    Raises ``ApiError`` with ``STORY_NOT_IN_WORKSPACE`` (403) if the story does
    not belong to the workspace.
    """
    story = await story_repo.find_by_id(user_story_id)
    if story is None:
        raise EntityNotFound("UserStory", str(user_story_id))

    project = await project_repo.find_by_id(story.project_id)
    if project is None:
        raise EntityNotFound("UserStory", str(user_story_id))

    if project.workspace_id != workspace_id:
        raise ApiError(
            status_code=status.HTTP_403_FORBIDDEN,
            error_code=STORY_NOT_IN_WORKSPACE,
            detail="This user story does not belong to the specified workspace",
        )


@extraction_router.post("/", status_code=status.HTTP_202_ACCEPTED)
async def extract_tasks(
    body: ExtractRequest,
    # The version-mutating gate (D13): extracting mints a new version, so only
    # the workspace owner or an admin may start a run. The dependency chains
    # ``get_workspace_for_user`` itself, so a non-member's 403
    # ``NOT_A_WORKSPACE_MEMBER`` fires first and keeps its code; the gate's own
    # 403 ``WORKSPACE_OWNER_OR_ADMIN_REQUIRED`` is reserved for a member who is
    # neither the owner nor an ``ADMIN``. The status route below stays open to
    # every member — the gate is on the mutation, not on the read.
    ctx: tuple[Workspace, WorkspaceRole] = Depends(require_owner_or_admin),
    extraction_repo: ExtractionRepoDep = None,  # type: ignore[assignment]
    story_repo: StoryRepoDep = None,  # type: ignore[assignment]
    project_repo: ProjectRepoDep = None,  # type: ignore[assignment]
    llm_config_repo: LLMConfigRepoDep = None,  # type: ignore[assignment]
) -> ExtractResponse:
    """Extract tasks from a user story using an LLM.

    The user story must belong to a project within the workspace specified
    in the URL path. Only the workspace owner or a member with the ``admin``
    role may start an extraction: a member with the ``member`` role gets
    403 ``WORKSPACE_OWNER_OR_ADMIN_REQUIRED`` and a non-member 403
    ``NOT_A_WORKSPACE_MEMBER``, and neither creates an extraction.

    **This endpoint is asynchronous.** It creates a pending extraction
    record, launches the LLM call in a background task, and responds
    **immediately** with ``202 Accepted``. The client must poll
    ``GET /api/v1/extractions/{extraction_id}`` to get the final status.

    When the extraction completes, tasks are persisted to the database
    and can be fetched via ``GET /api/v1/tasks?user_story_id=...``.

    If ``body.model`` is ``None``, the model is resolved from the
    workspace's LLM config.

    The workspace's LLM configuration must be complete for its provider before
    anything is created. When it is not, this answers ``400`` with
    ``error_code: "LLM_CONFIG_INCOMPLETE"`` and the missing field names, leaving the
    story and the extraction table untouched.
    """
    workspace, _ = ctx

    # Validate the user story belongs to this workspace
    await _validate_story_belongs_to_workspace(
        body.user_story_id, workspace.id, story_repo, project_repo
    )

    # Resolve model, provider, api_key, and base_url from workspace config.
    # Even when body.model is provided, we fetch the workspace config for
    # api_key and base_url (which are never exposed in the request body).
    ws_config = await llm_config_repo.get(workspace.id)

    model = body.model or (ws_config.model if ws_config else None)
    # Normalized so the value that travels to the background task is the same one the
    # completeness rule below reasons about: a blank endpoint or credential is "not
    # configured", and the adapter must receive ``None`` rather than a string of spaces.
    api_key = normalize_optional(ws_config.api_key) if ws_config else None
    base_url = normalize_optional(ws_config.base_url) if ws_config else None

    # Provider: workspace config, fallback ollama
    provider = ws_config.provider if ws_config and ws_config.provider else "ollama"

    # Refuse before creating anything.
    #
    # An extraction against an incomplete configuration can only fail. It used to
    # fail *after* this route had already created a pending row and dragged the
    # story into ``failed_extraction`` — a state the user then had to repair. The
    # rule read here is the same one the settings form and
    # ``GET /settings/llm/status`` read, so the client is told which fields to fix
    # instead of only that something went wrong.
    missing = missing_llm_config_fields(provider, model=model, api_key=api_key, base_url=base_url)
    # ``model`` is named in the condition as well as carried by ``missing``: every
    # provider family requires it (pinned by
    # ``test_llm_config_readiness.test_every_provider_family_requires_a_model``), so
    # the two are equivalent — and naming it is what lets the type checker see that
    # the value below is no longer ``str | None``.
    if missing or model is None:
        raise ApiError(
            status_code=status.HTTP_400_BAD_REQUEST,
            error_code=LLM_CONFIG_INCOMPLETE_CODE,
            detail={
                "detail": "This workspace's LLM configuration is incomplete.",
                "provider": provider,
                "missing": list(missing),
            },
        )

    # 1. Create pending extraction record — gives the client something to poll
    #    ``temperature`` is resolved once, here: the column that declares it, the
    #    ``LLMConfig`` the adapter runs at, and the value passed to the runner are all
    #    this one resolved value.
    resolved_temperature = body.temperature if body.temperature is not None else DEFAULT_TEMPERATURE
    pending = Extraction(
        user_story_id=body.user_story_id,
        model_used=model,
        raw_response="",
        provider=provider,
        temperature=resolved_temperature,
        status=ExtractionStatus.PENDING,
        user_story_status=UserStoryStatus.PENDING_EXTRACTION,
        # ``temperature`` has its own column; a second copy in JSON is drift bait.
        prompt_config={
            "validate": body.run_validation,
        },
    )
    pending = await extraction_repo.create_next_version(pending)
    extraction_id = pending.id

    # 2. Launch background extraction in the same process
    #    No Celery, no Redis — just asyncio.create_task
    asyncio.create_task(
        run_background_extraction(
            extraction_id=extraction_id,
            story_id=body.user_story_id,
            workspace_id=workspace.id,
            model=model,
            temperature=resolved_temperature,
            validate=body.run_validation,
            provider=provider,
            api_key=api_key,
            base_url=base_url,
        )
    )

    # 3. Respond immediately — no tasks yet, client will poll
    return ExtractResponse(
        extraction_id=extraction_id,
        status=ExtractionStatus.PENDING,
        user_story_id=body.user_story_id,
        message="Extraction started. Poll GET /extractions/{extraction_id} for progress.",
        # What the just-created extraction actually has: the minted number is the
        # returned entity's (create_next_version is its only source), and the
        # provider/temperature are the values resolved above that the background
        # run itself was handed.
        version_number=pending.version_number,
        provider=provider,
        temperature=resolved_temperature,
    )


@extraction_router.get("/status/{extraction_id}")
async def extraction_status(
    extraction_id: UUID,
    ctx: tuple[Workspace, WorkspaceRole] = Depends(get_workspace_for_user),
    repo: ExtractionRepoDep = None,  # type: ignore[assignment]
    story_repo: StoryRepoDep = None,  # type: ignore[assignment]
    project_repo: ProjectRepoDep = None,  # type: ignore[assignment]
) -> ExtractionResponse:
    """Get the status and details of an extraction by its ID.

    The extraction must belong to a user story in the workspace specified
    in the URL path. Workspace membership is validated via
    ``get_workspace_for_user``.
    """
    workspace, _ = ctx
    extraction = await repo.find_by_id(extraction_id)
    if extraction is None:
        raise ApiError(
            status_code=status.HTTP_404_NOT_FOUND,
            error_code=EXTRACTION_NOT_FOUND,
            detail=f"Extraction '{extraction_id}' not found",
        )

    # Membership of the path workspace is not containment: without this check any
    # member of any workspace could read any extraction by guessing its id.
    await _validate_story_belongs_to_workspace(
        extraction.user_story_id, workspace.id, story_repo, project_repo
    )
    return ExtractionResponse(
        id=extraction.id,
        user_story_id=extraction.user_story_id,
        model_used=extraction.model_used,
        status=extraction.status,
        user_story_status=extraction.user_story_status,
        error_info=extraction.error_info,
        prompt_config=extraction.prompt_config,
        raw_response=extraction.raw_response,
        confidence_score=extraction.confidence_score,
        created_at=extraction.created_at,
        completed_at=extraction.completed_at,
        version_number=extraction.version_number,
        provider=extraction.provider,
        temperature=extraction.temperature,
    )
