"""Application configuration via pydantic-settings."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables / .env file."""

    # PostgreSQL
    database_url: str = "postgresql+asyncpg://storico:storico@localhost:5432/storico"

    # Qdrant (vector store)
    qdrant_url: str = "http://localhost:6333"

    # Ollama — fallback default; users configure their LLM host per workspace in DB
    ollama_host: str = "http://localhost:11434"

    # Embedding
    embedding_model: str = "nomic-embed-text"
    embedding_dimensions: int = 768

    # Vector store (Qdrant)
    qdrant_collection: str = "storico_extractions"

    # RAG
    rag_similarity_threshold: float = 0.85
    rag_max_examples: int = 3

    # Auth — CORS origins (comma-separated)
    auth_allowed_origins: str = "http://localhost:4321"

    # Auth — JWT secret for verifying proxy-generated tokens
    auth_jwt_secret: str = "dev-insecure-token-change-in-production"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="STORICO_",
        extra="ignore",
    )

    @classmethod
    def load(cls) -> "Settings":
        """Convenience factory — loads settings from env / .env file."""
        return cls()
