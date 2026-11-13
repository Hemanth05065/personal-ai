from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Local AI Personal Assistant"
    environment: str = "development"
    database_url: str = "sqlite:///./assistant.db"
    ollama_url: str = "http://127.0.0.1:11434"
    model: str = "qwen3.5:4b"
    allowed_origins: str = "http://localhost:5173"
    max_context_messages: int = 20
    workspace_dir: Path = Path("assistant_workspace")
    max_file_bytes: int = 1_000_000
    api_key: str | None = None
    auth_required: bool = True
    session_hours: int = 12
    secure_cookies: bool = False
    security_dir: Path = Path(".security")
    master_key: str | None = None
    opa_url: str = "http://127.0.0.1:8181"
    opa_required: bool = False
    openshell_enabled: bool = False

    model_config = SettingsConfigDict(
        env_file=".env", env_prefix="ASSISTANT_", extra="ignore"
    )

    @property
    def origins(self) -> list[str]:
        return [item.strip() for item in self.allowed_origins.split(",") if item.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
