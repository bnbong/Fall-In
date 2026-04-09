"""
Server-side match state models.

ActiveMatch owns the authoritative GameRules instance for a running match.
All state mutations go through MatchService.

Design rules (from multiplayer plan):
  - player_id == seat_index for all seats.
  - board_row_owners tracks per-card seat ownership for PublicMatchState serialisation.
  - Starter cards (dealt to rows at round start) have owner_seat = -1.
  - last_turn_steps holds the most recently resolved turn's placements;
    it is cleared at the start of each new round.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    pass

from app.models.room import SeatControllerType


@dataclass
class MatchSeat:
    """Per-seat match identity: maps a room participant to a GameRules Player."""

    seat_index: int
    # fall_in.core.player.Player — typed as object to avoid circular import at module load
    player: object
    connection_id: Optional[str]  # None for bots; cleared on disconnect
    user_id: Optional[str]  # None for guests and bots
    display_name: str
    controller_type: SeatControllerType
    # "registered" | "guest" | "bot" — used by MmrService to determine whether
    # MMR should be persisted for this seat after the match ends.
    account_type: str = "guest"
    ai_controller: Optional[object] = None  # fall_in.ai.ai_player.AIPlayer; None for human seats

    # Presence / reconnect state (PR-05).
    # is_disconnected: True between WebSocketDisconnect and successful reconnect.
    # disconnected_at: time.time() value recorded when is_disconnected becomes True.
    # took_over_by_bot: True once the grace period has expired and the seat has
    #   been permanently converted to bot control.  Cannot be reversed.
    is_disconnected: bool = False
    disconnected_at: Optional[float] = None
    took_over_by_bot: bool = False


@dataclass
class TurnStep:
    """Result of a single card placement during turn resolution."""

    seat_index: int
    card_number: int
    card_danger: int
    row_index: int
    penalty_score: int
    had_to_take_row: bool
    order: int  # 1-based placement order
    penalty_card_count: int = 0  # number of penalty cards taken in this placement


@dataclass
class RoundSummary:
    """Scores and elimination info produced by MatchService.finalize_round()."""

    round_number: int
    round_danger: dict[int, int]  # seat_index -> danger this round
    total_scores: dict[int, int]  # seat_index -> cumulative danger
    eliminated_seats: list[int]
    game_over: bool
    winner_seat: Optional[int]


@dataclass
class ActiveMatch:
    """Live match owned by MatchService."""

    match_id: str
    room_code: str
    rules: object  # fall_in.core.rules.GameRules
    seats: dict[int, MatchSeat]  # seat_index -> MatchSeat
    player_to_seat: dict[int, int]  # player_id -> seat_index

    # Parallel ownership tracking for board rows.
    # board_row_owners[row_idx][pos] = seat_index (-1 for starter cards).
    board_row_owners: list[list[int]] = field(default_factory=lambda: [[], [], [], []])

    # Most recently resolved turn's TurnStep list (cleared at round start).
    last_turn_steps: list[TurnStep] = field(default_factory=list)

    # Timestamp (time.time()) set when the SELECTING phase begins.
    # Used by the card-selection timeout task to know when the timer started.
    selection_started_at: Optional[float] = None

    # True when this match was created from the quick-match queue (PR-06).
    # Determines whether MMR updates are applied after the game ends.
    # Custom-room matches always have is_ranked=False.
    is_ranked: bool = False

    # Round-settlement coordination (client result screen before continuing).
    round_settlement_pending: bool = False
    round_settlement_ready_seats: set[int] = field(default_factory=set)
    round_summary_pending: Optional[RoundSummary] = None

    # Seats that voluntarily left mid-match (MATCH_LEAVE).
    # They are converted to bot immediately but marked as eliminated
    # at the end of the current round in finalize_round().
    voluntarily_left_seats: set[int] = field(default_factory=set)
