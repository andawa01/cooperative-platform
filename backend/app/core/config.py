"""
Application configuration.

Reads from environment variables (or a .env file in dev). Centralised here so
no other module ever calls os.getenv() directly — that gets messy fast.
"""
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


# Resolve .env relative to THIS FILE, not the current working directory.
BACKEND_DIR = Path(__file__).resolve().parents[2]
ENV_FILE = BACKEND_DIR / ".env"


class Settings(BaseSettings):
    # Database
    database_url: str
    database_url_test: str = ""

    # App
    environment: str = "development"
    secret_key: str

    # Currency used when a delivery is recorded for a produce line that has
    # never had a rate. Replaced by the cooperative's currency when
    # multi-cooperative support arrives. See D-019.
    default_currency: str = "KES"

    # JWT
    jwt_secret_key: str
    jwt_algorithm: str = "HS256"
    # 12 hours — chosen deliberately (see DECISIONS.md D-012).
    # Covers a full field shift; halves exposure vs a 24h token.
    access_token_expire_minutes: int = 12 * 60

    model_config = SettingsConfigDict(
        env_file=str(ENV_FILE),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


settings = Settings()