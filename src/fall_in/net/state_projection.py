"""
Client-side visual projection for multiplayer card state.

Design principle (from multiplayer plan §8):
  - The server sends only number / danger / owner_seat in public state.
  - Each client projects its OWN collection onto cards it owns.
  - Cards belonging to other seats always render as "unknown_default".
  - This means the same card number can legitimately render differently on
    different clients — that is intentional and correct.

No server data is modified here.  These helpers are pure functions that
take a viewer's local state and return a sprite/visual identifier string.
"""

from __future__ import annotations


_UNKNOWN_VISUAL = "unknown_default"


def resolve_card_visual(
    card_number: int,
    owner_seat: int,
    viewer_seat: int,
    viewer_collection: set[int],
) -> str:
    """
    Determine the visual identifier for a card on the board or in hand.

    Args:
        card_number:       The card's number (1-104).
        owner_seat:        Seat index of the player who played / owns the card.
        viewer_seat:       Seat index of the local viewer.
        viewer_collection: Set of card numbers the viewer has collected
                           (from their local or server-side collection).

    Returns:
        A sprite/asset key string:
          - ``"soldier_{number}"``   when the viewer owns the card AND has
                                     collected (interviewed) it.
          - ``"unknown_default"``    in all other cases.

    Notes:
        Cards played by other seats always return ``"unknown_default"``,
        even if the viewer happens to own the same number in their collection.
        The viewer's private hand cards (owner_seat == viewer_seat) are
        visible only when collected.
    """
    if owner_seat != viewer_seat:
        return _UNKNOWN_VISUAL
    if card_number not in viewer_collection:
        return _UNKNOWN_VISUAL
    return f"soldier_{card_number}"


def resolve_hand_card_visual(
    card_number: int,
    viewer_collection: set[int],
) -> str:
    """
    Determine the visual for a card in the viewer's own hand.

    Convenience wrapper — hand cards are always owner == viewer.

    Args:
        card_number:       The card's number (1-104).
        viewer_collection: Set of card numbers the viewer has collected.

    Returns:
        ``"soldier_{number}"`` if collected, else ``"unknown_default"``.
    """
    if card_number not in viewer_collection:
        return _UNKNOWN_VISUAL
    return f"soldier_{card_number}"
