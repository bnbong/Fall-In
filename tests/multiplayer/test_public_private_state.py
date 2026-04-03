"""
Tests for the public/private state boundary and collection-field exclusion.

These tests enforce the core multiplayer invariant:
  Private cosmetic fields (is_collected, name, rank, unit, note, body_type)
  must NEVER appear in any public-facing DTO or serialised dict.

They also verify that PrivatePlayerState is never reachable from
PublicMatchState — the two objects are always kept separate.
"""

import dataclasses
import pytest

from fall_in.multiplayer.models import (
    MatchCardPublic,
    PublicMatchState,
    PrivatePlayerState,
    AccountProgressRef,
    SeatIdentity,
    ControllerType,
)
from fall_in.net.serializers import (
    match_card_to_dict,
    public_state_to_dict,
    private_state_to_dict,
    _PRIVATE_CARD_FIELDS,
)
from fall_in.net.state_projection import resolve_card_visual, resolve_hand_card_visual
from fall_in.core.card import Card


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_card(number: int = 42) -> Card:
    """Create a Card with all private cosmetic fields populated."""
    from fall_in.core.card import calculate_danger

    return Card(
        number=number,
        danger=calculate_danger(number),
        is_collected=True,
        name="홍길동",
        rank="병장",
        unit="제1전투비행단",
        note="우수 병사",
        body_type="NORMAL",
    )


def _make_public_card(number: int = 42, owner_seat: int = 0) -> MatchCardPublic:
    from fall_in.core.card import calculate_danger

    return MatchCardPublic(
        number=number,
        danger=calculate_danger(number),
        owner_seat=owner_seat,
    )


def _make_seat(
    seat_index: int = 0, controller_type: ControllerType = ControllerType.LOCAL
) -> SeatIdentity:
    return SeatIdentity(
        seat_index=seat_index,
        controller_type=controller_type,
        display_name=f"Player {seat_index}",
    )


def _make_public_state(
    board_cards: list[MatchCardPublic] | None = None,
) -> PublicMatchState:
    cards = board_cards or [_make_public_card(10, 0)]
    return PublicMatchState(
        match_id="test-match-001",
        round_number=1,
        phase="SELECTING",
        player_order_seats=[0, 1, 2, 3],
        board_rows=[[c] for c in cards],
        played_cards_this_turn=[],
        committed_scores={0: 0, 1: 0, 2: 0, 3: 0},
        seats=[_make_seat(i) for i in range(4)],
    )


# ---------------------------------------------------------------------------
# MatchCardPublic field contract
# ---------------------------------------------------------------------------


class TestMatchCardPublicFields:
    """MatchCardPublic must have exactly the three allowed fields."""

    def test_has_number_danger_owner_seat(self):
        card = _make_public_card(42, 2)
        assert card.number == 42
        assert card.danger == 1
        assert card.owner_seat == 2

    def test_private_fields_do_not_exist_on_match_card_public(self):
        card = _make_public_card()
        for field_name in _PRIVATE_CARD_FIELDS:
            assert not hasattr(card, field_name), (
                f"MatchCardPublic must not have field '{field_name}'"
            )

    def test_match_card_public_dataclass_fields_are_exactly_three(self):
        field_names = {f.name for f in dataclasses.fields(MatchCardPublic)}
        assert field_names == {"number", "danger", "owner_seat"}

    def test_match_card_public_is_frozen(self):
        card = _make_public_card()
        with pytest.raises((dataclasses.FrozenInstanceError, AttributeError)):
            card.number = 99  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Serialiser — single card
# ---------------------------------------------------------------------------


class TestMatchCardToDict:
    """card_to_public_dto must strip all private fields."""

    def test_dict_contains_only_allowed_keys(self):
        card = _make_public_card(55, 1)
        d = match_card_to_dict(card)
        assert set(d.keys()) == {"number", "danger", "owner_seat"}

    def test_dict_values_are_correct(self):
        card = _make_public_card(66, 3)
        d = match_card_to_dict(card)
        assert d["number"] == 66
        assert d["danger"] == 7  # Card 66 has danger 7
        assert d["owner_seat"] == 3

    def test_no_private_fields_in_dict(self):
        card = _make_public_card(42, 0)
        d = match_card_to_dict(card)
        for field_name in _PRIVATE_CARD_FIELDS:
            assert field_name not in d, (
                f"Private field '{field_name}' leaked into public card dict"
            )


# ---------------------------------------------------------------------------
# Serialiser — public state
# ---------------------------------------------------------------------------


