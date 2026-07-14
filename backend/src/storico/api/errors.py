"""FastAPI exception handlers for domain-level errors."""

from fastapi import Request
from fastapi.responses import JSONResponse

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


async def entity_not_found_handler(
    request: Request,
    exc: EntityNotFound,
) -> JSONResponse:
    """Maps ``EntityNotFound`` to a 404 JSON response."""
    return JSONResponse(
        status_code=404,
        content={"detail": str(exc), "type": "entity_not_found"},
    )


async def duplicate_entity_handler(
    request: Request,
    exc: DuplicateEntity,
) -> JSONResponse:
    """Maps ``DuplicateEntity`` to a 409 JSON response."""
    return JSONResponse(
        status_code=409,
        content={"detail": str(exc), "type": "duplicate_entity"},
    )


async def repository_error_handler(
    request: Request,
    exc: RepositoryError,
) -> JSONResponse:
    """Maps ``RepositoryError`` to a 500 JSON response (without leaking internals)."""
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error", "type": "repository_error"},
    )


async def generic_error_handler(
    request: Request,
    exc: Exception,  # noqa: BLE001
) -> JSONResponse:
    """Catches any unhandled exception and returns a safe 500 response."""
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error", "type": "internal_error"},
    )


async def llm_connection_error_handler(
    request: Request,
    exc: LLMConnectionError,
) -> JSONResponse:
    """Maps ``LLMConnectionError`` to a 503 JSON response."""
    return JSONResponse(
        status_code=503,
        content={
            "detail": "LLM service unavailable",
            "type": "llm_connection_error",
            "message": str(exc),
        },
    )


async def llm_model_not_found_handler(
    request: Request,
    exc: LLMModelNotFoundError,
) -> JSONResponse:
    """Maps ``LLMModelNotFoundError`` to a 404 JSON response."""
    return JSONResponse(
        status_code=404,
        content={
            "detail": str(exc),
            "type": "llm_model_not_found",
            "model": exc.model,
        },
    )


async def llm_response_error_handler(
    request: Request,
    exc: LLMResponseError,
) -> JSONResponse:
    """Maps ``LLMResponseError`` to a 502 JSON response."""
    return JSONResponse(
        status_code=502,
        content={
            "detail": "Bad response from LLM service",
            "type": "llm_response_error",
            "message": str(exc),
        },
    )


async def parse_error_handler(
    request: Request,
    exc: ParseError,
) -> JSONResponse:
    """Maps ``ParseError`` to a 422 JSON response."""
    return JSONResponse(
        status_code=422,
        content={
            "detail": str(exc),
            "type": "parse_error",
        },
    )


# ── Workspace exception handlers ─────────────────────────────────


async def insufficient_role_handler(
    request: Request,
    exc: InsufficientRole,
) -> JSONResponse:
    """Maps ``InsufficientRole`` to a 403 JSON response."""
    return JSONResponse(
        status_code=403,
        content={"detail": str(exc), "type": "insufficient_role"},
    )


async def owner_transfer_error_handler(
    request: Request,
    exc: OwnerTransferError,
) -> JSONResponse:
    """Maps ``OwnerTransferError`` to a 400 JSON response."""
    return JSONResponse(
        status_code=400,
        content={"detail": str(exc), "type": "owner_transfer_error"},
    )


async def last_admin_error_handler(
    request: Request,
    exc: LastAdminError,
) -> JSONResponse:
    """Maps ``LastAdminError`` to a 400 JSON response."""
    return JSONResponse(
        status_code=400,
        content={"detail": str(exc), "type": "last_admin_error"},
    )


async def cannot_remove_owner_handler(
    request: Request,
    exc: CannotRemoveOwnerError,
) -> JSONResponse:
    """Maps ``CannotRemoveOwnerError`` to a 400 JSON response."""
    return JSONResponse(
        status_code=400,
        content={"detail": str(exc), "type": "cannot_remove_owner"},
    )
