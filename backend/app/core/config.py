"""
Application configuration.

Reads from environment variables (or a .env file in dev). Centralised here so
no other module ever calls os.getenv() directly — that gets messy fast.
"""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Database
    database_url: str

    # App
    environment: str = "development"
    secret_key: str

    # Pydantic v2 config
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


# Single shared instance. Import this elsewhere: `from app.core.config import settings`
settings = Settings()