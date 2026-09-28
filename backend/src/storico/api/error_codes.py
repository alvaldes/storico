"""Canonical machine-readable error codes for the API error envelope.

Single registry for every ``error_code`` value the API emits, so code names are
invented once and reviewed as one list instead of drifting per call site.
Values are SCREAMING_SNAKE (feature ``api-error-code-envelope``, decision D3).

Add a constant here before referencing it from a handler or a raise site;
frontend translation (WU5) keys on these exact strings.
"""

__all__ = [
    "CANNOT_REMOVE_OWNER",
    "CIPHER_ERROR",
    "CREDENTIAL_UNDECRYPTABLE",
    "DUPLICATE_ENTITY",
    "ENCRYPTION_KEY_MISSING",
    "ENTITY_NOT_FOUND",
    "INSUFFICIENT_ROLE",
    "INTERNAL_ERROR",
    "LAST_ADMIN_ERROR",
    "LLM_CONNECTION_ERROR",
    "LLM_MODEL_NOT_FOUND",
    "LLM_RESPONSE_ERROR",
    "OWNER_TRANSFER_ERROR",
    "PARSE_ERROR",
    "REPOSITORY_ERROR",
    "REQUEST_VALIDATION_FAILED",
]

# ── Domain exception handlers (api/errors.py) ────────────────────

ENTITY_NOT_FOUND = "ENTITY_NOT_FOUND"
DUPLICATE_ENTITY = "DUPLICATE_ENTITY"
REPOSITORY_ERROR = "REPOSITORY_ERROR"
INTERNAL_ERROR = "INTERNAL_ERROR"
LLM_CONNECTION_ERROR = "LLM_CONNECTION_ERROR"
LLM_MODEL_NOT_FOUND = "LLM_MODEL_NOT_FOUND"
LLM_RESPONSE_ERROR = "LLM_RESPONSE_ERROR"
PARSE_ERROR = "PARSE_ERROR"
INSUFFICIENT_ROLE = "INSUFFICIENT_ROLE"
OWNER_TRANSFER_ERROR = "OWNER_TRANSFER_ERROR"
LAST_ADMIN_ERROR = "LAST_ADMIN_ERROR"
CANNOT_REMOVE_OWNER = "CANNOT_REMOVE_OWNER"

# ── Credential cipher exception handlers ─────────────────────────

ENCRYPTION_KEY_MISSING = "ENCRYPTION_KEY_MISSING"
CREDENTIAL_UNDECRYPTABLE = "CREDENTIAL_UNDECRYPTABLE"
CIPHER_ERROR = "CIPHER_ERROR"

# ── Framework-level handlers ─────────────────────────────────────

# FastAPI's own body-validation 422 (``RequestValidationError``): the default
# response carries no app code, only the ``detail`` list of validation errors.
REQUEST_VALIDATION_FAILED = "REQUEST_VALIDATION_FAILED"