class TestPublicStateSerialization:
    """public_state_to_dict must produce a clean wire-safe dict."""

    def test_serialised_dict_has_expected_top_level_keys(self):
        state = _make_public_state()
        d = public_state_to_dict(state)
        expected_keys = {
            "match_id",
            "round_number",
            "phase",
            "player_order_seats",
            "board_rows",
            "played_cards_this_turn",
            "committed_scores",
            "seats",
        }
        assert set(d.keys()) == expected_keys

    def test_board_row_cards_have_no_private_fields(self):
        cards = [_make_public_card(n, 0) for n in [10, 30, 50, 70]]
        state = _make_public_state(board_cards=cards)
        d = public_state_to_dict(state)
        for row in d["board_rows"]:
            for card_dict in row:
                for field_name in _PRIVATE_CARD_FIELDS:
                    assert field_name not in card_dict, (
                        f"Private field '{field_name}' found in board row card dict"
                    )

    def test_played_cards_this_turn_have_no_private_fields(self):
        state = _make_public_state()
        state.played_cards_this_turn = [
            _make_public_card(42, 1),
            _make_public_card(77, 2),
        ]
        d = public_state_to_dict(state)
        for card_dict in d["played_cards_this_turn"]:
            for field_name in _PRIVATE_CARD_FIELDS:
                assert field_name not in card_dict

    def test_serialiser_raises_if_private_field_injected(self):
        """
        Guard: if someone accidentally puts a raw dict with private fields
        into the state, the serialiser's assertion must catch it.
        """
        # We test the assertion helper directly.
        from fall_in.net.serializers import _assert_no_private_fields

        bad_dict = {"number": 1, "danger": 1, "owner_seat": 0, "is_collected": True}
        with pytest.raises(AssertionError, match="is_collected"):
            _assert_no_private_fields(bad_dict, context="test")

    def test_round_number_and_phase_preserved(self):
        state = _make_public_state()
        state.round_number = 3
        state.phase = "PLACING"
        d = public_state_to_dict(state)
        assert d["round_number"] == 3
        assert d["phase"] == "PLACING"

    def test_committed_scores_are_seat_indexed(self):
        state = _make_public_state()
        state.committed_scores = {0: 5, 1: 12, 2: 0, 3: 33}
        d = public_state_to_dict(state)
        # Keys become strings after JSON round-trip, but at serialiser level they're int.
        assert d["committed_scores"][0] == 5
        assert d["committed_scores"][3] == 33


# ---------------------------------------------------------------------------
# Serialiser — private state
# ---------------------------------------------------------------------------


class TestPrivateStateSerialization:
    """private_state_to_dict reflects hand cards — these stay private."""

    def test_private_state_contains_seat_index_and_hand(self):
        priv = PrivatePlayerState(
            seat_index=2,
            hand=[_make_public_card(42, 2), _make_public_card(77, 2)],
            has_selected=False,
        )
        d = private_state_to_dict(priv)
        assert d["seat_index"] == 2
        assert len(d["hand"]) == 2
        assert d["has_selected"] is False

    def test_hand_card_dicts_have_no_private_fields(self):
        priv = PrivatePlayerState(
            seat_index=0,
            hand=[_make_public_card(n, 0) for n in [5, 15, 25]],
        )
        d = private_state_to_dict(priv)
        for card_dict in d["hand"]:
            for field_name in _PRIVATE_CARD_FIELDS:
                assert field_name not in card_dict


# ---------------------------------------------------------------------------
# State separation — public never exposes private
# ---------------------------------------------------------------------------


class TestStateSeparation:
    """PublicMatchState and PrivatePlayerState are distinct, non-overlapping objects."""

    def test_public_state_has_no_hand_field(self):
        state = _make_public_state()
        assert not hasattr(state, "hand"), (
            "PublicMatchState must not contain a 'hand' field"
        )

    def test_private_state_has_no_board_rows_field(self):
        priv = PrivatePlayerState(seat_index=1)
        assert not hasattr(priv, "board_rows"), (
            "PrivatePlayerState must not contain 'board_rows'"
        )

    def test_public_and_private_are_independent_objects(self):
        state = _make_public_state()
        priv = PrivatePlayerState(
            seat_index=0,
            hand=[_make_public_card(42, 0)],
        )
        # Modifying private state must not affect public state
        priv.hand.append(_make_public_card(55, 0))
        assert all(len(row) == 1 for row in state.board_rows)

    def test_public_state_serialised_dict_has_no_hand_key(self):
        state = _make_public_state()
        d = public_state_to_dict(state)
        assert "hand" not in d


# ---------------------------------------------------------------------------
# AccountProgressRef — local-only, not broadcast
# ---------------------------------------------------------------------------


