"""Common/shared Pydantic schemas for Storico API."""

from pydantic import BaseModel, Field


class PaginationParams(BaseModel):
    """Query parameters for paginated endpoints."""

    page: int = Field(default=1, ge=1, description="Page number")
    size: int = Field(default=20, ge=1, le=100, description="Items per page")


class PaginatedResponse[T](BaseModel):
    """Generic wrapper for paginated list responses."""

    items: list[T]
    total: int
    page: int
    size: int


class ErrorResponse(BaseModel):
    """Standard error payload returned by the API."""

    detail: str
    type: str
