"""
Database operations for user_collection.

Invariant enforced here:
  - add_soldier must only be called with a registered user_id.
  - The service layer (or API dependency require_registered) is responsible
    for rejecting guest user_ids before reaching this function.

These functions do NOT validate account_type — that boundary belongs to the
service / API layers.  Repositories are intentionally thin.
"""

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.db import UserCollection


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def get_for_user(db: Session, user_id: str) -> list[UserCollection]:
    """Return all collection entries for a user, ordered by unlock time."""
    return (
        db.query(UserCollection)
        .filter(UserCollection.user_id == user_id)
        .order_by(UserCollection.unlocked_at)
        .all()
    )


def has_soldier(db: Session, user_id: str, soldier_id: int) -> bool:
    return (
        db.query(UserCollection)
        .filter(
            UserCollection.user_id == user_id,
            UserCollection.soldier_id == soldier_id,
        )
        .first()
        is not None
    )


def add_soldier(
    db: Session,
    user_id: str,
    soldier_id: int,
    source: str = "interview",
) -> UserCollection:
    """
    Add a soldier to a user's collection.

    Caller must ensure user_id belongs to a registered user.
    Does not check for duplicates — caller should use has_soldier() first
    if idempotency is required.
    """
    entry = UserCollection(
        user_id=user_id,
        soldier_id=soldier_id,
        source=source,
        unlocked_at=_utcnow(),
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


def add_soldiers_batch(
    db: Session,
    user_id: str,
    soldier_ids: list[int],
    source: str = "client_merge",
) -> int:
    """Add multiple soldiers in a single transaction. Returns count added."""
    now = _utcnow()
    for sid in soldier_ids:
        db.add(
            UserCollection(
                user_id=user_id,
                soldier_id=sid,
                source=source,
                unlocked_at=now,
            )
        )
    db.commit()
    return len(soldier_ids)
