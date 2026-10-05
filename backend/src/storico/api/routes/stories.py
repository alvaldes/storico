"""UserStory CRUD API routes."""

from dataclasses import replace
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, UploadFile, status

from storico.api.dependencies import (
    get_current_user,
    get_repository,
    get_vector_store,
    get_workspace_for_user,
    require_story_owner_or_admin,
    require_story_workspace_access,
)
from storico.api.error_codes import (
    DUPLICATE_USER_STORY,
    NOT_A_WORKSPACE_MEMBER,
    PROJECT_NOT_IN_WORKSPACE,
)
from storico.api.errors import ApiError
from storico.api.schemas.common import PaginatedResponse, PaginationParams
from storico.api.schemas.story import (
    CreateUserStoryRequest,
    StoryImportDuplicateItem,
    StoryImportErrorItem,
    StoryImportResponse,
    StoryVersionResponse,
    UpdateUserStoryRequest,
    UserStoryResponse,
)
from storico.api.schemas.task import StoryInvalidationResponse
from storico.application.services.story_deletion_service import StoryDeletionService
from storico.domain.entities import EntityNotFound, User, UserStory, Workspace, WorkspaceRole
from storico.domain.entities.extraction import ExtractionStatus
from storico.domain.ports.vector_store_port import VectorStorePort
from storico.domain.services.story_import import ImportRow, validate_import
from storico.infrastructure.database.repositories import (
    SQLAlchemyExtractionRepository,
    SQLAlchemyProjectRepository,
    SQLAlchemyTaskInvalidationRepository,
    SQLAlchemyUserStoryRepository,
    SQLAlchemyWorkspaceRepository,
)
from storico.infrastructure.database.repositories.workspace_member_repository import (
    SQLAlchemyWorkspaceMemberRepository,
)
from storico.infrastructure.parsers.story_csv import (
    MAX_FILE_BYTES,
    MAX_ROWS,
    StoryCsvError,
    parse_story_csv,
)

router = APIRouter(prefix="/api/v1/stories", tags=["stories"])

import_router = APIRouter(
    prefix="/api/v1/workspaces/{workspace_id}/stories",
    tags=["stories"],
    redirect_slashes=False,
)

StoryRepoDep = Annotated[
    SQLAlchemyUserStoryRepository,
    Depends(get_repository(SQLAlchemyUserStoryRepository)),
]

ProjectRepoDep = Annotated[
    SQLAlchemyProjectRepository,
    Depends(get_repository(SQLAlchemyProjectRepository)),
]

MemberRepoDep = Annotated[
    SQLAlchemyWorkspaceMemberRepository,
    Depends(get_repository(SQLAlchemyWorkspaceMemberRepository)),
]

ExtractionRepoDep = Annotated[
    SQLAlchemyExtractionRepository,
    Depends(get_repository(SQLAlchemyExtractionRepository)),
]

InvalidationRepoDep = Annotated[
    SQLAlchemyTaskInvalidationRepository,
    Depends(get_repository(SQLAlchemyTaskInvalidationRepository)),
]

WorkspaceRepoDep = Annotated[
    SQLAlchemyWorkspaceRepository,
    Depends(get_repository(SQLAlchemyWorkspaceRepository)),
]


@router.post("/", status_code=status.HTTP_201_CREATED)
async def create_story(
    body: CreateUserStoryRequest,
    current_user: User = Depends(get_current_user),
    repo: StoryRepoDep = None,  # type: ignore[assignment]
    project_repo: ProjectRepoDep = None,  # type: ignore[assignment]
    member_repo: MemberRepoDep = None,  # type: ignore[assignment]
) -> UserStoryResponse:
    """Create a new user story.

    The story's project must belong to a workspace the user is a member of.
    Duplicate stories (same raw_text) within the same project are not allowed.
    """
    # Validate the user has access to the project's workspace
    project = await project_repo.find_by_id(body.project_id)
    if project is None:
        raise EntityNotFound("Project", str(body.project_id))

    member = await member_repo.find_by_workspace_and_user(project.workspace_id, current_user.id)
    if member is None:
        raise ApiError(
            status_code=status.HTTP_403_FORBIDDEN,
            error_code=NOT_A_WORKSPACE_MEMBER,
            detail="Not a member of this workspace",
        )

    # Check for duplicate story in the same project (by actor, feature, benefit)
    existing_story = await repo.find_by_parts(
        body.project_id, body.actor, body.feature, body.benefit
    )
    if existing_story is not None:
        raise ApiError(
            status_code=status.HTTP_409_CONFLICT,
            error_code=DUPLICATE_USER_STORY,
            detail=(
                f"User story with the same actor, feature, and benefit already exists in this project. "
                f"Existing story ID: {existing_story.id}"
            ),
        )

    story = UserStory(
        project_id=body.project_id,
        actor=body.actor,
        feature=body.feature,
        benefit=body.benefit,
        raw_text=body.raw_text,
    )
    result = await repo.save(story)
    return UserStoryResponse(
        id=result.id,
        project_id=result.project_id,
        actor=result.actor,
        feature=result.feature,
        benefit=result.benefit,
        raw_text=result.raw_text,
        created_at=result.created_at,
        status=result.status,
    )


