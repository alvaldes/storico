"""Task CRUD API routes."""

from dataclasses import replace
from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status

from storico.api.dependencies import (
    get_current_user,
    get_repository,
    require_story_workspace_access,
    require_task_owner_or_admin,
    resolve_task_access,
)
from storico.api.error_codes import (
    NOT_A_WORKSPACE_MEMBER,
    REQUEST_VALIDATION_FAILED,
    TASK_ALREADY_MARKED,
    TASK_CREATION_ENDPOINT_REMOVED,
    TASK_DELETE_ENDPOINT_REMOVED,
    TASK_VERSION_FROZEN,
)
from storico.api.errors import ApiError
from storico.api.schemas.common import PaginatedResponse, PaginationParams
from storico.api.schemas.task import (
    CreateInvalidationRequest,
    InvalidationResponse,
    RepetitionMatch,
    RepetitionResponse,
    TaskResponse,
    UpdateTaskRequest,
)
from storico.application.services.task_service import (
    InvalidStateTransition,
    TaskService,
)
from storico.domain.entities import EntityNotFound, Task, User
from storico.domain.entities.extraction import Extraction
from storico.domain.entities.task_invalidation import TaskInvalidation
from storico.domain.services.task_title_normalizer import normalize_task_title
from storico.infrastructure.database.repositories import (
    SQLAlchemyExtractionRepository,
    SQLAlchemyProjectRepository,
    SQLAlchemyTaskInvalidationRepository,
    SQLAlchemyTaskRepository,
    SQLAlchemyUserStoryRepository,
)
from storico.infrastructure.database.repositories.workspace_member_repository import (
    SQLAlchemyWorkspaceMemberRepository,
)
from storico.infrastructure.database.repositories.workspace_repository import (
    SQLAlchemyWorkspaceRepository,
)

router = APIRouter(prefix="/api/v1/tasks", tags=["tasks"])

TaskRepoDep = Annotated[
    SQLAlchemyTaskRepository,
    Depends(get_repository(SQLAlchemyTaskRepository)),
]

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


async def _validate_task_workspace_access(
    task_id: UUID,
    current_user: User,
    task_repo: SQLAlchemyTaskRepository,
    story_repo: SQLAlchemyUserStoryRepository,
    project_repo: SQLAlchemyProjectRepository,
    member_repo: SQLAlchemyWorkspaceMemberRepository,
) -> Task:
    """Find a task and verify the user has access to its workspace.

    Thin caller of ``resolve_task_access``: the walk and its refusals live in
    ``api/dependencies.py``, unchanged. Returns the task if access is granted.
    Raises 404 or 403 otherwise.
    """
    access = await resolve_task_access(
        task_id,
        current_user,
        task_repo=task_repo,
        story_repo=story_repo,
        project_repo=project_repo,
        member_repo=member_repo,
    )
    return access.task


async def _frozen_version_state(
    task: Task, extraction_repo: SQLAlchemyExtractionRepository
) -> tuple[bool, Extraction | None]:
    """D21's frozen verdict for a task, plus the current version it was judged against.

    Frozen means: the story has no ``completed`` version at all, or the task
    belongs to a superseded one. Shared by ``update_task``'s dependencies guard
    and the invalidation mark/revoke guards; each caller keeps its own refusal
    wording, so ``update_task``'s 409 detail stays byte-identical.
    """
    current = await extraction_repo.find_current_version(task.user_story_id)
    frozen = current is None or task.extraction_id != current.id
    return frozen, current


@router.api_route(
    "/",
    methods=["POST"],
    status_code=status.HTTP_410_GONE,
    include_in_schema=False,
)
async def deprecated_create_task() -> None:
    """Retired endpoint — manual task creation is gone (410 Gone).

    A task is only ever born from an extraction run (design decision D3):
    revision ``0028`` made ``tasks.extraction_id`` ``NOT NULL``, so no
    hand-written task can be persisted. To produce tasks, extract the story
    again: POST /api/v1/workspaces/{workspace_id}/extract

    The handler reads no body and runs no authorization walk: the story id it
    used to authorize against lived in the deleted request body, so the
    retirement is the whole answer and it discloses nothing about any
    workspace.
    """
    raise ApiError(
        status_code=status.HTTP_410_GONE,
        error_code=TASK_CREATION_ENDPOINT_REMOVED,
        detail=(
            "Manual task creation has been removed. Tasks are only born from an "
            "extraction run (design decision D3): since revision 0028 every task "
            "row must belong to the run that extracted it. To create tasks, "
            "extract the story again via POST /api/v1/workspaces/{workspace_id}/extract."
        ),
    )


