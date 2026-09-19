"""FastAPI dependency injection utilities for Storico API."""

import logging
from collections.abc import Awaitable, Callable
from typing import Annotated
from uuid import UUID

import jwt as pyjwt  # PyJWT library
from fastapi import Depends, HTTPException, Path, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from storico.config.settings import Settings, get_settings
from storico.domain.entities import EntityNotFound, User, UserStory
from storico.domain.entities.workspace import Workspace
from storico.domain.entities.workspace_member import WorkspaceRole
from storico.domain.ports import CipherPort, EmbeddingPort, UserRepository, VectorStorePort
from storico.domain.ports.workspace_member_repository import WorkspaceMemberRepository
from storico.domain.ports.workspace_repository import WorkspaceRepository
from storico.infrastructure.cache.user_cache import get_cached_user, set_cached_user
from storico.infrastructure.crypto import FernetCipher
from storico.infrastructure.database.repositories import (
    SQLAlchemyProjectRepository,
    SQLAlchemyUserRepository,
    SQLAlchemyUserStoryRepository,
    SQLAlchemyWorkspaceLLMConfigRepository,
)
from storico.infrastructure.database.repositories.workspace_member_repository import (
    SQLAlchemyWorkspaceMemberRepository,
)
from storico.infrastructure.database.repositories.workspace_repository import (
    SQLAlchemyWorkspaceRepository,
)
from storico.infrastructure.database.session import get_session
from storico.infrastructure.llm import (
    PromptManager,
    TaskParser,
)
from storico.infrastructure.vector import QdrantAdapter, get_embedding_port

logger = logging.getLogger(__name__)


def get_repository[RepoType](
    repo_class: Callable[[AsyncSession], RepoType],
) -> Callable[..., Awaitable[RepoType]]:
    """Factory that returns a FastAPI dependency for the given repository class.

    Usage::

        from fastapi import APIRouter, Depends
        from storico.api.dependencies import get_repository
        from storico.infrastructure.database.repositories.project import ProjectRepository

        router = APIRouter()

        @router.get("/projects/{project_id}")
        async def get_project(
            repo: ProjectRepository = Depends(get_repository(ProjectRepository)),
        ):
            ...

    The returned dependency resolves an ``AsyncSession`` and injects it into the
    repository constructor on every request.
    """

    async def _get_repo(
        session: Annotated[AsyncSession, Depends(get_session)],
    ) -> RepoType:
        return repo_class(session)

    return _get_repo


async def get_current_user(
    request: Request,
    repo: UserRepository = Depends(get_repository(SQLAlchemyUserRepository)),
) -> User:
    """Validate JWT from Authorization header and return the authenticated user.

    Extracts and verifies a JWT from the ``Authorization: Bearer <token>``
    header, then looks up the user identified by the ``sub`` claim.
    """
    settings = get_settings()

    # Extract Bearer token
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing authentication token",
        )

    token = auth_header.removeprefix("Bearer ")

    # Decode JWT
    try:
        payload = pyjwt.decode(token, settings.auth_jwt_secret, algorithms=["HS256"])
        user_id = payload.get("sub")
        if not user_id:
            raise ValueError("Missing sub claim")
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing authentication token",
        )

    # Look up user — check in-process cache first (TTL 30s) to skip the
    # DB round-trip on repeated requests from the same user. The cache is
    # process-local and per-user_id; correctness always falls back to the
    # repository lookup on miss/expiry. Endpoints that mutate the user
    # (PATCH /users/me/onboarding) call invalidate_user() so subsequent
    # calls re-read from the DB.
    user = get_cached_user(user_id)
    if user is None:
        try:
            user = await repo.find_by_id(UUID(user_id))
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or missing authentication token",
            )
        if user is not None:
            set_cached_user(user_id, user)

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing authentication token",
        )

    return user


def get_prompt_manager() -> PromptManager:
    """Factory for the prompt manager."""
    return PromptManager()


def get_cipher() -> CipherPort:
    """Factory for the credential cipher, keyed by the configured master key.

    A missing ``encryption_key`` produces a cipher that refuses to encrypt rather than an
    error here: the process has to be able to *hold* that state so the refusal surfaces at
    the write that would otherwise store a plaintext credential, not at startup.
    """
    return FernetCipher(Settings.load().encryption_key)


