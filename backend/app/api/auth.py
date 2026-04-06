"""
Authentication API routes.

POST /auth/register  — create account, return access + refresh tokens
POST /auth/login     — email+password login, return access + refresh tokens
POST /auth/guest     — ephemeral guest identity, return short-lived access token only
POST /auth/refresh   — exchange refresh token for new access token
POST /auth/logout    — client-side logout (token blacklist deferred to PR-08)
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from jose import JWTError
from sqlalchemy.orm import Session

from app.auth.jwt import (
    create_access_token,
    create_guest_token,
    create_refresh_token,
    decode_token,
)
from app.auth.password import hash_password
from app.database import get_db
from app.models.db import UserStatus
from app.repositories import user_repo
from app.schemas.auth import (
    AuthResponse,
    GuestLoginRequest,
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
    TokenResponse,
)
from app.services.auth_service import AuthenticationError, authenticate

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
def register(req: RegisterRequest, db: Session = Depends(get_db)) -> AuthResponse:
    """
    Create a new registered account.

    Returns 400 if the email is already registered.
    """
    if user_repo.get_by_email(db, req.email):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered",
        )

    user = user_repo.create_registered(
        db,
        email=req.email,
        password_hash=hash_password(req.password),
        nickname=req.nickname,
    )

    return AuthResponse(
        access_token=create_access_token(user.id, "registered"),
        refresh_token=create_refresh_token(user.id),
        account_type="registered",
    )


@router.post("/login", response_model=AuthResponse)
def login(req: LoginRequest, db: Session = Depends(get_db)) -> AuthResponse:
    """Authenticate with email + password."""
    try:
        user = authenticate(db, req.email, req.password)
    except AuthenticationError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )

    user_repo.touch_last_login(db, user)

    return AuthResponse(
        access_token=create_access_token(user.id, "registered"),
        refresh_token=create_refresh_token(user.id),
        account_type="registered",
    )


@router.post("/guest", response_model=AuthResponse)
def guest_login(req: GuestLoginRequest, db: Session = Depends(get_db)) -> AuthResponse:
    """
    Create a temporary guest identity.

    No refresh token is issued.  Guest data (profile, session identity,
    report log linkage) exists only for the token's lifetime.
    Persistent rewards, MMR, and collection writes are blocked at the
    API level (see require_registered dependency).
    """
    nickname = req.nickname or f"Guest_{uuid.uuid4().hex[:6].upper()}"
    user = user_repo.create_guest(db, nickname=nickname)

    return AuthResponse(
        access_token=create_guest_token(user.id),
        refresh_token=None,
        account_type="guest",
    )


@router.post("/refresh", response_model=TokenResponse)
def refresh(req: RefreshRequest, db: Session = Depends(get_db)) -> TokenResponse:
    """
    Exchange a valid refresh token for a new access token.

    Only registered users receive refresh tokens, so this endpoint
    implicitly only serves registered accounts.
    """
    try:
        payload = decode_token(req.refresh_token)
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
        )

    if payload.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not a refresh token",
        )

    user_id: str | None = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has no subject",
        )

    user = user_repo.get_by_id(db, user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )

    if user.status != UserStatus.ACTIVE:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Account is not active",
        )

    return TokenResponse(
        access_token=create_access_token(user.id, user.account_type.value),
    )


@router.post("/logout")
def logout() -> dict:
    """
    Signal logout intent from the client.

    Token invalidation (blacklist) is deferred to PR-08 (beta hardening).
    Until then, clients must discard their tokens locally.
    """
    return {"detail": "Logged out"}