@router.get("/")
async def list_tasks(
    params: Annotated[PaginationParams, Depends()],
    current_user: User = Depends(get_current_user),
    repo: TaskRepoDep = None,  # type: ignore[assignment]
    story_repo: StoryRepoDep = None,  # type: ignore[assignment]
    project_repo: ProjectRepoDep = None,  # type: ignore[assignment]
    member_repo: MemberRepoDep = None,  # type: ignore[assignment]
    extraction_repo: ExtractionRepoDep = None,  # type: ignore[assignment]
    user_story_id: UUID | None = None,
    workspace_id: UUID | None = None,
    extraction_id: UUID | None = None,
) -> PaginatedResponse[TaskResponse]:
    """List tasks with optional filters and pagination.

    Filters:
    - ``user_story_id``: filter by user story (requires workspace membership).
      By default only the story's current version (the highest-numbered
      ``completed`` run) is answered; passing ``extraction_id`` reads exactly
      that version instead, so a superseded version's tasks stay addressable.
      A version that does not belong to the requested story — or does not
      exist — is refused with 422 ``REQUEST_VALIDATION_FAILED``.
    - ``workspace_id``: filter by workspace (requires workspace membership).

    ``extraction_id`` is a story-scoped question: supplying it without
    ``user_story_id`` is refused with 422 before any repository call (the
    repository's own ``ValueError`` for that shape is an internal invariant,
    not an HTTP contract).

    If neither scope filter is provided, returns tasks from all workspaces
    the current user is a member of.

    The page and its total come from one statement in the database —
    ``count(*) OVER ()`` rides on the rows' own query, so no separate
    ``SELECT COUNT(*)`` is issued. The order is ``created_at DESC, id DESC``,
    which makes the paging deterministic.
    """
    offset = (params.page - 1) * params.size
    # The shape refusal is the route's own answer and comes before every
    # branch: the repository raises ``ValueError`` for this same combination,
    # and letting that escape would surface as a 500 instead of a coded 422.
    if extraction_id is not None and user_story_id is None:
        raise ApiError(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            error_code=REQUEST_VALIDATION_FAILED,
            detail=(
                "extraction_id requires user_story_id: reading a named version "
                "is a story-scoped question."
            ),
        )
    # Validate workspace access
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
    elif user_story_id is not None:
        # Validate user has access to the user story's workspace
        await require_story_workspace_access(
            user_story_id,
            current_user,
            story_repo=story_repo,
            project_repo=project_repo,
            member_repo=member_repo,
        )
        if extraction_id is not None:
            # A named version is only honored when it belongs to the requested
            # story: a foreign or nonexistent id is a caller mistake, refused
            # with 422 — the same code FastAPI's own body validation uses —
            # rather than a 404 that would hint at which version ids exist.
            version = await extraction_repo.find_by_id(extraction_id)
            if version is None or version.user_story_id != user_story_id:
                raise ApiError(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    error_code=REQUEST_VALIDATION_FAILED,
                    detail=("extraction_id does not name a version of the requested user story."),
                )
        page, total = await repo.list_page(
            user_story_id=user_story_id,
            extraction_id=extraction_id,
            limit=params.size,
            offset=offset,
        )
    else:
        # No filter provided: return tasks from all workspaces the user is a member of
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
        TaskResponse(
            id=t.id,
            user_story_id=t.user_story_id,
            title=t.title,
            description=t.description,
            status=t.status,
            priority=t.priority,
            labels=t.labels,
            dependencies=t.dependencies,
            created_at=t.created_at,
            updated_at=t.updated_at,
        )
        for t in page
    ]
    return PaginatedResponse(
        items=items,
        total=total,
        page=params.page,
        size=params.size,
    )


@router.get("/{task_id}")
async def get_task(
    task_id: UUID,
    current_user: User = Depends(get_current_user),
    repo: TaskRepoDep = None,  # type: ignore[assignment]
    story_repo: StoryRepoDep = None,  # type: ignore[assignment]
    project_repo: ProjectRepoDep = None,  # type: ignore[assignment]
    member_repo: MemberRepoDep = None,  # type: ignore[assignment]
) -> TaskResponse:
    """Get a task by its ID.

    The user must be a member of the workspace that owns the task's user story project.
    """
    task = await _validate_task_workspace_access(
        task_id, current_user, repo, story_repo, project_repo, member_repo
    )
    return TaskResponse(
        id=task.id,
        user_story_id=task.user_story_id,
        title=task.title,
        description=task.description,
        status=task.status,
        priority=task.priority,
        labels=task.labels,
        dependencies=task.dependencies,
        created_at=task.created_at,
        updated_at=task.updated_at,
    )


