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

from typing import Optional

from fall_in.multiplayer.models import PrivatePlayerState, PublicMatchState


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

    # ------------------------------------------------------------------
    # Write path (called by the WS receive loop)
    # ------------------------------------------------------------------

    def apply_public_state(self, state: PublicMatchState) -> None:
        """Cache the latest public match state broadcast by the server."""
        self._public = state

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
