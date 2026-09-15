"""Application configuration via pydantic-settings."""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Path to .env: resolve relative to THIS file (settings.py), not to cwd.
#   backend/src/storico/config/settings.py → .parent*4 = backend/
_ENV_FILE = Path(__file__).resolve().parent.parent.parent.parent / ".env"


class Settings(BaseSettings):
    """Application settings loaded from environment variables / .env file."""

    # PostgreSQL
    database_url: str = "postgresql+asyncpg://storico:storico@localhost:5432/storico"

    # Qdrant (vector store)
    qdrant_url: str = "http://localhost:6333"
    qdrant_api_key: str | None = None

    # Ollama — fallback default; users configure their LLM host per workspace in DB
    ollama_host: str = "http://localhost:11434"

    # Embedding
    embedding_model: str = "nomic-embed-text"
    embedding_dimensions: int = 768
    embedding_provider: str = "ollama"
    google_embedding_model: str = "text-embedding-004"
    openai_embedding_model: str = "text-embedding-3-small"

    # Vector store (Qdrant)
    qdrant_collection: str = "storico_extractions"

    # RAG
    rag_similarity_threshold: float = 0.85
    rag_max_examples: int = 3

    # Auth — CORS origins (comma-separated)
    auth_allowed_origins: str = "http://localhost:4321"

    # Auth — JWT secret for verifying proxy-generated tokens
    auth_jwt_secret: str = "dev-insecure-token-change-in-production"

    # Embedding API keys
    google_api_key: str | None = None
    openai_api_key: str | None = None

    model_config = SettingsConfigDict(
        env_file=_ENV_FILE,
        env_file_encoding="utf-8",
        env_prefix="STORICO_",
        extra="ignore",
    )

    @classmethod
    def load(cls) -> "Settings":
        """Convenience factory — loads settings from env / .env file.

        Cached via the module-level ``get_settings`` lru_cache so repeated
        calls during a request lifecycle do not re-parse the ``.env`` file
        and re-instantiate pydantic-settings on every cold path (e.g. the
        ``get_current_user`` JWT decode path was hitting this per request).
        Kept as the legacy entrypoint for existing call sites and tests.
        """
        return get_settings()


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-lifetime cached ``Settings`` instance.

    Wrapping ``Settings()`` in ``lru_cache(maxsize=1)`` lets us skip the
    cost of re-reading ``.env`` and re-validating via pydantic-settings on
    every call — the previous ``Settings.load()`` did that on each
    invocation, which surfaced in hot paths such as auth/JWT (one per
    request) and engine setup.

    The cache is process-local and not shared across worker processes.
    Tests that need a fresh settings instance should call
    ``_reset_settings_cache()`` to clear the lru_cache.
    """
    return Settings()


def _reset_settings_cache() -> None:
    """Clear the ``get_settings`` lru_cache — for tests only.

    Production code should never call this; settings are immutable for
    the process lifetime. Tests use it to avoid cross-test pollution when
    they patch env vars or override ``Settings`` values.
    """
    get_settings.cache_clear()
