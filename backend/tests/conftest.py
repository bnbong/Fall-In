"""
Test fixtures for the Fall-In backend.

Each test function gets a fresh in-memory SQLite database via the
`client` and `db` fixtures.  Test isolation is achieved by creating
a new engine (and therefore a new in-memory database) per test.

Key design decisions:
  - StaticPool ensures all connections within one test share a single
    underlying SQLite connection, so data written by the test setup is
    visible to HTTP requests made through TestClient.
  - `db` and the session used inside `override_get_db` are the SAME
    session object, so commits in one context are immediately visible
    in the other — no race conditions with in-memory SQLite.
  - `app.dependency_overrides` is cleared after every test to prevent
    state leakage between test functions.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app


@pytest.fixture(autouse=True)
def reset_ws_manager():
    """Reset the WebSocket connection manager between tests."""
    from app.ws.connection_manager import manager
    manager.reset()
    yield
    manager.reset()


@pytest.fixture(autouse=True)
def reset_match_service():
    """Reset the module-level MatchService singleton between tests."""
    from app.ws.endpoint import _match_service
    _match_service.reset()
    yield
    _match_service.reset()


@pytest.fixture(autouse=True)
def reset_presence_manager():
    """
    Cancel all pending asyncio tasks and clear token state between tests.

    Calls PresenceManager.reset() which cancels grace-period and selection-
    timeout tasks AND clears the underlying reconnect token repo, so that
    tokens issued in one test are never visible in the next.
    """
    from app.ws.presence import presence_manager
    presence_manager.reset()
    yield
    presence_manager.reset()


@pytest.fixture()
def db_engine():
    """Fresh in-memory SQLite engine for one test."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


@pytest.fixture()
def db(db_engine) -> Session:
    """
    SQLAlchemy session tied to the test engine.

    This SAME session object is injected into every request handled
    by the TestClient (via the override below), so test setup writes
    are immediately visible inside request handlers.
    """
    SessionFactory = sessionmaker(bind=db_engine, autocommit=False, autoflush=False)
    session = SessionFactory()
    yield session
    session.close()


@pytest.fixture()
def client(db) -> TestClient:
    """
    FastAPI TestClient backed by the test database.

    The get_db dependency is overridden to always yield the shared
    `db` session, ensuring test data and request data share state.
    """

    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