def get_llm_config_repository(
    session: Annotated[AsyncSession, Depends(get_session)],
    cipher: Annotated[CipherPort, Depends(get_cipher)],
) -> SQLAlchemyWorkspaceLLMConfigRepository:
    """Factory for the workspace LLM config repository.

    Deliberately not built with ``get_repository``: that factory injects only a session,
    and this repository needs the cipher too. The cipher arrives as an explicit
    dependency rather than as a module-level singleton the repository reaches for, so a
    test — or a future key rotation — can substitute it per request.
    """
    return SQLAlchemyWorkspaceLLMConfigRepository(session, cipher)


def get_task_parser() -> TaskParser:
    """Factory for the task parser."""
    return TaskParser()


def get_embedding_port_() -> EmbeddingPort:
    """Factory for the active embedding port (Ollama / Google / OpenAI)."""
    return get_embedding_port(get_settings())


def get_vector_store(
    embedding_port: EmbeddingPort = Depends(get_embedding_port_),
) -> VectorStorePort | None:
    """Factory for the Qdrant vector store.

    Returns None if Qdrant is not configured (graceful degradation).
    """
    try:
        settings = get_settings()
        return QdrantAdapter(
            embedding_port=embedding_port,
            qdrant_url=settings.qdrant_url,
            qdrant_api_key=settings.qdrant_api_key,
            collection_name=settings.qdrant_collection,
            vector_size=settings.embedding_dimensions,
        )
    except Exception:
        logger.warning("Failed to create QdrantAdapter, RAG disabled")
        return None


# ── Workspace dependencies ──────────────────────────────────────────


async def get_workspace_for_user(
    workspace_id: UUID = Path(...),
    current_user: User = Depends(get_current_user),
    ws_repo: WorkspaceRepository = Depends(get_repository(SQLAlchemyWorkspaceRepository)),
    member_repo: WorkspaceMemberRepository = Depends(
        get_repository(SQLAlchemyWorkspaceMemberRepository)
    ),
) -> tuple[Workspace, WorkspaceRole]:
    """Resolve workspace and validate membership.

    Returns ``(Workspace, WorkspaceRole)`` if the user is a member.
    Raises 404 if the workspace does not exist (no 403 — avoids leaking
    existence to non-members).
    Raises 403 if the user is authenticated but not a member.
    """
    workspace = await ws_repo.find_by_id(workspace_id)
    if workspace is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Workspace with id '{workspace_id}' not found",
        )

    member = await member_repo.find_by_workspace_and_user(workspace_id, current_user.id)
    if member is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not a member of this workspace",
        )

    return (workspace, member.role)


async def require_admin(
    ctx: tuple[Workspace, WorkspaceRole] = Depends(get_workspace_for_user),
) -> tuple[Workspace, WorkspaceRole]:
    """Require admin role for the current workspace.

    Must be chained after ``get_workspace_for_user``.
    Raises 403 if the user is not an admin.
    """
    workspace, role = ctx
    if role != WorkspaceRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    return ctx


async def require_owner(
    ctx: tuple[Workspace, WorkspaceRole] = Depends(require_admin),
    current_user: User = Depends(get_current_user),
) -> Workspace:
    """Require workspace ownership (for transfer operations).

    Must be chained after ``require_admin``.
    Raises 403 if the authenticated user is not the workspace owner.
    """
    workspace, _ = ctx
    if workspace.owner_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the workspace owner can perform this action",
        )
    return workspace


async def require_story_workspace_access(
    story_id: UUID,
    current_user: User,
    *,
    story_repo: SQLAlchemyUserStoryRepository,
    project_repo: SQLAlchemyProjectRepository,
    member_repo: SQLAlchemyWorkspaceMemberRepository,
    reported_as: tuple[str, UUID] | None = None,
) -> UserStory:
    """Resolve a story's workspace and require the caller to be a member of it.

    The story -> project -> workspace walk that every task, story and extraction route
    needs. Every failure is reported as a miss of the *caller's* head entity
    (``reported_as``), so a route never tells the caller whether the story, its project,
    or their own membership was the problem.

    Raises ``EntityNotFound`` (404) for a missing story or project and ``HTTPException``
    (403) for a missing membership.
    """
    label, report_id = reported_as or ("UserStory", story_id)
    story = await story_repo.find_by_id(story_id)
    if story is None:
        raise EntityNotFound(label, str(report_id))
    project = await project_repo.find_by_id(story.project_id)
    if project is None:
        raise EntityNotFound(label, str(report_id))
    member = await member_repo.find_by_workspace_and_user(project.workspace_id, current_user.id)
    if member is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not a member of this workspace",
        )
    return story
