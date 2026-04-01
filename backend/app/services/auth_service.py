"""
Auth service — business logic for authentication flows.

Keeps route handlers thin by centralising credential validation here.
"""

from sqlalchemy.orm import Session

from app.auth.password import verify_password
from app.models.db import AccountType, User
from app.repositories import user_repo


class AuthenticationError(Exception):
    """Raised when credentials are invalid."""
    pass


def authenticate(db: Session, email: str, password: str) -> User:
    """
    Validate email + password and return the matching User.

    Raises AuthenticationError on any failure (user not found,
    wrong password, or account is a guest — no password set).
    Using the same exception type for all cases avoids leaking
    which part of the check failed (timing-safe).
    """
    user = user_repo.get_by_email(db, email)

    if user is None or user.account_type != AccountType.REGISTERED:
        raise AuthenticationError("Invalid credentials")

    if not user.password_hash:
        raise AuthenticationError("Invalid credentials")

    if not verify_password(password, user.password_hash):
        raise AuthenticationError("Invalid credentials")

    return user