@router.put("/{task_id}")
async def update_task(
    task_id: UUID,
    body: UpdateTaskRequest,
    current_user: User = Depends(get_current_user),
    repo: TaskRepoDep = None,  # type: ignore[assignment]
    story_repo: StoryRepoDep = None,  # type: ignore[assignment]
    project_repo: ProjectRepoDep = None,  # type: ignore[assignment]
    member_repo: MemberRepoDep = None,  # type: ignore[assignment]
    extraction_repo: ExtractionRepoDep = None,  # type: ignore[assignment]
) -> TaskResponse:
    """Update an existing task.

    The D5/D21 field matrix: ``status`` and ``labels`` are editable in every
    version state; ``dependencies`` is only editable while the task's version
    is the story's current one — a dependencies write on a frozen version is
    refused with 409 ``TASK_VERSION_FROZEN``. For ``labels`` and
    ``dependencies`` on an editable task:
    - ``None`` means keep existing values.
    - ``[]`` means clear the list.

    The user must be a member of the workspace that owns the task's user story project.
    """
    existing = await _validate_task_workspace_access(
        task_id, current_user, repo, story_repo, project_repo, member_repo
    )

    # The frozen guard keys on presence, not value: ``model_fields_set`` is
    # populated by an explicit ``"dependencies": null`` too, so the key alone
    # is a write attempt. ``current is None`` (no completed version) counts as
    # frozen — the conservative reading of design decision D21. The current-
    # version lookup is paid only when the body actually carries the
    # ``dependencies`` key: no keyless payload can observe the frozen verdict,
    # so a ``{"status": …}``-only board write must not spend the extra
    # statement the D21 tradeoff prices. When the key is present the refusal
    # still precedes the state-machine check below.
    if "dependencies" in body.model_fields_set:
        frozen, current = await _frozen_version_state(existing, extraction_repo)
        if frozen:
            if current is not None:
                reason = (
                    "Dependencies can only be edited on the story's current "
                    f"version (v{current.version_number}); this task belongs to a "
                    "superseded version."
                )
            else:
                reason = (
                    "Dependencies can only be edited on the story's current "
                    "version, but this story has no current version: no completed "
                    "extraction exists for it."
                )
            raise ApiError(
                status_code=status.HTTP_409_CONFLICT,
                error_code=TASK_VERSION_FROZEN,
                detail={
                    "detail": reason,
                    "current_version": current.version_number if current else None,
                },
            )

    # Validate status transition if status is being updated
    if body.status is not None:
        try:
            TaskService(repo).ensure_transition_allowed(existing.status, body.status)
        except InvalidStateTransition as exc:
            raise ApiError(
                status_code=status.HTTP_400_BAD_REQUEST,
                error_code="INVALID_STATE_TRANSITION",
                detail={
                    "detail": "Invalid state transition",
                    "current_state": exc.current_state.value,
                    "attempted_state": exc.attempted_state.value,
                    "allowed_transitions": [s.value for s in exc.allowed_transitions],
                },
            ) from exc

    kwargs: dict = {"updated_at": datetime.now(UTC)}
    if body.status is not None:
        kwargs["status"] = body.status
    if body.labels is not None:
        kwargs["labels"] = body.labels
    if body.dependencies is not None:
        kwargs["dependencies"] = body.dependencies

    updated = replace(existing, **kwargs)
    result = await repo.save(updated)
    return TaskResponse(
        id=result.id,
        user_story_id=result.user_story_id,
        title=result.title,
        description=result.description,
        status=result.status,
        priority=result.priority,
        labels=result.labels,
        dependencies=result.dependencies,
        created_at=result.created_at,
        updated_at=result.updated_at,
    )


