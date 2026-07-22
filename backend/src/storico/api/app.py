"""Storico FastAPI application factory."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from storico.api.errors import (
    cannot_remove_owner_handler,
    duplicate_entity_handler,
    entity_not_found_handler,
    generic_error_handler,
    insufficient_role_handler,
    last_admin_error_handler,
    llm_connection_error_handler,
    llm_model_not_found_handler,
    llm_response_error_handler,
    owner_transfer_error_handler,
    parse_error_handler,
    repository_error_handler,
)
from storico.api.routes import (
    auth,
    export,
    extraction,
    extractions,
    health,
    projects,
    stories,
    tasks,
    users,
    workspaces,
    workspace_settings,
)
from storico.api.routes import (
    settings as settings_routes,
)
from storico.config.settings import Settings
from storico.domain.entities import (
    CannotRemoveOwnerError,
    DuplicateEntity,
    EntityNotFound,
    InsufficientRole,
    LastAdminError,
    LLMConnectionError,
    LLMModelNotFoundError,
    LLMResponseError,
    OwnerTransferError,
    ParseError,
    RepositoryError,
)
from storico.infrastructure.database.base import dispose_engine, get_engine


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """FastAPI lifespan — initializes engine on startup and disposes on shutdown."""
    get_engine()

    # Recover any extractions that were left pending after a server crash
    try:
        from storico.infrastructure.tasks.extraction_task import recover_stuck_extractions

        await recover_stuck_extractions()
    except Exception:
        pass  # non-blocking — the API should still start

    yield
    dispose_engine()


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    settings = Settings.load()
    app = FastAPI(
        title="Storico API",
        version="0.1.0",
        lifespan=lifespan,
    )

    # CORS middleware
    origins = [o.strip() for o in settings.auth_allowed_origins.split(",") if o.strip()]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Exception handlers
    app.add_exception_handler(EntityNotFound, entity_not_found_handler)
    app.add_exception_handler(DuplicateEntity, duplicate_entity_handler)
    app.add_exception_handler(RepositoryError, repository_error_handler)
    app.add_exception_handler(LLMConnectionError, llm_connection_error_handler)
    app.add_exception_handler(LLMModelNotFoundError, llm_model_not_found_handler)
    app.add_exception_handler(LLMResponseError, llm_response_error_handler)
    app.add_exception_handler(ParseError, parse_error_handler)

    # Workspace exception handlers
    app.add_exception_handler(InsufficientRole, insufficient_role_handler)
    app.add_exception_handler(OwnerTransferError, owner_transfer_error_handler)
    app.add_exception_handler(LastAdminError, last_admin_error_handler)
    app.add_exception_handler(CannotRemoveOwnerError, cannot_remove_owner_handler)

    app.add_exception_handler(Exception, generic_error_handler)  # type: ignore[arg-type]

    # Routers
    app.include_router(health.router)
    app.include_router(auth.router)
    app.include_router(projects.router)
    app.include_router(stories.router)
    app.include_router(tasks.router)
    app.include_router(extractions.router)
    app.include_router(users.router)
    app.include_router(extraction.router)
    app.include_router(settings_routes.settings_router)
    app.include_router(settings_routes.test_router)

    # Workspace routes
    app.include_router(workspaces.router)
    app.include_router(workspace_settings.router)
    app.include_router(projects.projects_router)  # workspace-scoped
    app.include_router(extraction.extraction_router)  # workspace-scoped
    app.include_router(export.router)  # workspace-scoped

    return app


# Module-level instance for uvicorn (no --factory flag).
# Kept separate from create_app() so tests can still call create_app() directly.
app = create_app()
