# --- Fall-In Backend ---
# Multi-stage build optimised for ARM64 (Oracle Cloud Ampere A1).
# Build (from repo root):
#   docker build -t fall-in-backend -f backend/Dockerfile .
# Run:
#   docker run -p 8000:8000 --env-file backend/.env fall-in-backend

FROM python:3.12-slim AS base

# Prevent Python from writing .pyc files and enable unbuffered output.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# --- Dependencies stage ---
FROM base AS deps

# Install uv for fast, reproducible dependency resolution.
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copy only dependency metadata first (cache-friendly layer).
COPY backend/pyproject.toml backend/uv.lock ./backend/
COPY pyproject.toml uv.lock ./

# Install backend deps (prod extras include redis).
# The client package (fall_in.core, fall_in.ai, etc.) is needed at runtime.
RUN cd backend && uv sync --no-dev --extra prod --no-install-project

# --- Runtime stage ---
FROM base AS runtime

# Copy the virtual environment from deps stage.
COPY --from=deps /app/backend/.venv /app/backend/.venv

# Copy source code.
COPY backend/app ./backend/app
COPY backend/migrations ./backend/migrations
COPY backend/alembic.ini ./backend/
COPY src/fall_in ./src/fall_in
COPY data ./data

# Make fall_in package importable (backend pythonpath includes ../src).
ENV PYTHONPATH="/app/src:/app/backend"
ENV PATH="/app/backend/.venv/bin:$PATH"

WORKDIR /app/backend

EXPOSE 8000

# Run migrations then start uvicorn.
# --host 0.0.0.0 binds to all interfaces inside the container.
# --workers 1 is correct for the in-memory singleton architecture.
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
