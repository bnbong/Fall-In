"""
Alembic migration environment.

DATABASE_URL is loaded from app.config (which reads from .env),
so no credentials need to live in alembic.ini.

Usage:
    cd backend
    uv run alembic upgrade head          # apply all migrations
    uv run alembic revision --autogenerate -m "describe change"
"""

import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool

# Make sure 'app' is importable when running alembic from backend/
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.config import settings
from app.database import Base

# Import all models so Alembic can detect them during autogenerate
from app.models import db as _models_db  # noqa: F401

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def get_url() -> str:
    return settings.DATABASE_URL


def run_migrations_offline() -> None:
    context.configure(
        url=get_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    cfg = config.get_section(config.config_ini_section, {})
    cfg["sqlalchemy.url"] = get_url()

    connectable = engine_from_config(
        cfg,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
