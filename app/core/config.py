"""Application Configuration using Pydantic Settings."""

import os
from pathlib import Path
from typing import List, Union
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Application Basics
    APP_NAME: str = "IMAGEKEY"
    ENVIRONMENT: str = "development"
    DEBUG: bool = True
    HOST: str = "127.0.0.1"
    PORT: int = 8000

    # Base Paths
    BASE_DIR: Path = Path(__file__).resolve().parent.parent.parent
    UPLOAD_DIR: Path = Field(default=Path("./uploads"))

    # Security & Tokens
    SECRET_KEY: str = "dev-secret-key-change-me-in-production-min32chars"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://imagekey_user:imagekey_secret@127.0.0.1:5432/imagekey_db"
    DB_ECHO: bool = False

    # Upload Rules
    MAX_FILE_SIZE_BYTES: int = 5 * 1024 * 1024  # 5MB
    ALLOWED_MIME_TYPES: Union[str, List[str]] = "image/jpeg,image/png,image/webp"

    # Computer Vision & Recognition
    CONFIDENCE_THRESHOLD_VERIFIED: float = 0.85
    CONFIDENCE_THRESHOLD_UNCERTAIN: float = 0.65
    HAMMING_DISTANCE_MAX: int = 10

    # Rate Limiting
    RATE_LIMIT_PER_MINUTE: int = 60
    RATE_LIMIT_ENABLED: bool = True
    TESTING: bool = False

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    @field_validator("UPLOAD_DIR", mode="after")
    @classmethod
    def ensure_upload_dir(cls, v: Union[str, Path]) -> Path:
        p = Path(v)
        if not p.is_absolute():
            base = Path(__file__).resolve().parent.parent.parent
            p = base / p
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def allowed_mimes(self) -> List[str]:
        if isinstance(self.ALLOWED_MIME_TYPES, list):
            return self.ALLOWED_MIME_TYPES
        return [m.strip() for m in self.ALLOWED_MIME_TYPES.split(",") if m.strip()]


# Global cached settings instance
settings = Settings()
