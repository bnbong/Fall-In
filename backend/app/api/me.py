"""
/me — authenticated user's own profile and collection.

GET /me/profile    — available to registered and guest users
GET /me/collection — registered users only (guests have no persistent collection)
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user, require_registered
from app.models.db import User
from app.repositories import collection_repo
from app.schemas.profile import CollectionEntry, CollectionResponse, ProfileResponse

router = APIRouter(prefix="/me", tags=["me"])


@router.get("/profile", response_model=ProfileResponse)
def get_profile(user: User = Depends(get_current_user)) -> ProfileResponse:
    """
    Return the authenticated user's public profile.

    Available to both registered and guest users.
    Note: hidden_mmr is intentionally NOT included in the response.
    """
    return ProfileResponse(
        user_id=user.id,
        nickname=user.profile.nickname,
        avatar_id=user.profile.avatar_id,
        currency=user.profile.currency,
        total_games=user.profile.total_games,
        total_wins=user.profile.total_wins,
        account_type=user.account_type.value,
    )


@router.get("/collection", response_model=CollectionResponse)
def get_collection(
    user: User = Depends(require_registered),
    db: Session = Depends(get_db),
) -> CollectionResponse:
    """
    Return the authenticated user's soldier collection.

    Restricted to registered accounts — guests receive 403.
    The collection is keyed exclusively by user_id, so one user's
    collection is never visible to another.
    """
    rows = collection_repo.get_for_user(db, user.id)
    items = [
        CollectionEntry(
            soldier_id=row.soldier_id,
            unlocked_at=row.unlocked_at,
            source=row.source,
        )
        for row in rows
    ]
    return CollectionResponse(items=items, total=len(items))