@router.api_route(
    "/{task_id}",
    methods=["DELETE"],
    status_code=status.HTTP_410_GONE,
    include_in_schema=False,
)
async def deprecated_delete_task(
    task_id: UUID,
    current_user: User = Depends(get_current_user),
    repo: TaskRepoDep = None,  # type: ignore[assignment]
    story_repo: StoryRepoDep = None,  # type: ignore[assignment]
    project_repo: ProjectRepoDep = None,  # type: ignore[assignment]
    member_repo: MemberRepoDep = None,  # type: ignore[assignment]
) -> None:
    """Retired endpoint — single-task deletion is gone (410 Gone).

    No product path deletes a single task (design decision D12): a task
    belongs to a version of its story and is only ever destroyed together with
    that story.

    The membership walk is unchanged, so a missing task still answers 404 and a
    non-member still answers 403 ``NOT_A_WORKSPACE_MEMBER`` before the
    retirement is ever reached — the retired door teaches a caller nothing
    about a workspace they are not in.
    """
    await _validate_task_workspace_access(
        task_id, current_user, repo, story_repo, project_repo, member_repo
    )
    raise ApiError(
        status_code=status.HTTP_410_GONE,
        error_code=TASK_DELETE_ENDPOINT_REMOVED,
        detail=(
            "Single-task deletion has been removed. No product path deletes a "
            "single task (design decision D12): a task belongs to a version of "
            "its story and is only ever destroyed together with that story."
        ),
    )


def _frozen_refusal_detail(action: str, current: Extraction | None) -> dict:
    """The 409 body the mark and revoke guards answer with on a frozen version.

    Same shape as ``update_task``'s frozen detail — a readable reason plus the
    story's current version number — but worded for the mark, whose refusal is
    not about editing dependencies.
    """
    if current is not None:
        reason = (
            f"The task can only be {action} while it belongs to the story's "
            f"current version (v{current.version_number}); this task belongs to "
            "a superseded version."
        )
    else:
        reason = (
            f"The task can only be {action} while it belongs to the story's "
            "current version, but this story has no current version: no "
            "completed extraction exists for it."
        )
    return {
        "detail": reason,
        "current_version": current.version_number if current else None,
    }


@router.post("/{task_id}/invalidations", status_code=status.HTTP_201_CREATED)
async def create_invalidation(
    task_id: UUID,
    body: CreateInvalidationRequest,
    current_user: User = Depends(get_current_user),
    repo: TaskRepoDep = None,  # type: ignore[assignment]
    story_repo: StoryRepoDep = None,  # type: ignore[assignment]
    project_repo: ProjectRepoDep = None,  # type: ignore[assignment]
    member_repo: MemberRepoDep = None,  # type: ignore[assignment]
    ws_repo: WorkspaceRepoDep = None,  # type: ignore[assignment]
    extraction_repo: ExtractionRepoDep = None,  # type: ignore[assignment]
    invalidation_repo: InvalidationRepoDep = None,  # type: ignore[assignment]
) -> InvalidationResponse:
    """Mark the task invalid, with a reason, as the current user.

    Gated to the workspace owner or an admin. A blank reason never reaches the
    handler — ``CreateInvalidationRequest`` refuses it at body validation with
    422 ``REQUEST_VALIDATION_FAILED``. The refusal order is the design's: the
    frozen check first, then the active-mark read — resolved through
    ``find_active_by_task`` **before** any write, so a second active mark is a
    designed 409 ``TASK_ALREADY_MARKED`` carrying the live mark's reason, and
    the table's partial unique index stays the lost-race backstop it is, not
    the contract. Revoking is the only way a mark stops being active.
    """
    task = await require_task_owner_or_admin(
        task_id,
        current_user,
        task_repo=repo,
        story_repo=story_repo,
        project_repo=project_repo,
        member_repo=member_repo,
        ws_repo=ws_repo,
    )
    frozen, current = await _frozen_version_state(task, extraction_repo)
    if frozen:
        raise ApiError(
            status_code=status.HTTP_409_CONFLICT,
            error_code=TASK_VERSION_FROZEN,
            detail=_frozen_refusal_detail("marked", current),
        )
    active = await invalidation_repo.find_active_by_task(task_id)
    if active is not None:
        raise ApiError(
            status_code=status.HTTP_409_CONFLICT,
            error_code=TASK_ALREADY_MARKED,
            detail=active.reason,
        )
    mark = await invalidation_repo.create(
        TaskInvalidation(task_id=task_id, reason=body.reason, marked_by=current_user.id)
    )
    return InvalidationResponse(
        id=mark.id,
        reason=mark.reason,
        marked_by=mark.marked_by,
        marked_at=mark.marked_at,
        revoked_by=mark.revoked_by,
        revoked_at=mark.revoked_at,
    )