class TestAccountProgressRef:
    """AccountProgressRef is a local-only object; it has no serialiser."""

    def test_has_collected_returns_true_for_owned_number(self):
        ref = AccountProgressRef(user_id="user-001", collection={10, 42, 77})
        assert ref.has_collected(42) is True

    def test_has_collected_returns_false_for_missing(self):
        ref = AccountProgressRef(user_id="user-001", collection={10, 42})
        assert ref.has_collected(99) is False

    def test_guest_ref_has_no_user_id(self):
        ref = AccountProgressRef(user_id=None, collection={5, 6})
        assert ref.user_id is None

    def test_account_progress_ref_has_no_serialiser(self):
        """There must be no public serialise function for AccountProgressRef."""
        import fall_in.net.serializers as ser

        # Verify no function named *_account_progress* is exported
        public_names = [n for n in dir(ser) if not n.startswith("_")]
        for name in public_names:
            assert "account_progress" not in name.lower(), (
                f"Unexpected serialiser for AccountProgressRef found: '{name}'"
            )


# ---------------------------------------------------------------------------
# Viewer projection
# ---------------------------------------------------------------------------


class TestResolveCardVisual:
    """resolve_card_visual enforces the cosmetic projection rules."""

    def test_own_collected_card_returns_soldier_key(self):
        result = resolve_card_visual(
            card_number=42,
            owner_seat=1,
            viewer_seat=1,
            viewer_collection={42, 55},
        )
        assert result == "soldier_42"

    def test_own_uncollected_card_returns_unknown(self):
        result = resolve_card_visual(
            card_number=42,
            owner_seat=1,
            viewer_seat=1,
            viewer_collection={55},  # 42 not collected
        )
        assert result == "unknown_default"

    def test_other_seat_card_always_returns_unknown(self):
        result = resolve_card_visual(
            card_number=42,
            owner_seat=2,
            viewer_seat=1,
            viewer_collection={42, 55, 2},  # Even if collected, must be unknown
        )
        assert result == "unknown_default"

    def test_empty_collection_always_returns_unknown(self):
        result = resolve_card_visual(
            card_number=1,
            owner_seat=0,
            viewer_seat=0,
            viewer_collection=set(),
        )
        assert result == "unknown_default"

    def test_hand_card_visual_collected(self):
        result = resolve_hand_card_visual(card_number=10, viewer_collection={10, 20})
        assert result == "soldier_10"

    def test_hand_card_visual_not_collected(self):
        result = resolve_hand_card_visual(card_number=10, viewer_collection={20})
        assert result == "unknown_default"

    def test_same_card_different_owners_different_visuals(self):
        """
        The same card number renders differently depending on who owns it.
        This is the intended multi-client cosmetic behaviour.
        """
        card_number = 42
        viewer_seat = 0
        collection = {42}  # viewer has collected this card

        # Own card → personalised
        own = resolve_card_visual(
            card_number,
            owner_seat=0,
            viewer_seat=viewer_seat,
            viewer_collection=collection,
        )
        # Other player's card → unknown
        other = resolve_card_visual(
            card_number,
            owner_seat=1,
            viewer_seat=viewer_seat,
            viewer_collection=collection,
        )

        assert own == "soldier_42"
        assert other == "unknown_default"
        assert own != other


# ---------------------------------------------------------------------------
# Card → public DTO conversion (using a Card domain object)
# ---------------------------------------------------------------------------


class TestCardDomainToPublicDto:
    """
    When converting a raw Card to a public network DTO, private fields
    must be stripped.  This tests the conversion pattern PR-04 adapters
    will use.
    """

    def test_card_with_all_private_fields_converts_safely(self):
        card = _make_card(42)  # has name, rank, etc.
        # Manual conversion (the adapter will do this in PR-04)
        pub = MatchCardPublic(
            number=card.number,
            danger=card.danger,
            owner_seat=0,
        )
        d = match_card_to_dict(pub)
        assert "is_collected" not in d
        assert "name" not in d
        assert "rank" not in d
        assert "unit" not in d
        assert "note" not in d
        assert "body_type" not in d

    def test_card_number_and_danger_are_preserved(self):
        card = _make_card(66)  # danger 7, special card
        pub = MatchCardPublic(number=card.number, danger=card.danger, owner_seat=2)
        assert pub.number == 66
        assert pub.danger == 7

    def test_two_cards_with_same_number_but_different_owners_are_not_equal(self):
        """owner_seat is part of the public DTO identity."""
        pub_a = MatchCardPublic(number=42, danger=1, owner_seat=0)
        pub_b = MatchCardPublic(number=42, danger=1, owner_seat=1)
        assert pub_a != pub_b
