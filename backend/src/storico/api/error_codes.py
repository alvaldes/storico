"""Canonical machine-readable error codes for the API error envelope.

Single registry for every ``error_code`` value the API emits, so code names are
invented once and reviewed as one list instead of drifting per call site.
Values are SCREAMING_SNAKE (feature ``api-error-code-envelope``, decision D3).

Add a constant here before referencing it from a handler or a raise site;
frontend translation (WU5) keys on these exact strings.
"""

__all__ = [
    "ADMIN_ACCESS_REQUIRED",
    "AUTH_TOKEN_INVALID",
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
    "NOT_A_WORKSPACE_MEMBER",
    "OWNER_ACCESS_REQUIRED",
    "OWNER_TRANSFER_ERROR",
    "PARSE_ERROR",
    "REPOSITORY_ERROR",
    "REQUEST_VALIDATION_FAILED",
    "WORKSPACE_NOT_FOUND",
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

# ── Access-control raise sites (api/dependencies.py) ─────────────

# ``get_current_user``: the bearer token is absent, malformed, or names no user.
AUTH_TOKEN_INVALID = "AUTH_TOKEN_INVALID"

# ``get_workspace_for_user``: the addressed workspace row does not exist.
WORKSPACE_NOT_FOUND = "WORKSPACE_NOT_FOUND"

# The shared membership check behind every workspace-scoped route.
NOT_A_WORKSPACE_MEMBER = "NOT_A_WORKSPACE_MEMBER"

# ``require_admin``: the caller is a member but not an admin.
ADMIN_ACCESS_REQUIRED = "ADMIN_ACCESS_REQUIRED"

# ``require_owner``: the caller is an admin but not the workspace owner.
OWNER_ACCESS_REQUIRED = "OWNER_ACCESS_REQUIRED"

# ── Framework-level handlers ─────────────────────────────────────

# FastAPI's own body-validation 422 (``RequestValidationError``): the default
# response carries no app code, only the ``detail`` list of validation errors.
REQUEST_VALIDATION_FAILED = "REQUEST_VALIDATION_FAILED"
