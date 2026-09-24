"""Application configuration via pydantic-settings."""

import logging
from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
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
    #
    # ``embedding_model`` is the **Ollama** model only. Each cloud provider reads its own
    # field (``google_embedding_model``, ``openai_embedding_model``); the provider→field
    # mapping has exactly one home, ``embedding_model_for()`` in
    # ``infrastructure/vector/__init__.py``. Do not read ``embedding_model`` to report
    # which model is in use: it names the wrong one for two of the three providers.
    embedding_model: str = "nomic-embed-text"
    embedding_dimensions: int = 768
    embedding_provider: str = "ollama"
    # Google embedding model. ``text-embedding-004`` was retired by the API and now
    # answers 404 NOT_FOUND; ``gemini-embedding-001`` is the current one and honours
    # ``output_dimensionality`` (768 here), so the vector still matches the collection.
    google_embedding_model: str = "gemini-embedding-001"
    openai_embedding_model: str = "text-embedding-3-small"

    # Vector store (Qdrant)
    #
    # One collection per environment: a collection belongs to the embedding model that
    # fills it, and vectors from two different models are incomparable even at the same
    # dimensions. A shared collection therefore silently returns meaningless neighbours.
    qdrant_collection: str = "storico_extractions"

    # No RAG knobs here, deliberately. ``rag_similarity_threshold`` and ``rag_max_examples``
    # were declared here and read by nothing: the retrieval threshold is a parameter with its
    # own default on ``QdrantAdapter.search_similar``, and the value that actually reaches it
    # is per workspace (``extraction_task`` reads ``few_shot_threshold``). A setting nothing
    # reads is a knob in name only.

    # Auth — CORS origins (comma-separated)
    auth_allowed_origins: str = "http://localhost:4321"

    # Auth — JWT secret for verifying proxy-generated tokens
    auth_jwt_secret: str = "dev-insecure-token-change-in-production"

    # Master key for encrypting workspace LLM credentials at rest.
    #
    # Deliberately has no default. A default would be a published key that silently
    # encrypts — or worse, fails to protect — production rows, and that is
    # indistinguishable from no encryption at all while being much harder to notice.
    # Absent, the cipher refuses to store a credential and the API answers 500 with
    # ``ENCRYPTION_KEY_MISSING``, so the gap is loud instead of cosmetic.
    encryption_key: str | None = None

    # Embedding API keys
    google_api_key: str | None = None
    openai_api_key: str | None = None

    # Logging — root logger level applied by ``create_app()`` (see api/app.py).
    # Validated loudly instead of left as a free-form string: a typo'd value
    # (``INF0``, ``LOGLEVEL``) that pydantic accepted would flow into
    # ``dictConfig`` and raise a deep, unrelated error — or, with a laxer
    # design, silently degrade to some default. Same defect class that
    # ``extra="ignore"`` hides for unknown env names, one level up.
    log_level: str = "INFO"

    @field_validator("log_level")
    @classmethod
    def _log_level_must_be_a_real_level(cls, value: str) -> str:
        """Reject unknown level names with the offending value in the message."""
        normalized = value.strip().upper()
        valid_names = sorted(logging.getLevelNamesMapping())
        if normalized not in logging.getLevelNamesMapping():
            raise ValueError(
                f"STORICO_LOG_LEVEL={value!r} is not a valid logging level name. "
                f"Valid names: {valid_names}"
            )
        return normalized

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
