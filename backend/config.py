"""
Central configuration module for the RAG pipeline.

Uses pydantic-settings to load configuration from environment variables
and .env files with sensible defaults for all pipeline components.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """RAG pipeline configuration loaded from environment variables / .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # --- HuggingFace ---
    HF_API_TOKEN: str = ""
    HF_MODEL_ID: str = "mistralai/Mistral-7B-Instruct-v0.3"
    HF_EMBEDDING_MODEL: str = "BAAI/bge-base-en-v1.5"
    HF_RERANKER_MODEL: str = "BAAI/bge-reranker-base"

    # --- Storage ---
    CHROMA_PERSIST_DIR: str = "./chroma_db"
    MONITORING_DB_PATH: str = "./monitoring.db"

    # --- Cache ---
    CACHE_MAX_SIZE: int = 1000
    CACHE_TTL: int = 3600  # seconds

    # --- Retrieval ---
    MAX_CONTEXT_TOKENS: int = 3000
    RETRIEVAL_TOP_K: int = 20
    RERANK_TOP_K: int = 5

    # --- Rate Limiting ---
    RATE_LIMIT_RPM: int = 30

    # --- Cost Tracking ---
    COST_PER_1K_EMBEDDING_TOKENS: float = 0.0001
    COST_PER_1K_GENERATION_TOKENS: float = 0.0006


# Singleton settings instance — import this everywhere.
settings = Settings()
