"""FastAPI exception handlers for domain-level errors."""

import logging

from fastapi import Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from storico.api.error_codes import (
    CANNOT_REMOVE_OWNER,
    CIPHER_ERROR,
    CREDENTIAL_UNDECRYPTABLE,
    DUPLICATE_ENTITY,
    ENCRYPTION_KEY_MISSING,
    ENTITY_NOT_FOUND,
    INSUFFICIENT_ROLE,
    INTERNAL_ERROR,
    LAST_ADMIN_ERROR,
    LLM_CONNECTION_ERROR,
    LLM_MODEL_NOT_FOUND,
    LLM_RESPONSE_ERROR,
    OWNER_TRANSFER_ERROR,
    PARSE_ERROR,
    REPOSITORY_ERROR,
    REQUEST_VALIDATION_FAILED,
)
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

__all__ = [
    "ApiError",
    "api_error_handler",
    "cannot_remove_owner_handler",
    "cipher_error_handler",
    "duplicate_entity_handler",
    "entity_not_found_handler",
    "generic_error_handler",
    "insufficient_role_handler",
    "last_admin_error_handler",
    "llm_connection_error_handler",
    "llm_model_not_found_handler",
    "llm_response_error_handler",
    "owner_transfer_error_handler",
    "parse_error_handler",
    "repository_error_handler",
    "request_validation_error_handler",
]


class ApiError(Exception):
    """An API error that carries its own top-level machine-readable code.

    ``HTTPException`` exposes only ``status_code`` and ``detail``, so a raise
    site that needs a top-level ``error_code`` in the response body must use
    this exception instead — nesting a code inside ``detail`` is exactly the
    inconsistency the error-envelope feature removes.

    ``detail`` is a plain string: the human-readable English fallback that
    operators see; the code is the contract clients branch on.
    """

    def __init__(self, status_code: int, error_code: str, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.error_code = error_code
        self.detail = detail


async def api_error_handler(request: Request, exc: ApiError) -> JSONResponse:
    """Maps ``ApiError`` to a JSON response with its top-level ``error_code``."""
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail, "error_code": exc.error_code},
    )


async def request_validation_error_handler(
    request: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    """Maps FastAPI's own body-validation errors to a coded 422 response.

    ``detail`` reproduces FastAPI's default body exactly — the list of
    ``{type, loc, msg, input}`` items the frontend already parses
    (``api.ts`` ``buildErrorMessage`` reads ``first.msg``). Only top-level
    ``error_code`` is added on top of it.
    """
    return JSONResponse(
        status_code=422,
        content={
            "detail": jsonable_encoder(exc.errors()),
            "error_code": REQUEST_VALIDATION_FAILED,
        },
    )


async def entity_not_found_handler(
    request: Request,
    exc: EntityNotFound,
) -> JSONResponse:
    """Maps ``EntityNotFound`` to a 404 JSON response."""
    return JSONResponse(
        status_code=404,
        content={"detail": str(exc), "error_code": ENTITY_NOT_FOUND},
    )


async def duplicate_entity_handler(
    request: Request,
    exc: DuplicateEntity,
) -> JSONResponse:
    """Maps ``DuplicateEntity`` to a 409 JSON response."""
    return JSONResponse(
        status_code=409,
        content={"detail": str(exc), "error_code": DUPLICATE_ENTITY},
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
        content={"detail": "Internal server error", "error_code": REPOSITORY_ERROR},
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
        content={"detail": "Internal server error", "error_code": INTERNAL_ERROR},
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
            "error_code": LLM_CONNECTION_ERROR,
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
            "error_code": LLM_MODEL_NOT_FOUND,
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
            "error_code": LLM_RESPONSE_ERROR,
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
            "error_code": PARSE_ERROR,
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
        content={"detail": str(exc), "error_code": INSUFFICIENT_ROLE},
    )


async def owner_transfer_error_handler(
    request: Request,
    exc: OwnerTransferError,
) -> JSONResponse:
    """Maps ``OwnerTransferError`` to a 400 JSON response."""
    return JSONResponse(
        status_code=400,
        content={"detail": str(exc), "error_code": OWNER_TRANSFER_ERROR},
    )


async def last_admin_error_handler(
    request: Request,
    exc: LastAdminError,
) -> JSONResponse:
    """Maps ``LastAdminError`` to a 400 JSON response."""
    return JSONResponse(
        status_code=400,
        content={"detail": str(exc), "error_code": LAST_ADMIN_ERROR},
    )


async def cannot_remove_owner_handler(
    request: Request,
    exc: CannotRemoveOwnerError,
) -> JSONResponse:
    """Maps ``CannotRemoveOwnerError`` to a 400 JSON response."""
    return JSONResponse(
        status_code=400,
        content={"detail": str(exc), "error_code": CANNOT_REMOVE_OWNER},
    )


# ── Credential cipher exception handlers ─────────────────────────

# One code per subclass, keyed by exact type: the handler is registered on the
# ``CipherError`` base so it must say which specific condition it caught. The code is what
# a client or an operator greps for; the message is what they act on.
_CIPHER_ERROR_CODES: dict[type[CipherError], str] = {
    EncryptionKeyMissing: ENCRYPTION_KEY_MISSING,
    CredentialUndecryptable: CREDENTIAL_UNDECRYPTABLE,
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
    error_code = _CIPHER_ERROR_CODES.get(type(exc), CIPHER_ERROR)
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
            "error_code": error_code,
        },
    )
