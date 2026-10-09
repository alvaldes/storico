from __future__ import annotations

from uuid import UUID

from storico.domain.entities.trello_board import TrelloBoardRef


class RepositoryError(Exception):
    """Base exception for all repository errors."""

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(self.message)

    def __str__(self) -> str:
        return self.message


class EntityNotFound(RepositoryError):
    """Raised when a domain entity is not found in the repository."""

    def __init__(self, entity_type: str, entity_id: str | UUID) -> None:
        self.entity_type = entity_type
        self.entity_id = entity_id
        super().__init__(f"{entity_type} with id '{entity_id}' not found")

    def __str__(self) -> str:
        return f"{self.entity_type} with id '{self.entity_id}' not found"


class DuplicateEntity(RepositoryError):
    """Raised when trying to create an entity that already exists."""

    def __init__(self, entity_type: str, field: str, value: str) -> None:
        self.entity_type = entity_type
        self.field = field
        self.value = value
        super().__init__(f"{entity_type} with {field} '{value}' already exists")

    def __str__(self) -> str:
        return f"{self.entity_type} with {self.field} '{self.value}' already exists"


class VersionAllocationConflictError(RepositoryError):
    """Raised when a version number could not be allocated after the bounded retries.

    Every attempt lost the race against a concurrent run on the same story. A distinct
    type — not a bare ``RepositoryError`` — is what the API slice needs to map the failure
    to its own HTTP status instead of leaving it silent inside the generic 500.

    Carries the story whose allocation was exhausted when the caller knows it, so the
    API handler can still compose a useful ``detail`` when the message is silent.
    """

    def __init__(self, message: str, user_story_id: UUID | None = None) -> None:
        self.user_story_id = user_story_id
        super().__init__(message)


class LLMError(Exception):
    """Base exception for all LLM-related errors."""

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(self.message)

    def __str__(self) -> str:
        return self.message


class LLMConnectionError(LLMError):
    """Raised when the LLM service cannot be reached."""

    def __init__(self, message: str = "Failed to connect to LLM service") -> None:
        super().__init__(message)


class LLMModelNotFoundError(LLMError):
    """Raised when the requested model is not available on the LLM service."""

    def __init__(self, model: str) -> None:
        self.model = model
        super().__init__(f"Model '{model}' not found on LLM service")


class LLMResponseError(LLMError):
    """Raised when the LLM response is invalid or unprocessable."""

    def __init__(self, message: str = "Invalid LLM response") -> None:
        super().__init__(message)


class ParseError(LLMError):
    """Raised when parsing LLM output fails."""

    def __init__(self, message: str = "Failed to parse LLM response") -> None:
        super().__init__(message)


class PromptTemplateNotFound(LLMError):
    """Raised when a requested prompt template file does not exist."""

    def __init__(self, template_name: str) -> None:
        self.template_name = template_name
        super().__init__(f"Prompt template '{template_name}' not found")


class VectorStoreError(Exception):
    """Raised when the vector store cannot service a destructive operation.

    Deliberately outside the ``RepositoryError`` tree: a vector-store failure is not a
    relational failure, and it must not be swallowed by the repository error handler.
    Its caller is destructive (story deletion cleanup), so the outage has to surface
    as its own retryable condition instead of a generic internal error.
    """

    def __init__(self, message: str = "Vector store operation failed") -> None:
        self.message = message
        super().__init__(self.message)

    def __str__(self) -> str:
        return self.message


class NotWorkspaceMember(RepositoryError):
    """Raised when a user is not a member of a workspace."""

    def __init__(self, workspace_id: UUID, user_id: UUID) -> None:
        self.workspace_id = workspace_id
        self.user_id = user_id
        super().__init__(f"User '{user_id}' is not a member of workspace '{workspace_id}'")


class InsufficientRole(RepositoryError):
    """Raised when a user lacks the required role for an action."""

    def __init__(self, workspace_id: UUID, user_id: UUID, required_role: str) -> None:
        self.workspace_id = workspace_id
        self.user_id = user_id
        self.required_role = required_role
        super().__init__(
            f"User '{user_id}' lacks required role '{required_role}' in workspace '{workspace_id}'"
        )


class OwnerTransferError(RepositoryError):
    """Raised when workspace ownership transfer fails."""

    def __init__(self, message: str) -> None:
        super().__init__(message)


class LastAdminError(RepositoryError):
    """Raised when trying to remove or demote the last admin of a workspace."""

    def __init__(self, message: str = "Cannot remove the last admin of a workspace") -> None:
        super().__init__(message)


class CannotRemoveOwnerError(RepositoryError):
    """Raised when trying to remove the workspace owner from the workspace."""

    def __init__(self, message: str = "Cannot remove the workspace owner") -> None:
        super().__init__(message)


