"""
Serializers for network-safe state objects.

Rules enforced here:
  - A Card's private cosmetic fields (is_collected, name, rank, unit, note,
    body_type) are NEVER included in any dict that will be sent over the wire.
  - Only MatchCardPublic (number, danger, owner_seat) crosses the network.
  - PublicMatchState and PrivatePlayerState are serialized separately; the
    private state is sent only to the owning seat.

These functions work on the DTO types defined in fall_in.multiplayer.models.
They do NOT import Card directly — the boundary is enforced by accepting only
MatchCardPublic instances.
"""

from __future__ import annotations

from typing import Any

from fall_in.multiplayer.models import (
    MatchCardPublic,
    PublicMatchState,
    PrivatePlayerState,
    SeatIdentity,
)

# Fields that must NEVER appear in a public-facing dict.
# Checked at runtime by the assertion helpers below.
_PRIVATE_CARD_FIELDS: frozenset[str] = frozenset(
    {"is_collected", "name", "rank", "unit", "note", "body_type"}
)


# ---------------------------------------------------------------------------
# Card DTO
# ---------------------------------------------------------------------------


def match_card_to_dict(card: MatchCardPublic) -> dict[str, Any]:
    """Serialise a public card DTO to a plain dict safe for JSON encoding."""
    return {
        "number": card.number,
        "danger": card.danger,
        "owner_seat": card.owner_seat,
    }


def _assert_no_private_fields(d: dict[str, Any], context: str = "") -> None:
    """Raise AssertionError if any private card field is present in *d*."""
    leaked = _PRIVATE_CARD_FIELDS & d.keys()
    if leaked:
        raise AssertionError(
            f"Private card fields leaked into public dict{' (' + context + ')' if context else ''}: "
            f"{leaked}"
        )


# ---------------------------------------------------------------------------
# Seat identity
# ---------------------------------------------------------------------------


def seat_identity_to_dict(seat: SeatIdentity) -> dict[str, Any]:
    """
    Serialise a SeatIdentity for broadcast.

    user_id is always omitted — it is a stable account identifier that
    other clients have no need for.  display_name is the only identity
    signal in public match state.
    """
    return {
        "seat_index": seat.seat_index,
        "controller_type": seat.controller_type.value,
        "display_name": seat.display_name,
    }


# ---------------------------------------------------------------------------
# Public match state
# ---------------------------------------------------------------------------


def public_state_to_dict(state: PublicMatchState) -> dict[str, Any]:
    """
    Serialise PublicMatchState to a wire-safe dict.

    Asserts that no private card fields are present before returning.
    """
    board_rows = [
        [match_card_to_dict(c) for c in row] for row in state.board_rows
    ]
    played_this_turn = [match_card_to_dict(c) for c in state.played_cards_this_turn]
    seats = [seat_identity_to_dict(s) for s in state.seats]

    result: dict[str, Any] = {
        "match_id": state.match_id,
        "round_number": state.round_number,
        "phase": state.phase,
        "player_order_seats": state.player_order_seats,
        "board_rows": board_rows,
        "played_cards_this_turn": played_this_turn,
        "committed_scores": state.committed_scores,
        "seats": seats,
    }

    # Runtime safety: walk every card dict and assert no leakage.
    for row in board_rows:
        for card_dict in row:
            _assert_no_private_fields(card_dict, context="board_rows")
    for card_dict in played_this_turn:
        _assert_no_private_fields(card_dict, context="played_cards_this_turn")

    return result


# ---------------------------------------------------------------------------
# Private player state
# ---------------------------------------------------------------------------


def private_state_to_dict(state: PrivatePlayerState) -> dict[str, Any]:
    """
    Serialise PrivatePlayerState to a dict.

    This is only ever sent to the owning seat — never broadcast.
    Hand cards are the player's own cards (owner_seat == viewer_seat), so
    cosmetic projection happens client-side after deserialisation.
    """
    hand = [match_card_to_dict(c) for c in state.hand]
    result: dict[str, Any] = {
        "seat_index": state.seat_index,
        "hand": hand,
        "has_selected": state.has_selected,
    }
    return result
