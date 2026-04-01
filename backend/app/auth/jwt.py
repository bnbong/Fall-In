"""
JWT creation and verification.

Token types:
  access   — short-lived (15 min for registered, 24 h for guest).
             Contains: sub (user_id), account_type, type="access".
  refresh  — long-lived (7 days), registered users only.
             Contains: sub (user_id), type="refresh".
             No account_type — caller must look up from DB if needed.

Token invalidation (blacklist) is deferred to PR-08 (beta hardening).
For now, logout is client-side only.
"""

from datetime import datetime, timedelta, timezone

from jose import jwt

from app.config import settings


def _now() -> datetime:
    return datetime.now(timezone.utc)


def create_access_token(user_id: str, account_type: str) -> str:
    expire = _now() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {
        "sub": user_id,
        "account_type": account_type,
        "type": "access",
        "exp": expire,
        "iat": _now(),
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def create_refresh_token(user_id: str) -> str:
    """Refresh tokens are issued only to registered users."""
    expire = _now() + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    payload = {
        "sub": user_id,
        "type": "refresh",
        "exp": expire,
        "iat": _now(),
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def create_guest_token(user_id: str) -> str:
    """Guest access tokens have a longer TTL but no refresh counterpart."""
    expire = _now() + timedelta(hours=settings.GUEST_TOKEN_EXPIRE_HOURS)
    payload = {
        "sub": user_id,
        "account_type": "guest",
        "type": "access",
        "exp": expire,
        "iat": _now(),
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def decode_token(token: str) -> dict:
    """
    Decode and verify a JWT.

    Raises jose.JWTError on invalid signature, expired token, etc.
    Callers must handle JWTError explicitly.
    """
    return jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
