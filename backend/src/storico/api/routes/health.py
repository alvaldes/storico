"""Health check endpoint."""

from fastapi import APIRouter

router = APIRouter(prefix="/api/v1", tags=["health"])


@router.get("/health")
async def health():
    """Return API health status."""
    return {
        "status": "ok",
        "version": "0.1.0",
    }