class CipherError(Exception):
    """Base exception for credential cipher errors.

    Deliberately outside the ``RepositoryError`` tree: nothing is wrong with the
    repository, and the server's *configuration* is what leaves the request unservable.

    Messages name the problem and never the secret. A message, a log line and a ``repr``
    are all places a key or a plaintext credential would outlive the request that
    carried it, so the value is never interpolated into any of them.
    """

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(self.message)

    def __str__(self) -> str:
        return self.message


class EncryptionKeyMissing(CipherError):
    """Raised when no master key is configured and a value must be encrypted."""

    def __init__(
        self,
        message: str = (
            "No encryption master key is configured, so workspace credentials cannot be stored"
        ),
    ) -> None:
        super().__init__(message)


class CredentialUndecryptable(CipherError):
    """Raised when a value marked as encrypted cannot be decrypted."""

    def __init__(
        self,
        message: str = (
            "A stored workspace credential cannot be decrypted with the configured master key"
        ),
    ) -> None:
        super().__init__(message)


class TrelloExportError(Exception):
    """Base exception for all Trello export errors.

    Carries ``board_ref`` when the failure happened *after* the board was
    created. That is the partial-failure contract: an export that died halfway
    must not report as if nothing happened, because the half-built board exists
    on Trello and the member needs its URL to go look at it. Failures before
    the board existed carry ``board_ref=None``.

    Messages never contain credentials, and the py-trello exceptions behind
    them are deliberately not chained either (``raise ... from None``). On the
    installed 0.20.1 those messages are already credential-free — the base URL
    and the response text, with the credentials in a separate ``params`` dict —
    but the policy does not rest on that: a chained cause reaches every
    traceback a logger prints without passing through anything this module
    controls, and the message shape is a library detail with no promise attached
    to it.
    """

    def __init__(self, message: str, board_ref: TrelloBoardRef | None = None) -> None:
        self.message = message
        self.board_ref = board_ref
        super().__init__(self.message)

    def __str__(self) -> str:
        return self.message


class TrelloCredentialRejectedError(TrelloExportError):
    """Raised when Trello rejects the workspace's API key or token (HTTP 401).

    Not retryable: the credential is wrong or revoked, and retrying cannot fix
    it — the workspace's credentials have to be re-entered by an admin.
    """

    def __init__(
        self,
        message: str = "Trello rejected the workspace credentials: the API key or token was not accepted",
        board_ref: TrelloBoardRef | None = None,
    ) -> None:
        super().__init__(message, board_ref)


class TrelloServiceUnavailableError(TrelloExportError):
    """Raised when Trello failed unexpectedly (connection errors, 5xx).

    Retryable in principle — the failure is transient and not the caller's
    fault — but this adapter raises it without retrying: only the rate-limit
    kind of failure earns the bounded backoff, matching csv2trello's measured
    policy. A caller that wants to may retry an export that failed this way.
    """

    def __init__(
        self,
        message: str = "Trello was unreachable or failed unexpectedly during the export",
        board_ref: TrelloBoardRef | None = None,
    ) -> None:
        super().__init__(message, board_ref)


class TrelloRateLimitExhaustedError(TrelloExportError):
    """Raised when Trello kept failing with rate-limit responses and the
    adapter's bounded retries ran out.

    Not retryable by the caller: the adapter already backed off exponentially
    through its full budget of attempts, and an immediate retry would start
    from the same saturated window. Waiting and re-exporting creates a new
    board (a new job), which is the accepted recovery path.
    """

    def __init__(
        self,
        message: str = "Trello kept rate-limiting the export after the retries ran out",
        board_ref: TrelloBoardRef | None = None,
    ) -> None:
        super().__init__(message, board_ref)


class TrelloBoardRefusedError(TrelloExportError):
    """Raised when Trello refused to create the board itself.

    Not retryable: the refusal is a quota or workspace limit on the Trello
    account (csv2trello measured that these messages must never be retried —
    "workspace full", "limit", "quota"), so only a human action on the Trello
    account can change the outcome. The board never existed, so ``board_ref``
    is always ``None``.
    """

    def __init__(
        self,
        message: str = "Trello refused to create the board: the account appears to have reached a board or quota limit",
        board_ref: TrelloBoardRef | None = None,
    ) -> None:
        super().__init__(message, board_ref)


class TrelloCardRefusedError(TrelloExportError):
    """Raised when Trello refused part of the board's content — a list, a
    label, a card or a checklist — after the board already existed.

    Not retryable: like the board refusal, the refusal is a quota or workspace
    limit, and retrying cannot lift it. Always carries ``board_ref`` so the
    half-built board is never hidden from the member.
    """

    def __init__(
        self,
        message: str = "Trello refused part of the board's content: the account appears to have reached a board or quota limit",
        board_ref: TrelloBoardRef | None = None,
    ) -> None:
        super().__init__(message, board_ref)
