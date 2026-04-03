"""
Application settings loaded from environment variables / .env file.

All tuneable values live here.  No secrets should be hard-coded anywhere else.
"""

from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Database
    DATABASE_URL: str = "sqlite:///./fall_in_dev.db"

    # JWT
    SECRET_KEY: str = "dev-secret-key-change-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    GUEST_TOKEN_EXPIRE_HOURS: int = 24

    # Startup behaviour
    # Set true only for local dev; production uses Alembic migrations instead.
    CREATE_TABLES_ON_STARTUP: bool = False

    # Redis (optional).
    # Leave unset for local dev — the in-memory fallback is used automatically.
    # Set to e.g. "redis://localhost:6379/0" in production to use Redis-backed
    # reconnect token storage with automatic TTL expiry.
    REDIS_URL: Optional[str] = None

    # WebSocket heartbeat.
    # Server sends PING every HEARTBEAT_INTERVAL_SECONDS.
    # If session.awaiting_pong is still True when the next PING is due, the
    # previous PING went unanswered — the connection is closed with code 1001.
    # Effective dead-connection timeout = HEARTBEAT_INTERVAL_SECONDS.
    HEARTBEAT_INTERVAL_SECONDS: int = 15

    # Reconnect & timeout windows.
    # RECONNECT_GRACE_SECONDS: how long a disconnected human seat is preserved
    #   before being permanently converted to bot control.
    # CARD_SELECTION_TIMEOUT_SECONDS: how long the server waits for a human to
    #   select a card before auto-playing with bot logic.
    RECONNECT_GRACE_SECONDS: int = 45
    CARD_SELECTION_TIMEOUT_SECONDS: int = 30

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
