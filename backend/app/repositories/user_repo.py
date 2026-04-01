"""
Database operations for User and Profile rows.

All functions accept an explicit Session — no global state.
Callers (services / routes) own transaction boundaries.
"""

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.models.db import AccountType, Profile, User


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


# ---------------------------------------------------------------------------
# Read
# ---------------------------------------------------------------------------


def get_by_id(db: Session, user_id: str) -> Optional[User]:
    return db.get(User, user_id)


def get_by_email(db: Session, email: str) -> Optional[User]:
    return db.query(User).filter(User.email == email).first()


# ---------------------------------------------------------------------------
# Write
# ---------------------------------------------------------------------------


def create_registered(
    db: Session,
    *,
    email: str,
    password_hash: str,
    nickname: str,
) -> User:
    """Create a registered user + profile in a single transaction."""
    user = User(
        account_type=AccountType.REGISTERED,
        email=email,
        password_hash=password_hash,
    )
    db.add(user)
    db.flush()  # populate user.id before creating Profile

    profile = Profile(
        user_id=user.id,
        nickname=nickname,
        updated_at=_utcnow(),
    )
    db.add(profile)
    db.commit()
    db.refresh(user)
    return user


def create_guest(db: Session, *, nickname: str) -> User:
    """
    Create a guest user + profile.

    Guest rows are ephemeral: they have no email/password and
    should never accumulate collection entries or MMR.
    """
    user = User(account_type=AccountType.GUEST)
    db.add(user)
    db.flush()

    profile = Profile(
        user_id=user.id,
        nickname=nickname,
        updated_at=_utcnow(),
    )
    db.add(profile)
    db.commit()
    db.refresh(user)
    return user


def touch_last_login(db: Session, user: User) -> None:
    user.last_login_at = _utcnow()
    db.commit()
