"""
Shared FastAPI dependency functions.

get_current_user  — decode Bearer token and return the owning User row.
require_registered — same as above but rejects guest accounts.
"""

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from sqlalchemy.orm import Session

from app.auth.jwt import decode_token
from app.database import get_db
from app.models.db import AccountType, User, UserStatus
from app.repositories import user_repo

_bearer = HTTPBearer()


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer),
    db: Session = Depends(get_db),
) -> User:
    """
    Decode the Bearer JWT and return the corresponding User.

    Raises 401 if the token is missing, expired, or malformed.
    The token must have type == "access".
    """
    token = credentials.credentials
    try:
        payload = decode_token(token)
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )

    if payload.get("type") != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type",
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

    return user


def require_registered(user: User = Depends(get_current_user)) -> User:
    """
    Dependency that rejects guest accounts.

    Guest tokens are valid access tokens, but certain resources (collection,
    MMR, persistent rewards) are only available to registered users.
    """
    if user.account_type != AccountType.REGISTERED:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="A registered account is required for this action",
        )
    return user
