"""
Pydantic schemas for authentication endpoints.
"""

from typing import Optional

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.services.nickname_service import NicknameError, validate_nickname


def _validate_nick(v: str) -> str:
    """Pydantic field validator that runs the nickname service check."""
    try:
        return validate_nickname(v)
    except NicknameError as exc:
        raise ValueError(str(exc)) from exc


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    nickname: str = Field(min_length=1, max_length=50)

    @field_validator("nickname")
    @classmethod
    def nickname_policy(cls, v: str) -> str:
        return _validate_nick(v)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class GuestLoginRequest(BaseModel):
    nickname: Optional[str] = Field(default=None, min_length=1, max_length=50)

    @field_validator("nickname")
    @classmethod
    def nickname_policy(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        return _validate_nick(v)


class RefreshRequest(BaseModel):
    refresh_token: str


class TokenResponse(BaseModel):
    """Minimal token response (used for refresh endpoint)."""

    access_token: str
    token_type: str = "bearer"


class AuthResponse(BaseModel):
    """Full auth response (register / login / guest)."""

    access_token: str
    token_type: str = "bearer"
    refresh_token: Optional[str] = None  # None for guest accounts
    account_type: str