@router.get("/")
async def list_stories(
    params: Annotated[PaginationParams, Depends()],
    current_user: User = Depends(get_current_user),
    repo: StoryRepoDep = None,  # type: ignore[assignment]
    project_repo: ProjectRepoDep = None,  # type: ignore[assignment]
    member_repo: MemberRepoDep = None,  # type: ignore[assignment]
    project_id: UUID | None = None,
    workspace_id: UUID | None = None,
) -> PaginatedResponse[UserStoryResponse]:
    """List user stories with optional filters and pagination.

    Filters:
    - ``project_id``: filter by project (requires workspace membership).
    - ``workspace_id``: filter by workspace (requires workspace membership).

    If neither filter is provided, returns stories from all workspaces
    the current user is a member of.

    The page and its total come from one statement in the database —
    ``count(*) OVER ()`` rides on the rows' own query, so no separate
    ``SELECT COUNT(*)`` is issued. The order is ``created_at DESC, id DESC``,
    which makes the paging deterministic.
    """
    offset = (params.page - 1) * params.size
    # Validate workspace access and get authorized workspace IDs
    if workspace_id is not None:
        # Validate user is a member of the specified workspace
        member = await member_repo.find_by_workspace_and_user(workspace_id, current_user.id)
        if member is None:
            raise ApiError(
                status_code=status.HTTP_403_FORBIDDEN,
                error_code=NOT_A_WORKSPACE_MEMBER,
                detail="Not a member of this workspace",
            )
        page, total = await repo.list_page(
            workspace_id=workspace_id, limit=params.size, offset=offset
        )
    elif project_id is not None:
        # Validate user has access to the project's workspace
        project = await project_repo.find_by_id(project_id)
        if project is None:
            raise EntityNotFound("Project", str(project_id))
        member = await member_repo.find_by_workspace_and_user(project.workspace_id, current_user.id)
        if member is None:
            raise ApiError(
                status_code=status.HTTP_403_FORBIDDEN,
                error_code=NOT_A_WORKSPACE_MEMBER,
                detail="Not a member of this workspace",
            )
        page, total = await repo.list_page(project_id=project_id, limit=params.size, offset=offset)
    else:
        # No filter provided: return stories from all workspaces the user is a member of
        memberships = await member_repo.list_by_user(current_user.id)
        workspace_ids = [m.workspace_id for m in memberships]
        # One statement for all the workspaces, not one per workspace: this branch used to await
        # `list_by_workspace` in a loop, which cost a statement each (~2s against the dev pooler,
        # where even a bare SELECT 1 measures 800ms). An empty membership list is answered
        # without a statement by the repository.
        page, total = await repo.list_page(
            workspace_ids=workspace_ids, limit=params.size, offset=offset
        )

    items = [
        UserStoryResponse(
            id=s.id,
            project_id=s.project_id,
            actor=s.actor,
            feature=s.feature,
            benefit=s.benefit,
            raw_text=s.raw_text,
            created_at=s.created_at,
            status=s.status,
        )
        for s in page
    ]
    return PaginatedResponse(
        items=items,
        total=total,
        page=params.page,
        size=params.size,
    )


@router.get("/{story_id}")
async def get_story(
    story_id: UUID,
    current_user: User = Depends(get_current_user),
    repo: StoryRepoDep = None,  # type: ignore[assignment]
    project_repo: ProjectRepoDep = None,  # type: ignore[assignment]
    member_repo: MemberRepoDep = None,  # type: ignore[assignment]
) -> UserStoryResponse:
    """Get a user story by its ID.

    The user must be a member of the workspace that owns the story's project.
    """
    story = await require_story_workspace_access(
        story_id,
        current_user,
        story_repo=repo,
        project_repo=project_repo,
        member_repo=member_repo,
    )
    return UserStoryResponse(
        id=story.id,
        project_id=story.project_id,
        actor=story.actor,
        feature=story.feature,
        benefit=story.benefit,
        raw_text=story.raw_text,
        created_at=story.created_at,
        status=story.status,
    )


