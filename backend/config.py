"""
Configuration management for VAULT Backend.
Supports environment variables with prefix VAULT_ and .env file loading.
"""

from functools import lru_cache
from pathlib import Path
from typing import List, Union
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="VAULT_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Application settings
    app_name: str = Field(default="VAULT Backend", description="Name of the application")
    app_version: str = Field(default="0.1.0", description="Backend version")
    environment: str = Field(default="development", description="Runtime environment")
    debug: bool = Field(default=False, description="Debug mode")
    host: str = Field(default="127.0.0.1", description="Server host bind address")
    port: int = Field(default=8000, description="Server port")
    cors_origins: Union[List[str], str] = Field(
        default=["http://localhost:3000", "http://127.0.0.1:3000", "http://localhost:8000"],
        description="Allowed CORS origins",
    )

    # Offline-first enforcement
    offline_mode: bool = Field(
        default=True,
        description="Enforces private offline operation (no external cloud APIs)",
    )

    # Database configuration (SQLite by default, PostgreSQL supported through configuration)
    database_url: str = Field(
        default="sqlite:///./vault.db",
        description="Database connection URL (sqlite:///... or postgresql://...)",
    )
    db_echo: bool = Field(default=False, description="Echo SQL statements")

    # Storage paths
    upload_dir: str = Field(
        default="./data/uploads",
        description="Directory for uploaded documents and datasets",
    )
    max_upload_size_bytes: int = Field(
        default=50 * 1024 * 1024,  # 50 MB
        description="Maximum allowed upload size in bytes",
    )

    # Local LLM configuration
    llm_mode: str = Field(
        default="mock",
        description="LLM provider mode: 'mock', 'ollama', or 'local_api'",
    )
    llm_endpoint: str = Field(
        default="http://127.0.0.1:11434",
        description="Configurable URL for the local LLM service (defaults to localhost)",
    )
    llm_model: str = Field(
        default="llama3:8b",
        description="Default local model name to request",
    )
    llm_timeout_seconds: float = Field(
        default=30.0,
        description="Timeout for requests to the local LLM inference server",
    )

    # Logging
    log_level: str = Field(default="INFO", description="Logging level")
    log_format: str = Field(default="json", description="Log format: 'json' or 'text'")

    @field_validator("cors_origins", mode="before")
    @classmethod
    def assemble_cors_origins(cls, v: Union[str, List[str]]) -> List[str]:
        if isinstance(v, str) and not v.startswith("["):
            return [i.strip() for i in v.split(",") if i.strip()]
        elif isinstance(v, list):
            return v
        return ["*"]

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")

    @property
    def is_postgres(self) -> bool:
        return self.database_url.startswith("postgres")

    @property
    def resolved_upload_path(self) -> Path:
        p = Path(self.upload_dir)
        p.mkdir(parents=True, exist_ok=True)
        return p


@lru_cache()
def get_settings() -> Settings:
    """Returns cached Settings instance."""
    return Settings()
