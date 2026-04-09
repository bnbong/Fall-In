"""
Database engine, session factory, and declarative base.

Session lifecycle:
  - get_db() yields a sync SQLAlchemy Session for use in FastAPI dependencies.
  - Each request gets its own session; it is closed (and rolled back on error)
    at the end of the request.

For tests, get_db is overridden via app.dependency_overrides to inject an
in-memory SQLite session — see backend/tests/conftest.py.
"""

from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import settings


def _make_engine(url: str):
    kwargs: dict = {}
    if url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
    else:
        # Production DB (PostgreSQL): detect stale connections after DB restart
        # and set a reasonable connection timeout.
        kwargs["pool_pre_ping"] = True
        kwargs["pool_size"] = 5
        kwargs["max_overflow"] = 10
        kwargs["pool_timeout"] = 10
    return create_engine(url, **kwargs)


engine = _make_engine(settings.DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    """Shared declarative base for all ORM models."""

    pass


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency that provides a database session per request."""
    db = SessionLocal()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