@router.get("/{story_id}/versions")
async def list_story_versions(
    story_id: UUID,
    current_user: User = Depends(get_current_user),
    repo: StoryRepoDep = None,  # type: ignore[assignment]
    project_repo: ProjectRepoDep = None,  # type: ignore[assignment]
    member_repo: MemberRepoDep = None,  # type: ignore[assignment]
    extraction_repo: ExtractionRepoDep = None,  # type: ignore[assignment]
) -> list[StoryVersionResponse]:
    """List every version of a user story, newest first, for the version selector.

    The user must be a member of the workspace that owns the story's project —
    the unchanged ``require_story_workspace_access`` walk, so a missing story is
    404 and a non-member is 403 ``NOT_A_WORKSPACE_MEMBER``, exactly the posture
    ``GET /{story_id}`` has; nothing about the workspace leaks into either body.

    The response is a **bare unpaginated array**: the list is the selector's
    pagination *input*, not a paginated resource, so the paginator's window must
    never truncate it. ``pending`` and ``failed`` runs are part of the history
    the user must see and are never filtered out. The two booleans are derived
    here, never stored: ``is_current`` marks the first ``completed`` entry of
    the ``version_number DESC`` list (a story with no completed run has no
    current entry — the legal frozen state), and ``has_output`` is
    ``status == completed``.
    """
    await require_story_workspace_access(
        story_id,
        current_user,
        story_repo=repo,
        project_repo=project_repo,
        member_repo=member_repo,
    )
    versions = await extraction_repo.list_versions(story_id)
    current_id = next(
        (v.id for v in versions if v.status == ExtractionStatus.COMPLETED),
        None,
    )
    return [
        StoryVersionResponse(
            id=v.id,
            version_number=v.version_number,
            status=v.status,
            model_used=v.model_used,
            provider=v.provider,
            temperature=v.temperature,
            created_at=v.created_at,
            completed_at=v.completed_at,
            error_info=v.error_info,
            is_current=v.id == current_id,
            has_output=v.status == ExtractionStatus.COMPLETED,
        )
        for v in versions
    ]


@router.get("/{story_id}/invalidations")
async def list_story_invalidations(
    story_id: UUID,
    current_user: User = Depends(get_current_user),
    repo: StoryRepoDep = None,  # type: ignore[assignment]
    project_repo: ProjectRepoDep = None,  # type: ignore[assignment]
    member_repo: MemberRepoDep = None,  # type: ignore[assignment]
    invalidation_repo: InvalidationRepoDep = None,  # type: ignore[assignment]
) -> list[StoryInvalidationResponse]:
    """List the story's active invalidation marks, newest first.

    The story-detail card renders one flag per task, so the page asks once for
    the story instead of once per task. The user must be a member of the
    workspace that owns the story's project — the unchanged
    ``require_story_workspace_access`` walk, so a missing story is 404 and a
    non-member is 403 ``NOT_A_WORKSPACE_MEMBER``, exactly the posture of
    ``GET /{story_id}/versions``. The gate is membership, not ownership: every
    member may read the record, the mutations are the gated half.

    The response is a **bare unpaginated array** like the versions read: the
    list is an input to the card, not a paginated resource. Every version of
    the story is included; the caller intersects the marks with the tasks it is
    displaying, so a frozen version's cards stay correct without a second
    query shape. Revoked marks are history and never appear here — they belong
    to ``GET /api/v1/tasks/{task_id}/invalidations``.
    """
    await require_story_workspace_access(
        story_id,
        current_user,
        story_repo=repo,
        project_repo=project_repo,
        member_repo=member_repo,
    )
    marks = await invalidation_repo.list_active_for_story(story_id)
    return [
        StoryInvalidationResponse(
            id=mark.id,
            task_id=mark.task_id,
            reason=mark.reason,
            marked_by=mark.marked_by,
            marked_at=mark.marked_at,
            revoked_by=mark.revoked_by,
            revoked_at=mark.revoked_at,
        )
        for mark in marks
    ]


