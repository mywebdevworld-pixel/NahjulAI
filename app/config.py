"""Application configuration, loaded from environment / .env file."""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env", env_file_encoding="utf-8", extra="ignore"
    )

    # LLM (any OpenAI-compatible endpoint; Ollama by default)
    llm_base_url: str = "http://localhost:11434/v1"
    llm_model: str = "llama3.1:8b"
    llm_api_key: str = "ollama"
    llm_timeout_seconds: float = 120.0
    llm_max_tokens: int = 1024
    llm_temperature: float = 0.3

    # Retrieval
    embedding_model: str = "BAAI/bge-small-en-v1.5"
    top_k: int = 6
    max_history_messages: int = 6

    # Paths
    data_dir: Path = PROJECT_ROOT / "data"
    frontend_dir: Path = PROJECT_ROOT / "frontend"

    # Server
    host: str = "0.0.0.0"
    port: int = 8000
    cors_origins: str = "*"

    @property
    def corpus_path(self) -> Path:
        return self.data_dir / "corpus.json"

    @property
    def chroma_dir(self) -> Path:
        return self.data_dir / "chroma"

    @property
    def raw_dir(self) -> Path:
        return self.data_dir / "raw"


@lru_cache
def get_settings() -> Settings:
    return Settings()
