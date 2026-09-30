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
    "CUSTOM_PROVIDER_NOT_FOUND",
    "DUPLICATE_ENTITY",
    "DUPLICATE_USER_STORY",
    "ENCRYPTION_KEY_MISSING",
    "ENTITY_NOT_FOUND",
    "EXTRACTION_ENDPOINT_REMOVED",
    "EXTRACTION_NOT_FOUND",
    "INSUFFICIENT_ROLE",
    "INTERNAL_ERROR",
    "LAST_ADMIN_ERROR",
    "LLM_CONNECTION_ERROR",
    "LLM_MODEL_NOT_FOUND",
    "LLM_RESPONSE_ERROR",
    "NOT_A_WORKSPACE_MEMBER",
    "OWNER_ACCESS_REQUIRED",
    "OWNER_ROLE_IMMUTABLE",
    "OWNER_TRANSFER_ERROR",
    "PARSE_ERROR",
    "PROJECT_ENDPOINT_REMOVED",
    "PROJECT_NOT_IN_WORKSPACE",
    "PROVIDER_DUPLICATE_NAME",
    "PROVIDER_MODELS_UNREACHABLE",
    "PROVIDER_NAME_BUILTIN",
    "PROVIDER_NAME_RESERVED",
    "PROVIDER_NOT_IN_WORKSPACE",
    "REPOSITORY_ERROR",
    "REQUEST_VALIDATION_FAILED",
    "STORY_NOT_IN_WORKSPACE",
    "TASK_CREATION_ENDPOINT_REMOVED",
    "TASK_DELETE_ENDPOINT_REMOVED",
    "TASK_VERSION_FROZEN",
    "UNSUPPORTED_EXPORT_FORMAT",
    "WORKSPACE_NOT_FOUND",
    "WORKSPACE_SLUG_TAKEN",
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

# ── Route raise sites (api/routes/) ──────────────────────────────

# ``workspaces.py`` PUT: the new slug collides with an existing workspace.
WORKSPACE_SLUG_TAKEN = "WORKSPACE_SLUG_TAKEN"

# ``workspaces.py`` PUT member role: the owner's role is not editable.
OWNER_ROLE_IMMUTABLE = "OWNER_ROLE_IMMUTABLE"

# ``projects.py`` and ``stories.py``: the addressed project lives in a
# different workspace than the path workspace.
PROJECT_NOT_IN_WORKSPACE = "PROJECT_NOT_IN_WORKSPACE"

# ``projects.py``: the pre-workspace project endpoints are gone (410).
PROJECT_ENDPOINT_REMOVED = "PROJECT_ENDPOINT_REMOVED"

# ``extraction.py``: the addressed story lives in a different workspace
# than the path workspace.
STORY_NOT_IN_WORKSPACE = "STORY_NOT_IN_WORKSPACE"

# ``extraction.py`` status: no extraction row for the addressed id.
EXTRACTION_NOT_FOUND = "EXTRACTION_NOT_FOUND"

# ``extraction.py``: the pre-workspace extraction endpoints are gone (410).
EXTRACTION_ENDPOINT_REMOVED = "EXTRACTION_ENDPOINT_REMOVED"

# ``tasks.py`` POST: manual task creation is gone (410) — a task is only born
# from an extraction run (design decision D3 of extraction-versioning).
TASK_CREATION_ENDPOINT_REMOVED = "TASK_CREATION_ENDPOINT_REMOVED"

# ``tasks.py`` DELETE: single-task deletion is gone (410) — no product path
# deletes a single task (design decision D12 of extraction-versioning).
TASK_DELETE_ENDPOINT_REMOVED = "TASK_DELETE_ENDPOINT_REMOVED"

# ``tasks.py`` PUT: dependencies are only editable on the story's current
# version — a dependencies write (presence, not value) on a frozen version is
# refused with the current version number in the detail (design decisions
# D5/D21 of extraction-versioning).
TASK_VERSION_FROZEN = "TASK_VERSION_FROZEN"

# ``stories.py`` POST: actor + feature + benefit already exist in the project.
DUPLICATE_USER_STORY = "DUPLICATE_USER_STORY"

# ``export.py`` GET: the requested export format is not one of json/markdown.
UNSUPPORTED_EXPORT_FORMAT = "UNSUPPORTED_EXPORT_FORMAT"

# ``workspace_settings.py``: no custom provider row for the addressed id.
CUSTOM_PROVIDER_NOT_FOUND = "CUSTOM_PROVIDER_NOT_FOUND"

# ``workspace_settings.py``: the provider row belongs to another workspace.
PROVIDER_NOT_IN_WORKSPACE = "PROVIDER_NOT_IN_WORKSPACE"

# ``workspace_settings.py`` create/rename: the name is taken in this workspace.
PROVIDER_DUPLICATE_NAME = "PROVIDER_DUPLICATE_NAME"

# ``workspace_settings.py`` create: the name collides with a built-in provider,
# so it can never be selected from the custom list.
PROVIDER_NAME_BUILTIN = "PROVIDER_NAME_BUILTIN"

# ``workspace_settings.py`` create: the name is the provider selector's control
# value, so registering it would break the "Add custom provider" slot.
PROVIDER_NAME_RESERVED = "PROVIDER_NAME_RESERVED"

# ``workspace_settings.py`` probe: the provider could not be reached to list
# its models (wrong API key or Base URL, or the provider is down).
PROVIDER_MODELS_UNREACHABLE = "PROVIDER_MODELS_UNREACHABLE"

# ── Framework-level handlers ─────────────────────────────────────

# FastAPI's own body-validation 422 (``RequestValidationError``): the default
# response carries no app code, only the ``detail`` list of validation errors.
REQUEST_VALIDATION_FAILED = "REQUEST_VALIDATION_FAILED"