@router.put("/{story_id}")
async def update_story(
    story_id: UUID,
    body: UpdateUserStoryRequest,
    current_user: User = Depends(get_current_user),
    repo: StoryRepoDep = None,  # type: ignore[assignment]
    project_repo: ProjectRepoDep = None,  # type: ignore[assignment]
    member_repo: MemberRepoDep = None,  # type: ignore[assignment]
) -> UserStoryResponse:
    """Update an existing user story.

    The user must be a member of the workspace that owns the story's project.
    """
    existing = await require_story_workspace_access(
        story_id,
        current_user,
        story_repo=repo,
        project_repo=project_repo,
        member_repo=member_repo,
    )

    kwargs: dict = {}
    if body.actor is not None:
        kwargs["actor"] = body.actor
    if body.feature is not None:
        kwargs["feature"] = body.feature
    if body.benefit is not None:
        kwargs["benefit"] = body.benefit
    if body.raw_text is not None:
        kwargs["raw_text"] = body.raw_text

    updated = replace(existing, **kwargs)
    result = await repo.save(updated)
    return UserStoryResponse(
        id=result.id,
        project_id=result.project_id,
        actor=result.actor,
        feature=result.feature,
        benefit=result.benefit,
        raw_text=result.raw_text,
        created_at=result.created_at,
        status=result.status,
    )


@router.delete("/{story_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_story(
    story_id: UUID,
    current_user: User = Depends(get_current_user),
    repo: StoryRepoDep = None,  # type: ignore[assignment]
    project_repo: ProjectRepoDep = None,  # type: ignore[assignment]
    member_repo: MemberRepoDep = None,  # type: ignore[assignment]
    ws_repo: WorkspaceRepoDep = None,  # type: ignore[assignment]
    extraction_repo: ExtractionRepoDep = None,  # type: ignore[assignment]
    vector_store: VectorStorePort | None = Depends(get_vector_store),
) -> None:
    """Delete a user story by its ID.

    Only the workspace owner or an ``ADMIN`` may delete: a plain ``MEMBER`` is
    refused with 403 ``WORKSPACE_OWNER_OR_ADMIN_REQUIRED``, a non-member keeps
    403 ``NOT_A_WORKSPACE_MEMBER``, and a missing story is 404. The deletion
    snapshots the story's versions, removes its vector points (when a vector
    store is configured) and then deletes the story and writes an audit record
    of the destroyed versions in one transaction. A vector store that cannot
    be reached answers 503 ``VECTOR_STORE_UNAVAILABLE`` and leaves the story,
    its versions and its tasks intact for a retry.
    """
    story = await require_story_owner_or_admin(
        story_id,
        current_user,
        story_repo=repo,
        project_repo=project_repo,
        member_repo=member_repo,
        ws_repo=ws_repo,
    )
    service = StoryDeletionService(
        story_repo=repo,
        extraction_repo=extraction_repo,
        project_repo=project_repo,
        vector_store=vector_store,
    )
    await service.delete_story(story, deleted_by=current_user.id)


# ═══════════════════════════════════════════════════════════════════
# CSV import
# ═══════════════════════════════════════════════════════════════════
#
# This route is workspace-scoped, like every newer feature in this API
# (``extraction_router``, ``projects_router``, ``export``): the workspace
# rides in the path and ``project_id`` stays a form field, matching both
# ``extraction_router`` (child resource id in the body) and ``create_story``
# (``project_id`` in the payload). The flat legacy router was the wrong home
# for an import that must resolve workspace membership before anything else.
#


