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
