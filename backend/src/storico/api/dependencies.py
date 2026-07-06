"""FastAPI dependency injection utilities for Storico API."""

from collections.abc import Awaitable, Callable
from typing import Annotated
from uuid import UUID

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from storico.application.extraction import ExtractFromStoryUseCase
from storico.domain.entities import User
from storico.domain.ports import LLMPort, UserRepository
from storico.domain.services.extraction_judge_service import LLMJudgeService
from storico.domain.services.extraction_service import ExtractionService
from storico.infrastructure.database.repositories import (
    SQLAlchemyExtractionRepository,
    SQLAlchemyTaskRepository,
    SQLAlchemyUserRepository,
    SQLAlchemyUserStoryRepository,
)
from storico.infrastructure.database.session import get_session
from storico.infrastructure.llm import OllamaAdapter, PromptManager, TaskParser


def get_repository[RepoType](repo_class: type[RepoType]) -> Callable[..., Awaitable[RepoType]]:
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


INTERNAL_TOKEN_HEADER = "X-Storico-Internal-Token"
USER_ID_HEADER = "X-Storico-User-Id"


async def get_current_user(
    request: Request,
    repo: UserRepository = Depends(get_repository(SQLAlchemyUserRepository)),
) -> User:
    """Validate trusted proxy headers and return the authenticated user.

    Requires both X-Storico-Internal-Token (shared secret) and
    X-Storico-User-Id (user UUID set by Astro proxy).
    """
    from storico.config.settings import Settings  # late import to avoid circular

    settings = Settings.load()

    # Validate internal token
    token = request.headers.get(INTERNAL_TOKEN_HEADER)
    if not token or token != settings.auth_internal_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing authentication token",
        )

    # Extract user ID
    user_id = request.headers.get(USER_ID_HEADER)
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing user identification",
        )

    # Look up user
    try:
        user = await repo.find_by_id(UUID(user_id))
    except ValueError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)

    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)

    return user


def get_llm_port() -> LLMPort:
    """Factory for the LLM port — returns an ``OllamaAdapter``."""
    from storico.config.settings import Settings  # late import to avoid circular

    settings = Settings.load()
    return OllamaAdapter(base_url=settings.ollama_host)


def get_prompt_manager() -> PromptManager:
    """Factory for the prompt manager."""
    return PromptManager()


def get_task_parser() -> TaskParser:
    """Factory for the task parser."""
    return TaskParser()


def get_extract_use_case(
    llm_port: LLMPort = Depends(get_llm_port),
    prompt_manager: PromptManager = Depends(get_prompt_manager),
    task_parser: TaskParser = Depends(get_task_parser),
    session: AsyncSession = Depends(get_session),
) -> ExtractFromStoryUseCase:
    """Factory for ``ExtractFromStoryUseCase`` with all dependencies wired."""
    extraction_repo = SQLAlchemyExtractionRepository(session)
    task_repo = SQLAlchemyTaskRepository(session)
    story_repo = SQLAlchemyUserStoryRepository(session)

    judge_service = LLMJudgeService(
        llm_port=llm_port,
        prompt_manager=prompt_manager,
    )
    extraction_service = ExtractionService(
        llm_port=llm_port,
        prompt_manager=prompt_manager,
        task_parser=task_parser,
        extraction_repo=extraction_repo,
        task_repo=task_repo,
        judge_service=judge_service,
    )
    return ExtractFromStoryUseCase(
        extraction_service=extraction_service,
        story_repo=story_repo,
    )
