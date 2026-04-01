"""
Fall-In Multiplayer API — FastAPI application entry point.

Local dev quickstart (from backend/ directory):
    cp .env.example .env          # fill in your values
    uv run alembic upgrade head   # apply migrations
    uv run uvicorn app.main:app --reload

Or set CREATE_TABLES_ON_STARTUP=true in .env to skip Alembic for local dev.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import auth as auth_router
from app.api import me as me_router
from app.config import settings
from app.database import Base, engine
from app.ws import endpoint as ws_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Dev convenience: auto-create tables if enabled.
    # Production deployments run `alembic upgrade head` instead.
    if settings.CREATE_TABLES_ON_STARTUP:
        Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(
    title="Fall-In Multiplayer API",
    version="0.1.0",
    description="Backend service for Fall-In (헤쳐 모여!) real-time multiplayer.",
    lifespan=lifespan,
)

app.include_router(auth_router.router)
app.include_router(me_router.router)
app.include_router(ws_router.router)


@app.get("/healthz", tags=["ops"])
def health_check():
    return {"status": "ok"}


@app.get("/version", tags=["ops"])
def version():
    return {"version": "0.1.0"}
