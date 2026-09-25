"""Storico FastAPI application factory."""

import logging
import logging.config
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from storico.api.errors import (
    cannot_remove_owner_handler,
    cipher_error_handler,
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
    workspace_settings,
    workspaces,
)
from storico.api.routes import (
    settings as settings_routes,
)
from storico.api.version import package_version
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
from storico.domain.entities.exceptions import CipherError
from storico.infrastructure.database.base import dispose_engine, get_engine

logger = logging.getLogger(__name__)


def _configure_logging(settings: Settings) -> None:
    """Configure application logging for the process.

    Lives inside ``create_app()`` — never at import time: importing this module
    must leave logging untouched, so the logging configuration is a decision
    the application factory makes, not an import side effect.

    The config owns only the root logger. Uvicorn configures ``uvicorn``,
    ``uvicorn.error`` and ``uvicorn.access`` with their own handlers and
    ``propagate=False``; with ``disable_existing_loggers=False`` those are
    left exactly as uvicorn set them, so server logs keep working and an
    application record cannot be printed twice (the ``storico.*`` chain has
    no dedicated handler — records travel once to the root's handler).

    Re-running ``dictConfig`` (a second ``create_app()``) replaces the
    previous configuration instead of stacking handlers, so calling the
    factory twice is safe.
    """
    logging.config.dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "storico_console": {
                    "format": "%(asctime)s %(levelname)-8s %(name)s — %(message)s",
                },
            },
            "handlers": {
                "storico_console": {
                    "class": "logging.StreamHandler",
                    "formatter": "storico_console",
                    "stream": "ext://sys.stderr",
                },
            },
            "root": {
                "handlers": ["storico_console"],
                "level": settings.log_level,
            },
        }
    )


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """FastAPI lifespan — initializes engine on startup and disposes on shutdown."""
    get_engine()

    # Recover any extractions that were left pending after a server crash.
    # Non-blocking by design — the API must still start even if recovery
    # fails — but failures must be visible in the logs so the operator can
    # investigate stuck extractions instead of debugging a silent skip.
    try:
        from storico.infrastructure.tasks.extraction_task import recover_stuck_extractions

        await recover_stuck_extractions()
    except Exception:
        logger.exception("recover_stuck_extractions failed")

    yield
    dispose_engine()


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    settings = Settings.load()
    _configure_logging(settings)
    app = FastAPI(
        title="Storico API",
        version=package_version(),
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

    # Credential cipher errors. Registered on the base class so both subclasses are covered;
    # the handler itself distinguishes them for the machine-readable ``error_code``.
    app.add_exception_handler(CipherError, cipher_error_handler)

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


def __getattr__(name: str) -> FastAPI:
    """Lazily expose the module-level ``app`` instance (PEP 562).

    Historically this module bound ``app = create_app()`` at import time,
    which made importing the module configure logging as a side effect. The
    attribute is now resolved on first access, so the documented entrypoints
    keep working — ``uvicorn storico.api.app:app`` and
    ``from storico.api.app import app`` — while importing the module alone
    leaves logging untouched.

    The instance is written back into the module namespace, which is what
    makes it a singleton again: ``__getattr__`` is only consulted on a miss,
    so the first access builds the app and every later access reads the global
    instead of building a second one. Without that write the module would hand
    out a fresh app — and re-run the logging configuration — per access, which
    is not what the previous module-level binding did.
    """
    if name == "app":
        instance = create_app()
        globals()["app"] = instance
        return instance
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
