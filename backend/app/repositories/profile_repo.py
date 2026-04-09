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
