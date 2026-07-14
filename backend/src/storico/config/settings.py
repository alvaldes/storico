"""Application configuration via pydantic-settings."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables / .env file."""

    app_name: str = "Storico API"
    debug: bool = False

    # PostgreSQL
    database_url: str = "postgresql+asyncpg://storico:storico@localhost:5432/storico"

    # Qdrant (vector store)
    qdrant_url: str = "http://localhost:6333"

    # Redis (Celery broker)
    redis_url: str = "redis://localhost:6379/0"

    # Ollama (local LLM)
    ollama_base_url: str = "http://localhost:11434"
    ollama_host: str = "http://localhost:11434"
    default_llm_model: str = "llama3.2"
    judge_llm_model: str = "llama3.2"
    llm_timeout: int = 120

    # Embedding
    embedding_model: str = "nomic-embed-text"
    embedding_dimensions: int = 768

    # Vector store (Qdrant)
    qdrant_collection: str = "storico_extractions"

    # RAG
    rag_similarity_threshold: float = 0.85
    rag_max_examples: int = 3

    # CORS
    cors_origins: str = "http://localhost:4321"

    # Auth
    auth_internal_token: str = "dev-insecure-token-change-in-production"
    auth_jwt_secret: str = "dev-insecure-token-change-in-production"
    auth_allowed_origins: str = "http://localhost:4321"

    # Server
    host: str = "127.0.0.1"
    port: int = 8000

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
