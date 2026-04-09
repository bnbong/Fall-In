"""
Database operations for Profile rows.
"""

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.db import Profile


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def set_currency(db: Session, profile: Profile, currency: int) -> Profile:
    """Persist the exact wallet amount for the profile."""
    profile.currency = currency
    profile.updated_at = _utcnow()
    db.commit()
    db.refresh(profile)
    return profile


def add_currency(db: Session, profile: Profile, delta: int) -> Profile:
    """Atomically add *delta* to the profile's wallet (can be negative)."""
    profile.currency = max(0, profile.currency + delta)
    profile.updated_at = _utcnow()
    db.commit()
    db.refresh(profile)
    return profile
