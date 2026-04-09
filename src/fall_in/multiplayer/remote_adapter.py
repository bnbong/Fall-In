"""
RemoteGameAdapter — receives server-side state snapshots for rendering.

No game logic is executed here.  All authoritative state comes from the
server via WebSocket messages.  The adapter stores the latest snapshot of
each type and exposes them for the client renderer.

Usage (client-side networking loop)::

    adapter = RemoteGameAdapter(my_seat=1)

    # When PHASE_SELECTING / PUBLIC_BOARD_STATE arrives:
    state = deserialise_public_state(msg["data"])
    adapter.apply_public_state(state)

    # When PRIVATE_HAND_STATE arrives:
    priv = deserialise_private_state(msg["data"])
    adapter.apply_private_state(priv)

    # In the render loop:
    public = adapter.get_public_state()
    private = adapter.get_private_state()
    if public:
        render_board(public.board_rows)
    if private:
        render_hand(private.hand)

    if adapter.is_my_turn_to_select():
        send_card_select(chosen_card_number)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from fall_in.multiplayer.models import ControllerType, PrivatePlayerState, PublicMatchState


# Emote entry: (seat_index, emote_id)
EmoteEntry = tuple[int, str]


@dataclass(frozen=True)
class RevealStep:
    seat_index: int
    card_number: int
    placement_order: int = 0
    card_danger: int = 0
    row_index: int = 0
    penalty_score: int = 0
    had_to_take_row: bool = False
    penalty_card_count: int = 0


class RemoteGameAdapter:
    """
    Client-side adapter for remote (server-authoritative) matches.

    Caches the most recent PublicMatchState and PrivatePlayerState received
    from the server.  Rendering code reads these; the WS layer writes them.
    """

    def __init__(self, my_seat: int) -> None:
        self._my_seat = my_seat
        self._public: Optional[PublicMatchState] = None
        self._private: Optional[PrivatePlayerState] = None
        # Emotes received since the last call to pop_pending_emotes().
        # The renderer drains this list each frame to trigger display.
        self._pending_emotes: list[EmoteEntry] = []
        self._turn_reveal_active = False
        self._pending_reveal_steps: list[tuple[RevealStep, PublicMatchState]] = []
        self._pending_post_reveal_public: list[PublicMatchState] = []
        self._pending_selecting_phase_count = 0
        self._pending_selecting_remaining_times: list[float] = []
        self._pending_round_results: list[dict] = []
        self._pending_match_results: list[dict] = []
        self._disconnected_seats: set[int] = set()
        self._bot_takeover_seats: set[int] = set()
        # Per-seat penalty card counts for the current round.
        self._round_penalty_counts: dict[int, int] = {}
        self._last_penalty_round: int = 0
        # Selection timeout info queued from SELECTION_TIMEOUT messages.
        self._pending_selection_timeouts: list[list[int]] = []

    # ------------------------------------------------------------------
    # Write path (called by the WS receive loop)
    # ------------------------------------------------------------------

    def apply_public_state(self, state: PublicMatchState) -> None:
        """Cache the latest public match state broadcast by the server."""
        self._public = state

    def begin_turn_reveal(self) -> None:
        """Start buffering incremental turn-reveal snapshots."""
        self._turn_reveal_active = True

    def is_turn_reveal_active(self) -> bool:
        return self._turn_reveal_active or bool(self._pending_reveal_steps)

    def queue_turn_reveal_step(self, step_data: dict, snapshot: PublicMatchState) -> None:
        """Store one incremental placement snapshot for later playback."""
        penalty_card_count = int(step_data.get("penalty_card_count", 0))
        step = RevealStep(
            seat_index=step_data.get("seat_index", 0),
            card_number=step_data.get("card_number", 0),
            placement_order=step_data.get("placement_order", 0),
            card_danger=step_data.get("card_danger", 0),
            row_index=step_data.get("row_index", 0),
            penalty_score=step_data.get("penalty_score", 0),
            had_to_take_row=step_data.get("had_to_take_row", False),
            penalty_card_count=penalty_card_count,
        )
        # Auto-reset penalty counts when a new round starts.
        current_round = snapshot.round_number if snapshot else 0
        if current_round != self._last_penalty_round:
            self._round_penalty_counts.clear()
            self._last_penalty_round = current_round
        # Accumulate per-seat penalty card counts.
        if penalty_card_count > 0:
            seat = step.seat_index
            self._round_penalty_counts[seat] = (
                self._round_penalty_counts.get(seat, 0) + penalty_card_count
            )
        self._pending_reveal_steps.append((step, snapshot))

    def has_pending_reveal_steps(self) -> bool:
        return bool(self._pending_reveal_steps)

    def pop_next_reveal_step(self) -> Optional[tuple[RevealStep, PublicMatchState]]:
        if not self._pending_reveal_steps:
            return None
        return self._pending_reveal_steps.pop(0)

    def finish_turn_reveal(self) -> None:
        """Mark the reveal stream complete; queued steps still play out."""
        self._turn_reveal_active = False

    def queue_post_reveal_public_state(self, state: PublicMatchState) -> None:
        self._pending_post_reveal_public.append(state)

    def flush_post_reveal_public_states(self) -> list[PublicMatchState]:
        pending = list(self._pending_post_reveal_public)
        self._pending_post_reveal_public.clear()
        return pending

    def notify_selecting_phase_started(self, remaining_time: float = 30.0) -> None:
        """Record that the server started a fresh SELECTING phase."""
        self._pending_selecting_phase_count += 1
        self._pending_selecting_remaining_times.append(remaining_time)

    def consume_selecting_phase_started(self) -> Optional[float]:
        """Return the remaining_time for the next queued SELECTING event, or None."""
        if self._pending_selecting_phase_count <= 0:
            return None
        self._pending_selecting_phase_count -= 1
        if self._pending_selecting_remaining_times:
            return self._pending_selecting_remaining_times.pop(0)
        return 30.0

    def queue_round_result(self, data: dict) -> None:
        """Store a ROUND_RESULT payload until the renderer is ready for it."""
        self._pending_round_results.append(dict(data))

    def pop_round_result(self) -> Optional[dict]:
        """Return the oldest queued ROUND_RESULT payload, if any."""
        if not self._pending_round_results:
            return None
        return self._pending_round_results.pop(0)

    def queue_match_result(self, data: dict) -> None:
        """Store a MATCH_RESULT payload until the renderer consumes it."""
        self._pending_match_results.append(dict(data))

    def pop_match_result(self) -> Optional[dict]:
        """Return the oldest queued MATCH_RESULT payload, if any."""
        if not self._pending_match_results:
            return None
        return self._pending_match_results.pop(0)

    def get_round_penalty_card_count(self, seat_index: int) -> int:
        """Return the accumulated penalty card count for *seat_index* this round."""
        return self._round_penalty_counts.get(seat_index, 0)

    def reset_round_penalty_counts(self) -> None:
        """Clear per-seat penalty counts (called on new round)."""
        self._round_penalty_counts.clear()

    def notify_selection_timeout(self, timed_out_seats: list[int]) -> None:
        """Record a SELECTION_TIMEOUT event from the server."""
        self._pending_selection_timeouts.append(list(timed_out_seats))

    def pop_selection_timeout(self) -> Optional[list[int]]:
        """Return the oldest queued SELECTION_TIMEOUT seat list, if any."""
        if not self._pending_selection_timeouts:
            return None
        return self._pending_selection_timeouts.pop(0)

    def apply_emote(self, seat_index: int, emote_id: str) -> None:
        """
        Record an EMOTE_BROADCAST received from the server.

        The renderer calls pop_pending_emotes() each frame to consume these.
        """
        self._pending_emotes.append((seat_index, emote_id))

    def pop_pending_emotes(self) -> list[EmoteEntry]:
        """
        Return and clear all emotes received since the last call.

        The renderer should call this once per frame and trigger per-seat
        display animations for each returned entry.
        """
        pending = list(self._pending_emotes)
        self._pending_emotes.clear()
        return pending

    def apply_private_state(self, state: PrivatePlayerState) -> None:
        """
        Cache the private hand state unicast to this seat.

        Raises ValueError if the state is for a different seat.
        """
        if state.seat_index != self._my_seat:
            raise ValueError(
                f"PrivatePlayerState is for seat {state.seat_index}, "
                f"but this adapter is for seat {self._my_seat}"
            )
        self._private = state

    def mark_seat_disconnected(self, seat_index: int) -> None:
        if seat_index < 0:
            return
        self._disconnected_seats.add(seat_index)

    def mark_seat_reconnected(self, seat_index: int) -> None:
        if seat_index < 0:
            return
        self._disconnected_seats.discard(seat_index)
        self._bot_takeover_seats.discard(seat_index)

    def mark_seat_bot_takeover(self, seat_index: int) -> None:
        if seat_index < 0:
            return
        self._disconnected_seats.discard(seat_index)
        self._bot_takeover_seats.add(seat_index)
        if self._public is not None:
            seat = self._public.get_seat(seat_index)
            if seat is not None:
                seat.controller_type = ControllerType.BOT

    def is_seat_disconnected(self, seat_index: int) -> bool:
        return seat_index in self._disconnected_seats

    def is_seat_bot_takeover(self, seat_index: int) -> bool:
        return seat_index in self._bot_takeover_seats

    # ------------------------------------------------------------------
    # Read path (called by the renderer)
    # ------------------------------------------------------------------

    @property
    def my_seat(self) -> int:
        return self._my_seat

    def get_public_state(self) -> Optional[PublicMatchState]:
        """Latest broadcast state, or None before the first snapshot arrives."""
        return self._public

    def get_private_state(self) -> Optional[PrivatePlayerState]:
        """Latest hand state, or None before the first snapshot arrives."""
        return self._private

    def has_match_started(self) -> bool:
        """True after the first PublicMatchState is received."""
        return self._public is not None

    def get_phase(self) -> Optional[str]:
        """Current phase string (e.g. "SELECTING"), or None if no state yet."""
        return self._public.phase if self._public else None

    def is_my_turn_to_select(self) -> bool:
        """
        True when the phase is SELECTING and this seat has not yet submitted
        a card selection.
        """
        if self._public is None or self._private is None:
            return False
        return self._public.phase == "SELECTING" and not self._private.has_selected

    def get_my_hand_cards(self) -> list:
        """
        Return the list of MatchCardPublic in this seat's hand.
        Returns an empty list if no private state is available yet.
        """
        return list(self._private.hand) if self._private is not None else []

    def get_board_rows(self) -> list:
        """
        Return a snapshot of the current board rows (list of lists of
        MatchCardPublic).  Returns an empty list if no public state yet.
        """
        return [list(row) for row in self._public.board_rows] if self._public else []

    def get_committed_scores(self) -> dict:
        """Return {seat_index: cumulative_danger} or {} if no state."""
        return dict(self._public.committed_scores) if self._public else {}
