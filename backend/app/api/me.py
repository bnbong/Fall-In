"""
/me — authenticated user's own profile and collection.

GET /me/profile    — available to registered and guest users
GET /me/collection — registered users only (guests have no persistent collection)
"""

import time

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.dependencies import get_current_user, require_registered
from app.models.db import User
from app.repositories import collection_repo, profile_repo
from app.schemas.profile import CollectionEntry, CollectionResponse, ProfileResponse
from app.schemas.progress import (
    CollectionUnlockRequest,
    CollectionUnlockResponse,
    ProgressMergeRequest,
    ProgressMergeResponse,
    RewardClaimRequest,
    RewardClaimResponse,
)

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


@router.post("/progress/merge", response_model=ProgressMergeResponse)
def merge_progress(
    req: ProgressMergeRequest,
    user: User = Depends(require_registered),
    db: Session = Depends(get_db),
) -> ProgressMergeResponse:
    """
    Merge local single-player progress into the registered server account.

    Merge strategy is intentionally conservative for beta:
      - currency keeps the larger of {server, local}
      - collection becomes the union of {server, local}

    This protects the common "old local save + new online account" case
    without forcing the client to reconcile multiple sources first.
    """
    current_rows = collection_repo.get_for_user(db, user.id)
    current_ids = {row.soldier_id for row in current_rows}
    merged_ids = current_ids | set(req.collected_soldier_ids)

    new_ids = sorted(merged_ids - current_ids)
    if new_ids:
        collection_repo.add_soldiers_batch(db, user.id, new_ids, source="client_merge")

    merged_currency = max(user.profile.currency, req.currency)
    if user.profile.currency != merged_currency:
        profile_repo.set_currency(db, user.profile, merged_currency)

    return ProgressMergeResponse(
        currency=merged_currency,
        collected_soldier_ids=sorted(merged_ids),
        total_collected=len(merged_ids),
    )


# Per-user rate-limit state for single-play reward claims.
# Key: user_id, Value: last claim timestamp.
_reward_last_claim: dict[str, float] = {}


@router.post("/reward", response_model=RewardClaimResponse)
def claim_reward(
    req: RewardClaimRequest,
    user: User = Depends(require_registered),
    db: Session = Depends(get_db),
) -> RewardClaimResponse:
    """
    Claim a delta-based currency reward from a single-player game.

    The server validates:
      - amount does not exceed REWARD_SINGLE_PLAY_MAX
      - minimum cooldown between claims (rate-limit)
    """
    if req.amount > settings.REWARD_SINGLE_PLAY_MAX:
        raise HTTPException(status_code=422, detail="Reward amount exceeds maximum")

    now = time.monotonic()
    last = _reward_last_claim.get(user.id, 0.0)
    if now - last < settings.REWARD_SINGLE_PLAY_COOLDOWN_SECONDS:
        raise HTTPException(status_code=429, detail="Reward claim too frequent")
    _reward_last_claim[user.id] = now

    profile_repo.add_currency(db, user.profile, req.amount)
    return RewardClaimResponse(granted=req.amount, currency=user.profile.currency)


@router.post("/collection/unlock", response_model=CollectionUnlockResponse)
def unlock_collection_entry(
    req: CollectionUnlockRequest,
    user: User = Depends(require_registered),
    db: Session = Depends(get_db),
) -> CollectionUnlockResponse:
    """
    Idempotently unlock a collected soldier for the authenticated user.
    """
    added = False
    if not collection_repo.has_soldier(db, user.id, req.soldier_id):
        collection_repo.add_soldier(
            db,
            user.id,
            req.soldier_id,
            source="client_unlock",
        )
        added = True

    total = len(collection_repo.get_for_user(db, user.id))
    return CollectionUnlockResponse(
        soldier_id=req.soldier_id,
        added=added,
        total_collected=total,
    )
