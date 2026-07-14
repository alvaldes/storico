from __future__ import annotations

from uuid import UUID


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


class NotWorkspaceMember(RepositoryError):
    """Raised when a user is not a member of a workspace."""

    def __init__(self, workspace_id: UUID, user_id: UUID) -> None:
        self.workspace_id = workspace_id
        self.user_id = user_id
        super().__init__(
            f"User '{user_id}' is not a member of workspace '{workspace_id}'"
        )


class InsufficientRole(RepositoryError):
    """Raised when a user lacks the required role for an action."""

    def __init__(self, workspace_id: UUID, user_id: UUID, required_role: str) -> None:
        self.workspace_id = workspace_id
        self.user_id = user_id
        self.required_role = required_role
        super().__init__(
            f"User '{user_id}' lacks required role '{required_role}' "
            f"in workspace '{workspace_id}'"
        )


class OwnerTransferError(RepositoryError):
    """Raised when workspace ownership transfer fails."""

    def __init__(self, message: str) -> None:
        super().__init__(message)


class LastAdminError(RepositoryError):
    """Raised when trying to remove or demote the last admin of a workspace."""

    def __init__(
        self, message: str = "Cannot remove the last admin of a workspace"
    ) -> None:
        super().__init__(message)


class CannotRemoveOwnerError(RepositoryError):
    """Raised when trying to remove the workspace owner from the workspace."""

    def __init__(
        self, message: str = "Cannot remove the workspace owner"
    ) -> None:
        super().__init__(message)