@import_router.post(
    "/import",
    status_code=status.HTTP_201_CREATED,
    # The blocked-report path dumps its items with ``exclude_none=True``, so the success
    # path has to agree: without this the same duplicate item carries
    # ``existing_story_id: null`` on a 201 and omits the key entirely on a 422, and the
    # client would need two shapes for one contract.
    response_model_exclude_none=True,
)
async def import_stories(
    project_id: Annotated[UUID, Form()],
    file: UploadFile = File(...),
    ctx: tuple[Workspace, WorkspaceRole] = Depends(get_workspace_for_user),
    repo: StoryRepoDep = None,  # type: ignore[assignment]
    project_repo: ProjectRepoDep = None,  # type: ignore[assignment]
) -> StoryImportResponse:
    """Import user stories into a project from an uploaded CSV file.

    The workspace in the path must exist and the caller must be a member of
    it (``get_workspace_for_user``). The project must then belong to that
    same workspace. The upload is validated as a whole before anything is
    written: one blocking error anywhere answers ``422`` with the full error
    list and no story is created. Rows that duplicate an existing story (or
    an earlier row of the same upload) are skipped and reported, never fatal.
    """
    workspace, _ = ctx

    # Containment, not just membership: resolving the path workspace proves the caller
    # belongs to it, but says nothing about the project named in the form. Without this
    # check a member of workspace A could import into a project of workspace B by naming
    # A in the URL. Mirrors the 403 containment check in routes/extraction.py
    # (_validate_story_belongs_to_workspace).
    project = await project_repo.find_by_id(project_id)
    if project is None:
        raise EntityNotFound("Project", str(project_id))
    if project.workspace_id != workspace.id:
        raise ApiError(
            status_code=status.HTTP_403_FORBIDDEN,
            error_code=PROJECT_NOT_IN_WORKSPACE,
            detail="This project does not belong to the specified workspace",
        )

    # The cap bounds this handler's own work — parsing, validation and storage — not the wire
    # size. Starlette's multipart parser has already consumed the request body by the time this
    # runs, so the earlier claim that the file is sized "before reading the body" was wrong, and
    # the 413 body's own ``size`` field is the proof: 3145750 was only knowable after a read.
    #
    # ``file.size`` is checked first because Starlette populates it while spooling, so an
    # oversized upload is refused without a second full copy into this process. The check after
    # the read stays as the authoritative one: ``size`` can be absent, and only the bytes we
    # actually hold can be parsed.
    if file.size is not None and file.size > MAX_FILE_BYTES:
        raise ApiError(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            error_code="IMPORT_FILE_TOO_LARGE",
            detail={
                "detail": "The file is too large.",
                "size": file.size,
                "max": MAX_FILE_BYTES,
            },
        )

    data = await file.read()
    if len(data) > MAX_FILE_BYTES:
        raise ApiError(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            error_code="IMPORT_FILE_TOO_LARGE",
            detail={
                "detail": "The file is too large.",
                "size": len(data),
                "max": MAX_FILE_BYTES,
            },
        )

    try:
        parsed = parse_story_csv(data)
    except StoryCsvError as exc:
        detail = {
            "detail": "The file could not be read.",
            "reason": exc.reason,
        }
        # Only a limit reason carries a number: the client substitutes it into
        # "more than N lines", and absent-vs-present distinguishes the branch
        # (``typeof max === 'number'``), so it must not be a null placeholder.
        if exc.reason == "too_many_rows":
            detail["max"] = MAX_ROWS
        raise ApiError(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            error_code="IMPORT_FILE_REJECTED",
            detail=detail,
        ) from exc

    # One statement for the whole project, not one find_by_parts per row: the
    # duplicate check becomes an in-memory lookup against this single query.
    rows = await repo.list_parts_by_project(project_id)
    existing = {(a, f, b): str(sid) for a, f, b, sid in rows}

    import_rows = [
        ImportRow(
            line_number=row.line_number,
            actor=row.actor,
            feature=row.feature,
            benefit=row.benefit,
            raw_text=row.raw_text,
            field_count=row.field_count,
            expected_field_count=parsed.expected_field_count,
        )
        for row in parsed.rows
    ]
    report = validate_import(import_rows, parsed.mode, existing)

    # Nothing is written while any row has a blocking error: the caller gets
    # the whole error list back and can fix the file and retry from scratch.
    # Duplicates are not blocking — they are reported and skipped below.
    if report.blocked:
        raise ApiError(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            error_code="IMPORT_VALIDATION_FAILED",
            detail={
                "detail": "The file has rows that must be fixed.",
                "created": 0,
                "total_rows": report.total_rows,
                "errors": [
                    StoryImportErrorItem(
                        line=error.line_number,
                        reason=error.reason,
                        field=error.field,
                        length=error.actual_length,
                        max=error.max_length,
                        observed=error.observed_count,
                        expected=error.expected_count,
                    ).model_dump(exclude_none=True)
                    for error in report.errors
                ],
                "duplicates": [
                    StoryImportDuplicateItem(
                        line=dup.line_number,
                        reason=dup.reason,
                        existing_story_id=dup.existing_story_id,
                        first_line=dup.first_line,
                    ).model_dump(exclude_none=True)
                    for dup in report.duplicates
                ],
            },
        )

    stories = [
        UserStory(
            project_id=project_id,
            actor=s.actor,
            feature=s.feature,
            benefit=s.benefit,
            raw_text=s.raw_text,
        )
        for s in report.new_stories
    ]
    # One commit for the whole upload; with nothing new to create there is
    # nothing to save.
    saved = await repo.save_many(stories) if stories else []

    return StoryImportResponse(
        created=len(saved),
        skipped=len(report.duplicates),
        total_rows=report.total_rows,
        duplicates=[
            StoryImportDuplicateItem(
                line=dup.line_number,
                reason=dup.reason,
                existing_story_id=dup.existing_story_id,
                first_line=dup.first_line,
            )
            for dup in report.duplicates
        ],
        story_ids=[story.id for story in saved],
    )
