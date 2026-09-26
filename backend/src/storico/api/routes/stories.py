"""UserStory CRUD API routes."""

from dataclasses import replace
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status

from storico.api.dependencies import (
    get_current_user,
    get_repository,
    require_story_workspace_access,
)
from storico.api.schemas.common import PaginatedResponse, PaginationParams
from storico.api.schemas.story import (
    CreateUserStoryRequest,
    StoryImportDuplicateItem,
    StoryImportErrorItem,
    StoryImportResponse,
    UpdateUserStoryRequest,
    UserStoryResponse,
)
from storico.domain.entities import EntityNotFound, User, UserStory
from storico.domain.services.story_import import ImportRow, validate_import
from storico.infrastructure.database.repositories import (
    SQLAlchemyProjectRepository,
    SQLAlchemyUserStoryRepository,
)
from storico.infrastructure.database.repositories.workspace_member_repository import (
    SQLAlchemyWorkspaceMemberRepository,
)
from storico.infrastructure.parsers.story_csv import MAX_FILE_BYTES, StoryCsvError, parse_story_csv

router = APIRouter(prefix="/api/v1/stories", tags=["stories"])

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
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not a member of this workspace",
        )

    # Check for duplicate story in the same project (by actor, feature, benefit)
    existing_story = await repo.find_by_parts(
        body.project_id, body.actor, body.feature, body.benefit
    )
    if existing_story is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
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
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
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
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
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
) -> None:
    """Delete a user story by its ID.

    The user must be a member of the workspace that owns the story's project.
    """
    await require_story_workspace_access(
        story_id,
        current_user,
        story_repo=repo,
        project_repo=project_repo,
        member_repo=member_repo,
    )
    await repo.delete(story_id)


# ═══════════════════════════════════════════════════════════════════
# CSV import
# ═══════════════════════════════════════════════════════════════════
#
# This route lives on the stories router, not under ``/api/v1/projects/{project_id}/...``.
# The obvious nested path is unreachable by construction: ``projects.router`` carries a
# legacy catch-all (``/{path:path}`` -> 410 Gone, ``routes/projects.py:39``) because
# non-workspace-scoped project routes were retired on purpose, and it is registered first
# in ``app.py``. Measured: a request to the nested path answered 410 with the retirement
# message, with the route present in the OpenAPI schema and the app starting cleanly.
#
# Registering the import before the catch-all would work and would also make correctness
# depend on registration order — the exact invisible mechanism that produced the 410. And
# the retired prefix means "gone", so a live route there disagrees with the decision that
# put it there. ``POST /api/v1/stories/import`` needs no ordering trick and matches the
# sibling it belongs to: ``create_story`` also takes ``project_id`` from the request body.


@router.post(
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
    current_user: User = Depends(get_current_user),
    repo: StoryRepoDep = None,  # type: ignore[assignment]
    project_repo: ProjectRepoDep = None,  # type: ignore[assignment]
    member_repo: MemberRepoDep = None,  # type: ignore[assignment]
) -> StoryImportResponse:
    """Import user stories into a project from an uploaded CSV file.

    The upload is validated as a whole before anything is written: one
    blocking error anywhere answers ``422`` with the full error list and no
    story is created. Rows that duplicate an existing story (or an earlier
    row of the same upload) are skipped and reported, never fatal.
    """
    # Access checks mirror create_story: the project must exist and the
    # caller must belong to its workspace.
    project = await project_repo.find_by_id(project_id)
    if project is None:
        raise EntityNotFound("Project", str(project_id))

    member = await member_repo.find_by_workspace_and_user(project.workspace_id, current_user.id)
    if member is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not a member of this workspace",
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
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail={
                "detail": "The file is too large.",
                "error_code": "IMPORT_FILE_TOO_LARGE",
                "size": file.size,
                "max": MAX_FILE_BYTES,
            },
        )

    data = await file.read()
    if len(data) > MAX_FILE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail={
                "detail": "The file is too large.",
                "error_code": "IMPORT_FILE_TOO_LARGE",
                "size": len(data),
                "max": MAX_FILE_BYTES,
            },
        )

    try:
        parsed = parse_story_csv(data)
    except StoryCsvError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={
                "detail": "The file could not be read.",
                "error_code": "IMPORT_FILE_REJECTED",
                "reason": exc.reason,
            },
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
        )
        for row in parsed.rows
    ]
    report = validate_import(import_rows, parsed.mode, existing)

    # Nothing is written while any row has a blocking error: the caller gets
    # the whole error list back and can fix the file and retry from scratch.
    # Duplicates are not blocking — they are reported and skipped below.
    if report.blocked:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={
                "detail": "The file has rows that must be fixed.",
                "error_code": "IMPORT_VALIDATION_FAILED",
                "created": 0,
                "total_rows": report.total_rows,
                "errors": [
                    StoryImportErrorItem(
                        line=error.line_number,
                        reason=error.reason,
                        field=error.field,
                        length=error.actual_length,
                        max=error.max_length,
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
