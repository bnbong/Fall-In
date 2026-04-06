"""
Tests for LocalGameAdapter and RemoteGameAdapter.

Covers:
  - LocalGameAdapter wraps GameRules correctly
  - LocalGameAdapter produces DTO-safe state snapshots
  - RemoteGameAdapter caches and exposes server snapshots
  - RemoteGameAdapter rejects private state for wrong seat
"""

import pytest

from fall_in.ai.ai_player import create_ai_players
from fall_in.core.player import create_players
from fall_in.core.rules import GameRules, RoundPhase
from fall_in.multiplayer.local_adapter import LocalGameAdapter
from fall_in.multiplayer.models import (
    ControllerType,
    MatchCardPublic,
    PrivatePlayerState,
    PublicMatchState,
    SeatIdentity,
)
from fall_in.multiplayer.remote_adapter import RemoteGameAdapter
from fall_in.net.serializers import (
    _PRIVATE_CARD_FIELDS,
    private_state_to_dict,
    public_state_to_dict,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_local_adapter(match_id: str = "local-test") -> LocalGameAdapter:
    players = create_players()  # 1 human + 3 AI
    ai_controllers = create_ai_players(players)
    rules = GameRules(players)
    adapter = LocalGameAdapter(rules, ai_controllers, match_id=match_id)
    adapter.start_round()
    return adapter


def _make_public_state() -> PublicMatchState:
    card = MatchCardPublic(number=10, danger=3, owner_seat=0)
    return PublicMatchState(
        match_id="remote-test",
        round_number=1,
        phase="SELECTING",
        player_order_seats=[0, 1, 2, 3],
        board_rows=[[card]],
        played_cards_this_turn=[],
        committed_scores={0: 0, 1: 0, 2: 0, 3: 0},
        seats=[
            SeatIdentity(
                seat_index=i,
                controller_type=ControllerType.REMOTE,
                display_name=f"P{i}",
            )
            for i in range(4)
        ],
    )


def _make_private_state(seat: int = 0) -> PrivatePlayerState:
    return PrivatePlayerState(
        seat_index=seat,
        hand=[MatchCardPublic(number=42, danger=1, owner_seat=seat)],
        has_selected=False,
    )


# ---------------------------------------------------------------------------
# TestLocalGameAdapter
# ---------------------------------------------------------------------------


class TestLocalGameAdapter:
    def test_start_round_deals_ten_cards_to_human(self):
        adapter = _make_local_adapter()
        priv = adapter.get_private_state()
        assert len(priv.hand) == 10

    def test_start_round_bots_have_selected(self):
        players = create_players()
        ai_controllers = create_ai_players(players)
        rules = GameRules(players)
        adapter = LocalGameAdapter(rules, ai_controllers)
        adapter.start_round()
        for player in rules.players[1:]:  # seats 1-3 are bots
            assert player.selected_card is not None

    def test_human_has_not_selected_at_start(self):
        adapter = _make_local_adapter()
        priv = adapter.get_private_state()
        assert priv.has_selected is False

    def test_all_selected_false_before_human_picks(self):
        adapter = _make_local_adapter()
        assert not adapter.all_selected()

    def test_all_selected_true_after_human_picks(self):
        adapter = _make_local_adapter()
        card_number = adapter.get_private_state().hand[0].number
        adapter.select_card_for_human(card_number)
        assert adapter.all_selected()

    def test_select_invalid_card_raises(self):
        adapter = _make_local_adapter()
        with pytest.raises(ValueError, match="not in"):
            adapter.select_card_for_human(9999)

    def test_resolve_turn_returns_four_placements(self):
        adapter = _make_local_adapter()
        card_number = adapter.get_private_state().hand[0].number
        adapter.select_card_for_human(card_number)
        results = adapter.resolve_turn()
        assert len(results) == 4

    def test_resolve_turn_results_are_tuples_of_seat_and_card(self):
        adapter = _make_local_adapter()
        card_number = adapter.get_private_state().hand[0].number
        adapter.select_card_for_human(card_number)
        results = adapter.resolve_turn()
        for seat_idx, card in results:
            assert isinstance(seat_idx, int)
            assert isinstance(card, MatchCardPublic)

    def test_resolve_turn_card_owner_seat_matches_seat_index(self):
        adapter = _make_local_adapter()
        card_number = adapter.get_private_state().hand[0].number
        adapter.select_card_for_human(card_number)
        results = adapter.resolve_turn()
        for seat_idx, card in results:
            assert card.owner_seat == seat_idx

    def test_public_state_has_four_board_rows(self):
        adapter = _make_local_adapter()
        pub = adapter.get_public_state()
        assert len(pub.board_rows) == 4

    def test_public_state_phase_is_selecting(self):
        adapter = _make_local_adapter()
        pub = adapter.get_public_state()
        assert pub.phase == RoundPhase.SELECTING.name

    def test_public_state_no_private_card_fields(self):
        adapter = _make_local_adapter()
        pub = adapter.get_public_state()
        d = public_state_to_dict(pub)
        for row in d["board_rows"]:
            for card_dict in row:
                for field in _PRIVATE_CARD_FIELDS:
                    assert field not in card_dict

    def test_private_state_no_private_card_fields(self):
        adapter = _make_local_adapter()
        priv = adapter.get_private_state()
        d = private_state_to_dict(priv)
        for card_dict in d["hand"]:
            for field in _PRIVATE_CARD_FIELDS:
                assert field not in card_dict

    def test_private_state_hand_owner_seat_is_zero(self):
        """Human is always seat 0; hand cards must carry owner_seat=0."""
        adapter = _make_local_adapter()
        priv = adapter.get_private_state()
        for card in priv.hand:
            assert card.owner_seat == 0

    def test_public_state_seat_0_is_local(self):
        adapter = _make_local_adapter()
        pub = adapter.get_public_state()
        seat0 = pub.get_seat(0)
        assert seat0 is not None
        assert seat0.controller_type == ControllerType.LOCAL

    def test_public_state_other_seats_are_bots(self):
        adapter = _make_local_adapter()
        pub = adapter.get_public_state()
        for seat in pub.seats[1:]:
            assert seat.controller_type == ControllerType.BOT

    def test_is_round_over_false_before_ten_turns(self):
        adapter = _make_local_adapter()
        card_number = adapter.get_private_state().hand[0].number
        adapter.select_card_for_human(card_number)
        adapter.resolve_turn()
        assert not adapter.is_round_over()

    def test_commit_round_returns_seat_indexed_scores(self):
        adapter = _make_local_adapter()
        rules = adapter._rules
        # Play all 10 turns.
        for _ in range(10):
            card_number = adapter.get_private_state().hand[0].number
            adapter.select_card_for_human(card_number)
            adapter.resolve_turn()
            if not adapter.is_round_over():
                # Re-select bots for next turn.
                for player_id, ai in adapter._ai.items():
                    player = next(p for p in rules.players if p.player_id == player_id)
                    if not player.is_eliminated:
                        ai.select_card(rules.board)
        assert adapter.is_round_over()
        scores = adapter.commit_round()
        for seat_idx in range(4):
            assert seat_idx in scores
            rd, total = scores[seat_idx]
            assert rd >= 0 and total >= 0


# ---------------------------------------------------------------------------
# TestRemoteGameAdapter
# ---------------------------------------------------------------------------


class TestRemoteGameAdapter:
    def test_has_match_started_false_initially(self):
        adapter = RemoteGameAdapter(my_seat=1)
        assert not adapter.has_match_started()

    def test_apply_public_state_marks_match_started(self):
        adapter = RemoteGameAdapter(my_seat=1)
        adapter.apply_public_state(_make_public_state())
        assert adapter.has_match_started()

    def test_get_public_state_returns_applied_state(self):
        adapter = RemoteGameAdapter(my_seat=0)
        state = _make_public_state()
        adapter.apply_public_state(state)
        assert adapter.get_public_state() is state

    def test_get_private_state_returns_applied_state(self):
        adapter = RemoteGameAdapter(my_seat=2)
        priv = _make_private_state(seat=2)
        adapter.apply_private_state(priv)
        assert adapter.get_private_state() is priv

    def test_apply_private_state_wrong_seat_raises(self):
        adapter = RemoteGameAdapter(my_seat=1)
        priv = _make_private_state(seat=3)
        with pytest.raises(ValueError, match="seat 3"):
            adapter.apply_private_state(priv)

    def test_is_my_turn_false_without_state(self):
        adapter = RemoteGameAdapter(my_seat=0)
        assert not adapter.is_my_turn_to_select()

    def test_is_my_turn_true_when_selecting_and_not_selected(self):
        adapter = RemoteGameAdapter(my_seat=0)
        adapter.apply_public_state(_make_public_state())  # phase=SELECTING
        adapter.apply_private_state(_make_private_state(seat=0))  # has_selected=False
        assert adapter.is_my_turn_to_select()

    def test_is_my_turn_false_after_selecting(self):
        adapter = RemoteGameAdapter(my_seat=0)
        adapter.apply_public_state(_make_public_state())
        priv = PrivatePlayerState(
            seat_index=0,
            hand=[MatchCardPublic(number=42, danger=1, owner_seat=0)],
            has_selected=True,
        )
        adapter.apply_private_state(priv)
        assert not adapter.is_my_turn_to_select()

    def test_get_my_hand_cards_empty_before_state(self):
        adapter = RemoteGameAdapter(my_seat=0)
        assert adapter.get_my_hand_cards() == []

    def test_get_my_hand_cards_returns_hand(self):
        adapter = RemoteGameAdapter(my_seat=1)
        priv = _make_private_state(seat=1)
        adapter.apply_private_state(priv)
        cards = adapter.get_my_hand_cards()
        assert len(cards) == 1
        assert cards[0].number == 42

    def test_get_board_rows_empty_before_state(self):
        adapter = RemoteGameAdapter(my_seat=0)
        assert adapter.get_board_rows() == []

    def test_get_board_rows_returns_snapshot(self):
        adapter = RemoteGameAdapter(my_seat=0)
        adapter.apply_public_state(_make_public_state())
        rows = adapter.get_board_rows()
        assert len(rows) == 1  # _make_public_state has 1 row with 1 card

    def test_get_phase_none_before_state(self):
        adapter = RemoteGameAdapter(my_seat=0)
        assert adapter.get_phase() is None

    def test_get_phase_returns_current_phase(self):
        adapter = RemoteGameAdapter(my_seat=0)
        adapter.apply_public_state(_make_public_state())
        assert adapter.get_phase() == "SELECTING"

    def test_my_seat_property(self):
        adapter = RemoteGameAdapter(my_seat=3)
        assert adapter.my_seat == 3

    def test_get_committed_scores_empty_before_state(self):
        adapter = RemoteGameAdapter(my_seat=0)
        assert adapter.get_committed_scores() == {}

    def test_get_committed_scores_returns_dict(self):
        adapter = RemoteGameAdapter(my_seat=0)
        state = _make_public_state()
        state.committed_scores = {0: 5, 1: 12}
        adapter.apply_public_state(state)
        scores = adapter.get_committed_scores()
        assert scores[0] == 5
        assert scores[1] == 12

    # ------------------------------------------------------------------
    # Emote path (PR-07)
    # ------------------------------------------------------------------

    def test_pop_pending_emotes_empty_initially(self):
        adapter = RemoteGameAdapter(my_seat=0)
        assert adapter.pop_pending_emotes() == []

    def test_apply_emote_queued_for_pop(self):
        adapter = RemoteGameAdapter(my_seat=0)
        adapter.apply_emote(seat_index=2, emote_id="smile")
        pending = adapter.pop_pending_emotes()
        assert pending == [(2, "smile")]

    def test_pop_pending_emotes_clears_queue(self):
        adapter = RemoteGameAdapter(my_seat=0)
        adapter.apply_emote(1, "fire")
        adapter.pop_pending_emotes()
        # Second pop must return empty
        assert adapter.pop_pending_emotes() == []

    def test_apply_emote_multiple_entries_ordered(self):
        adapter = RemoteGameAdapter(my_seat=0)
        adapter.apply_emote(0, "thumbsup")
        adapter.apply_emote(3, "cry")
        pending = adapter.pop_pending_emotes()
        assert len(pending) == 2
        assert pending[0] == (0, "thumbsup")
        assert pending[1] == (3, "cry")

    def test_apply_emote_independent_of_state(self):
        """Emotes can arrive before or after public/private state is set."""
        adapter = RemoteGameAdapter(my_seat=1)
        adapter.apply_emote(1, "clap")
        # No public or private state yet — should still work
        assert not adapter.has_match_started()
        pending = adapter.pop_pending_emotes()
        assert pending == [(1, "clap")]
