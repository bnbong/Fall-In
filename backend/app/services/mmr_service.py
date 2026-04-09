"""
Hidden MMR service (PR-06).

Responsibilities
----------------
* Read a player's current hidden MMR from the Profile row (or return DEFAULT_MMR
  if the profile has none set yet).
* Compute per-seat MMR deltas after a match ends using a simple 4-player Elo
  variant.
* Persist delta updates only for eligible matches:
    - Match must be a ranked quick-match (ActiveMatch.is_ranked == True).
    - 4 human seats  → full K-factor update.
    - 3 human seats  → half K-factor update.
    - ≤ 2 human seats → no update (AI-heavy; not meaningful data).

MMR is never exposed via the profile API.  It is used internally only for
matchmaking bucket assignment.

Delta formula (zero-sum across 4 players):
    winner:  +K points
    each of 3 losers: -K/3 points  (integer division; small rounding accepted)

Bucket thresholds (MMR → bucket name):
    0   – 799:  "bronze"
    800 – 1199: "silver"
    1200 – 1599: "gold"
    1600+:       "diamond"
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from app.config import settings
from app.models.db import Profile

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from app.models.match import ActiveMatch


# ---------------------------------------------------------------------------
# Bucket mapping
# ---------------------------------------------------------------------------

_BUCKET_THRESHOLDS: list[tuple[int, str]] = [
    (1600, "diamond"),
    (1200, "gold"),
    (800, "silver"),
    (0, "bronze"),
]


def mmr_to_bucket(mmr: int) -> str:
    """Return the bucket name for a given MMR value."""
    for threshold, name in _BUCKET_THRESHOLDS:
        if mmr >= threshold:
            return name
    return "bronze"


# ---------------------------------------------------------------------------
# MMR service
# ---------------------------------------------------------------------------


class MmrService:
    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def get_mmr(self, db: "Session", user_id: str) -> int:
        """
        Return the hidden MMR for a registered user.

        Falls back to DEFAULT_MMR if the profile row has no MMR set yet.
        Guests must never be passed here; call site is responsible for
        guarding with account_type checks.
        """
        profile: Optional[Profile] = db.get(Profile, user_id)
        if profile is None or profile.hidden_mmr is None:
            return settings.DEFAULT_MMR
        return profile.hidden_mmr

    def get_mmr_for_session(
        self,
        db: "Session",
        user_id: Optional[str],
        account_type: str,
    ) -> int:
        """
        Convenience wrapper: returns MMR for any session type.

        Guests always receive DEFAULT_MMR (not stored).
        """
        if account_type != "registered" or user_id is None:
            return settings.DEFAULT_MMR
        return self.get_mmr(db, user_id)

    # ------------------------------------------------------------------
    # Delta computation
    # ------------------------------------------------------------------

    def compute_deltas(
        self,
        winner_seat: int,
        human_seat_indices: list[int],
        k_factor: int,
    ) -> dict[int, int]:
        """
        Compute MMR delta for each human seat.

        Returns {seat_index: delta} (positive for winner, negative for losers).
        Only human seats are included; bot seats are not in the result.
        """
        if winner_seat not in human_seat_indices:
            # Winner was a bot (shouldn't happen in ranked matches, but guard).
            return {s: 0 for s in human_seat_indices}

        losers = [s for s in human_seat_indices if s != winner_seat]
        loser_penalty = k_factor // len(losers) if losers else 0

        deltas: dict[int, int] = {winner_seat: k_factor}
        for s in losers:
            deltas[s] = -loser_penalty
        return deltas

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def persist_updates(
        self,
        db: "Session",
        match: "ActiveMatch",
        winner_seat: int,
    ) -> None:
        """
        Apply MMR deltas for an eligible ranked match.

        Rules:
          - match.is_ranked must be True.
          - 4 human seats (no bot takeover) → full K.
          - 3 human seats                   → K // 2.
          - ≤ 2 human seats                 → no update.

        Only registered (non-guest) seats have their MMR persisted.
        Guest deltas are computed and discarded — guests do not accumulate MMR.
        """
        if not match.is_ranked:
            return

        from app.models.room import SeatControllerType

        # Count seats that were human throughout the match.
        # took_over_by_bot == True means the seat was converted mid-match.
        human_seats = [
            seat
            for seat in match.seats.values()
            if seat.controller_type == SeatControllerType.REMOTE and not seat.took_over_by_bot
        ]

        n_humans = len(human_seats)
        if n_humans <= 2:
            return

        k = settings.MMR_K_FACTOR if n_humans == 4 else settings.MMR_K_FACTOR // 2
        human_indices = [s.seat_index for s in human_seats]
        deltas = self.compute_deltas(winner_seat, human_indices, k)

        for seat in human_seats:
            if seat.account_type != "registered" or seat.user_id is None:
                continue  # guests: compute but don't store
            delta = deltas.get(seat.seat_index, 0)
            if delta == 0:
                continue

            profile: Optional[Profile] = db.get(Profile, seat.user_id)
            if profile is None:
                continue
            current = profile.hidden_mmr if profile.hidden_mmr is not None else settings.DEFAULT_MMR
            profile.hidden_mmr = max(0, current + delta)

        db.commit()


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

mmr_service = MmrService()
