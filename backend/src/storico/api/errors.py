"""FastAPI exception handlers for domain-level errors."""

import logging

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
from storico.domain.entities.exceptions import (
    CipherError,
    CredentialUndecryptable,
    EncryptionKeyMissing,
)

logger = logging.getLogger(__name__)


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
    logger.error(
        "RepositoryError: %s | path=%s method=%s",
        exc,
        request.url.path,
        request.method,
        exc_info=exc,
    )
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error", "type": "repository_error"},
    )


async def generic_error_handler(
    request: Request,
    exc: Exception,  # noqa: BLE001
) -> JSONResponse:
    """Catches any unhandled exception and returns a safe 500 response."""
    logger.exception(
        "Unhandled exception: %s | path=%s method=%s",
        exc,
        request.url.path,
        request.method,
    )
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


# ── Credential cipher exception handlers ─────────────────────────

# One code per subclass, keyed by exact type: the handler is registered on the
# ``CipherError`` base so it must say which specific condition it caught. The code is what
# a client or an operator greps for; the message is what they act on.
_CIPHER_ERROR_CODES: dict[type[CipherError], str] = {
    EncryptionKeyMissing: "ENCRYPTION_KEY_MISSING",
    CredentialUndecryptable: "CREDENTIAL_UNDECRYPTABLE",
}


async def cipher_error_handler(
    request: Request,
    exc: CipherError,
) -> JSONResponse:
    """Maps ``CipherError`` to a 500 JSON response an operator can act on.

    ``500`` and not a ``4xx``: the caller did nothing wrong. The server is not in a
    position to keep the secret it was asked to keep, and only whoever runs it can change
    that. Answering ``400`` would blame the workspace admin for a deployment gap.

    The message is the exception's own, which by construction names the problem and never
    the credential or the master key — that is what makes it safe both to return and to log.
    """
    error_code = _CIPHER_ERROR_CODES.get(type(exc), "CIPHER_ERROR")
    logger.error(
        "CipherError: %s | code=%s | path=%s method=%s",
        exc,
        error_code,
        request.url.path,
        request.method,
        exc_info=exc,
    )
    return JSONResponse(
        status_code=500,
        content={
            "detail": str(exc),
            "type": "cipher_error",
            "error_code": error_code,
        },
    )