@router.get("/{task_id}/invalidations")
async def list_invalidations(
    task_id: UUID,
    current_user: User = Depends(get_current_user),
    repo: TaskRepoDep = None,  # type: ignore[assignment]
    story_repo: StoryRepoDep = None,  # type: ignore[assignment]
    project_repo: ProjectRepoDep = None,  # type: ignore[assignment]
    member_repo: MemberRepoDep = None,  # type: ignore[assignment]
    invalidation_repo: InvalidationRepoDep = None,  # type: ignore[assignment]
) -> list[InvalidationResponse]:
    """The task's full mark history, active mark first.

    Membership-only: every member may read the record, the gate is on the
    mutations. Revoked rows are part of the history and carry their
    ``revoked_by``/``revoked_at`` attribution.
    """
    await _validate_task_workspace_access(
        task_id, current_user, repo, story_repo, project_repo, member_repo
    )
    marks = await invalidation_repo.list_by_task(task_id)
    return [
        InvalidationResponse(
            id=mark.id,
            reason=mark.reason,
            marked_by=mark.marked_by,
            marked_at=mark.marked_at,
            revoked_by=mark.revoked_by,
            revoked_at=mark.revoked_at,
        )
        for mark in marks
    ]


@router.delete("/{task_id}/invalidations/current", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_invalidation(
    task_id: UUID,
    current_user: User = Depends(get_current_user),
    repo: TaskRepoDep = None,  # type: ignore[assignment]
    story_repo: StoryRepoDep = None,  # type: ignore[assignment]
    project_repo: ProjectRepoDep = None,  # type: ignore[assignment]
    member_repo: MemberRepoDep = None,  # type: ignore[assignment]
    ws_repo: WorkspaceRepoDep = None,  # type: ignore[assignment]
    extraction_repo: ExtractionRepoDep = None,  # type: ignore[assignment]
    invalidation_repo: InvalidationRepoDep = None,  # type: ignore[assignment]
) -> None:
    """Revoke the task's active mark — an UPDATE of the row, never a DELETE.

    Gated to the workspace owner or an admin. The row that answers 404 is the
    active mark ``find_active_by_task`` resolves: no active mark means nothing
    to revoke. The row's reason, ``marked_by`` and ``marked_at`` stay intact —
    the revoke history is the record.
    """
    task = await require_task_owner_or_admin(
        task_id,
        current_user,
        task_repo=repo,
        story_repo=story_repo,
        project_repo=project_repo,
        member_repo=member_repo,
        ws_repo=ws_repo,
    )
    frozen, current = await _frozen_version_state(task, extraction_repo)
    if frozen:
        raise ApiError(
            status_code=status.HTTP_409_CONFLICT,
            error_code=TASK_VERSION_FROZEN,
            detail=_frozen_refusal_detail("revoked", current),
        )
    active = await invalidation_repo.find_active_by_task(task_id)
    if active is None:
        raise EntityNotFound("TaskInvalidation", str(task_id))
    await invalidation_repo.revoke(
        active.id, revoked_by=current_user.id, revoked_at=datetime.now(UTC)
    )


@router.get("/{task_id}/invalidations/repetition")
async def find_repetition(
    task_id: UUID,
    current_user: User = Depends(get_current_user),
    repo: TaskRepoDep = None,  # type: ignore[assignment]
    story_repo: StoryRepoDep = None,  # type: ignore[assignment]
    project_repo: ProjectRepoDep = None,  # type: ignore[assignment]
    member_repo: MemberRepoDep = None,  # type: ignore[assignment]
    invalidation_repo: InvalidationRepoDep = None,  # type: ignore[assignment]
) -> RepetitionResponse:
    """Warn on marks of the story's other versions whose title repeats this task's.

    The D16 read, and deliberately nothing more: the title is resolved
    server-side from the task id (the endpoint accepts no arbitrary text), the
    SQL narrows to the story's other versions' active marks, and the match is
    an exact comparison of ``normalize_task_title`` outputs — casefold plus
    whitespace collapse. No fuzzy, no vector, no prefix, and no write: the read
    creates, updates and revokes nothing.
    """
    task = await _validate_task_workspace_access(
        task_id, current_user, repo, story_repo, project_repo, member_repo
    )
    candidates = await invalidation_repo.list_active_on_other_versions(
        user_story_id=task.user_story_id, exclude_extraction_id=task.extraction_id
    )
    normalized = normalize_task_title(task.title)
    matches = [
        RepetitionMatch(
            version_number=candidate.version_number,
            reason=candidate.reason,
            marked_at=candidate.marked_at,
        )
        for candidate in candidates
        if normalize_task_title(candidate.title) == normalized
    ]
    return RepetitionResponse(matches=matches)
