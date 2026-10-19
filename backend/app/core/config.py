from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/ directory (config.py lives at backend/app/core/config.py)
BASE_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """Application settings, loaded from environment variables or backend/.env."""

    database_url: str
    max_upload_size_mb: int = 10  # used by the upload validation in Stage 9

    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()