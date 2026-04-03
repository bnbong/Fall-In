"""
Multiplayer state models — network-safe DTOs and seat identity types.

Design invariants enforced here (from multiplayer plan §§ 4, 8, 19):

1. MatchCardPublic contains ONLY number / danger / owner_seat.
   Private cosmetic fields (is_collected, name, rank, unit, note, body_type)
   are deliberately absent.  If you need to add a field, add it to Card in
   fall_in.core.card — NOT here.

2. seat_index ≠ user_id.
   A seat is a position in a room (0-3).  A user is an account.  Guests have
   no persistent user_id.  Bots have no user_id at all.

3. AccountProgressRef is NEVER broadcast.  It exists only on the client that
   owns it and is used for local cosmetic projection only.

4. PublicMatchState and PrivatePlayerState are always separate objects.
   Public state is broadcast to all seats.  Private state is unicast to the
   owning seat only.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


# ---------------------------------------------------------------------------
# Seat identity
# ---------------------------------------------------------------------------


class ControllerType(str, Enum):
    """Who (or what) controls a seat."""

    LOCAL = "local"  # Human on this client (single-player path)
    REMOTE = "remote"  # Human on another client (multiplayer)
    BOT = "bot"  # AI-controlled seat


@dataclass
class SeatIdentity:
    """
    Maps a seat position to the entity that controls it.

    seat_index    : 0-3, position at the table this round.
    controller_type: LOCAL | REMOTE | BOT.
    user_id       : Persistent account id (None for guests and bots).
    display_name  : Name shown in UI (player nickname or "AI N").
    """

    seat_index: int
    controller_type: ControllerType
    display_name: str
    user_id: Optional[str] = None  # None for guests and bots

    def is_bot(self) -> bool:
        return self.controller_type == ControllerType.BOT

    def is_guest(self) -> bool:
        return self.controller_type == ControllerType.REMOTE and self.user_id is None


# ---------------------------------------------------------------------------
# Card DTO — the ONLY card representation allowed in public match state
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MatchCardPublic:
    """
    Network-safe card representation for public match state.

    Contains only the fields needed for game logic and board rendering.
    Private cosmetic fields from Card are intentionally excluded.

    Fields intentionally NOT present (must never be added here):
      - is_collected
      - name
      - rank
      - unit
      - note
      - body_type
      - portrait path
      - figure variant id
    """

    number: int  # 1-104
    danger: int  # 1-7
    owner_seat: int  # Seat index of the player who played this card


# ---------------------------------------------------------------------------
# Public match state — broadcast to all seats
# ---------------------------------------------------------------------------


@dataclass
class PublicMatchState:
    """
    The portion of match state that is safe to broadcast to every participant.

    board_rows              : Current board, each row is a list of MatchCardPublic.
    played_cards_this_turn  : Cards revealed this turn (in player_order sequence).
    committed_scores        : {seat_index: cumulative_danger} after round commit.
    player_order_seats      : Current turn's player_order as seat indices.
    seats                   : SeatIdentity for all 4 seats.
    phase                   : Current round phase string (matches RoundPhase.value).
    round_number            : 1-based current round.
    match_id                : Server-assigned match identifier.
    """

    match_id: str
    round_number: int
    phase: str
    player_order_seats: list[int]  # seat indices in play order
    board_rows: list[list[MatchCardPublic]]
    played_cards_this_turn: list[MatchCardPublic]
    committed_scores: dict[int, int]  # seat_index -> danger total
    seats: list[SeatIdentity]

    def get_seat(self, seat_index: int) -> Optional[SeatIdentity]:
        for s in self.seats:
            if s.seat_index == seat_index:
                return s
        return None


# ---------------------------------------------------------------------------
# Private player state — unicast to the owning seat only
# ---------------------------------------------------------------------------


@dataclass
class PrivatePlayerState:
    """
    The portion of match state visible only to the owning seat.

    hand        : The player's current hand as MatchCardPublic entries.
                  owner_seat is always this player's seat_index.
    has_selected: Whether this seat has already committed a card this turn.
    seat_index  : Which seat this private state belongs to.

    Note: hand cards use MatchCardPublic (number/danger/owner_seat).
    The client applies cosmetic projection locally using AccountProgressRef.
    """

    seat_index: int
    hand: list[MatchCardPublic] = field(default_factory=list)
    has_selected: bool = False


# ---------------------------------------------------------------------------
# Account progress reference — local only, never sent to server in public state
# ---------------------------------------------------------------------------


@dataclass
class AccountProgressRef:
    """
    Client-side reference to the viewer's own persistent progression.

    This is NEVER serialised into public match state or broadcast.
    It is used solely for local cosmetic projection (resolve_card_visual).

    user_id    : None for guests (cosmetics derived from local JSON save).
    collection : Set of card numbers the viewer has collected (interviewed).
                 Populated from server profile (logged-in) or local
                 collected_soldiers.json (guest / single-player).
    """

    user_id: Optional[str]
    collection: set[int] = field(default_factory=set)

    def has_collected(self, card_number: int) -> bool:
        return card_number in self.collection
