"""
Application configuration.

Reads from environment variables (or a .env file in dev). Centralised here so
no other module ever calls os.getenv() directly — that gets messy fast.
"""

from pathlib import Path

from pydantic import field_validator
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

    # Comma-separated list of allowed browser origins. Kept as a string so it
    # can come from a plain env var (pydantic-settings would try to JSON-decode
    # a list). Use `cors_origin_list` at the call site.
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    # Currency used when a delivery is recorded for a produce line that has
    # never had a rate. Replaced by the cooperative's currency when
    # multi-cooperative support arrives. See D-019.
    default_currency: str = "KES"

    # --- Observability ------------------------------------------------
    # JSON lines on stdout by default; set LOG_JSON=false for readable local
    # output. SLOW_REQUEST_MS decides when an access log line escalates to
    # WARNING.
    log_level: str = "INFO"
    log_json: bool = True
    slow_request_ms: int = 500

    # --- Login throttling ----------------------------------------------
    # Failures allowed per window (counted per email, deliberately not per IP
    # — see D-030), the window itself, and the first lockout duration.
    # Successive lockouts for the same email double, capped at a day.
    login_max_attempts: int = 5
    login_window_seconds: int = 15 * 60
    login_lockout_seconds: int = 15 * 60

    # --- Database pool ------------------------------------------------
    db_pool_size: int = 5
    db_max_overflow: int = 10
    db_pool_timeout: int = 30
    db_pool_recycle: int = 1800
    # Server-side cap on any single statement. A runaway query must not hold
    # a connection until the pool starves.
    db_statement_timeout_ms: int = 5000

    # Redis (see D-024)
    redis_url: str = "redis://localhost:6379/0"
    # SMS dispatch
    sms_max_attempts: int = 3
    sms_backoff_seconds: tuple[int, ...] = (2, 8, 30)
    # Simulated gateway failure rate (0.0–1.0). Set to 0 in prod once a
    # real gateway is wired in.
    sms_simulated_failure_rate: float = 0.1

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

    # --- Validation ---------------------------------------------------
    # These run when Settings is constructed, i.e. at import. A misconfigured
    # deployment fails to boot instead of failing somewhere in a request.

    @field_validator("jwt_secret_key")
    @classmethod
    def _jwt_key_is_long_enough(cls, value: str) -> str:
        # HS256's own minimum is 32 bytes; a shorter key weakens the signature
        # and is almost always a placeholder that reached production.
        if len(value) < 32:
            raise ValueError("JWT_SECRET_KEY must be at least 32 characters")
        return value

    @field_validator("database_url")
    @classmethod
    def _database_url_is_postgres(cls, value: str) -> str:
        if not value.startswith("postgresql"):
            raise ValueError(
                "DATABASE_URL must be a postgresql URL (postgresql+psycopg://...)"
            )
        return value

    @field_validator("log_level")
    @classmethod
    def _log_level_is_known(cls, value: str) -> str:
        allowed = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        upper = value.upper()
        if upper not in allowed:
            raise ValueError(
                f"LOG_LEVEL must be one of {sorted(allowed)}, got {value!r}"
            )
        return upper

    @field_validator(
        "slow_request_ms",
        "db_statement_timeout_ms",
        "login_max_attempts",
        "login_window_seconds",
        "login_lockout_seconds",
    )
    @classmethod
    def _positive(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("this setting must be a positive number")
        return value

    @field_validator("cors_origins")
    @classmethod
    def _cors_not_empty(cls, value: str) -> str:
        if not [o for o in value.split(",") if o.strip()]:
            raise ValueError("CORS_ORIGINS must list at least one origin")
        return value


settings = Settings()
