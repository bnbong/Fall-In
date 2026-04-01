"""
Application settings loaded from environment variables / .env file.

All tuneable values live here.  No secrets should be hard-coded anywhere else.
"""

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

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
