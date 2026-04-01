"""
Regression tests for the current GameRules behavior.

PURPOSE:
  These tests lock in the CURRENT repository implementation so that:
  1. The multiplayer server can replicate identical deterministic results.
  2. Any accidental deviation from the current rules is caught immediately.

Key behaviors locked in here:
  - player_order is the resolution order, NOT ascending card number.
  - Each round, player_order rotates (head moves to tail).
  - A card smaller than all rows auto-takes the lowest-penalty row.
  - No human "row selection" prompt exists in the current code path.
  - The 6th card in a row causes the placer to collect 5 penalty cards.
  - GameRules requires exactly 4 players (NUM_PLAYERS).
  - _check_game_end currently treats players[0] as the human seat.
    This is documented here as a KNOWN ASSUMPTION that PR-04 will
    replace with a seat/controller model.
"""

import random
import pytest

from fall_in.core.card import Card, calculate_danger
from fall_in.core.player import Player, PlayerType, create_players
from fall_in.core.board import Board
from fall_in.core.rules import GameRules, RoundPhase


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_players() -> list[Player]:
    """4 players as the game normally creates them."""
    return create_players()


def _make_rules() -> GameRules:
    return GameRules(_make_players())


def _card(number: int) -> Card:
    return Card(number=number, danger=calculate_danger(number))


# ---------------------------------------------------------------------------
# Initialisation
# ---------------------------------------------------------------------------

class TestGameRulesInit:
    def test_requires_exactly_four_players(self):
        three = create_players(ai_count=2)
        with pytest.raises(ValueError, match="4"):
            GameRules(three)

    def test_requires_exactly_four_players_too_many(self):
        five = [
            Player(name=f"P{i}", player_type=PlayerType.AI, player_id=i)
            for i in range(5)
        ]
        with pytest.raises(ValueError, match="4"):
            GameRules(five)

    def test_player_order_contains_all_players(self):
        rules = _make_rules()
        # Player is not hashable (custom __eq__ without __hash__), use sorted lists
        assert sorted(p.player_id for p in rules.player_order) == sorted(p.player_id for p in rules.players)
        assert len(rules.player_order) == 4

    def test_initial_phase_is_dealing(self):
        rules = _make_rules()
        assert rules.round_state.phase == RoundPhase.DEALING

    def test_game_not_over_at_start(self):
        rules = _make_rules()
        assert rules.game_over is False
        assert rules.winner is None


# ---------------------------------------------------------------------------
# player_order rotation (not ascending number order)
# ---------------------------------------------------------------------------

class TestPlayerOrderRotation:
    def test_first_round_order_is_randomised(self):
        """player_order is randomised; with enough attempts it should differ."""
        original_order = _make_rules().players[:]
        # Run many times to confirm shuffling occurs
        seen_different = False
        for _ in range(50):
            r = _make_rules()
            if r.player_order != original_order:
                seen_different = True
                break
        assert seen_different, "player_order never differed from players list in 50 attempts"

    def test_second_round_rotates_head_to_tail(self):
        rules = _make_rules()
        order_before = rules.player_order.copy()

        rules.start_new_round()  # Round 1 — sets order, no rotation yet
        order_round1 = rules.player_order.copy()

        rules.start_new_round()  # Round 2 — rotate: head → tail
        order_round2 = rules.player_order

        assert order_round2[:-1] == order_round1[1:]   # tail unchanged
        assert order_round2[-1] == order_round1[0]     # old head is now tail

    def test_rotation_cycles_all_four_positions(self):
        rules = _make_rules()
        rules.start_new_round()
        initial_head = rules.player_order[0]

        # After 4 rotations the original head should be back at position 0
        for _ in range(4):
            rules.start_new_round()

        assert rules.player_order[0] == initial_head


# ---------------------------------------------------------------------------
# Resolution order follows player_order, NOT ascending card number
# ---------------------------------------------------------------------------

class TestPlayOrderIsPlayerOrder:
    """
    CRITICAL: The current game resolves cards in player_order sequence.
    This is different from classic 6 Nimmt! which uses ascending card number.
    This test must never be removed or weakened.
    """

    def test_get_cards_in_play_order_follows_player_order(self):
        rules = _make_rules()
        rules.start_new_round()

        # Assign cards so player_order[0] gets a HIGH number
        # and player_order[-1] gets a LOW number.
        # In ascending-number order, the low card would go first.
        # In player_order order, player_order[0] goes first.
        high_card = _card(100)
        low_card = _card(1)

        po = rules.player_order
        po[0].selected_card = high_card
        po[1].selected_card = _card(50)
        po[2].selected_card = _card(30)
        po[3].selected_card = low_card

        play_order = rules.get_cards_in_play_order()

        assert play_order[0] == (po[0], high_card), (
            "First to play must be player_order[0], even if they played the highest card"
        )
        assert play_order[-1] == (po[3], low_card), (
            "Last to play must be player_order[3], even if they played the lowest card"
        )

    def test_play_order_is_not_ascending_card_number(self):
        rules = _make_rules()
        rules.start_new_round()

        # Create a scenario where ascending-number order ≠ player_order
        po = rules.player_order
        # Assign descending card numbers to ascending player_order positions
        po[0].selected_card = _card(80)
        po[1].selected_card = _card(60)
        po[2].selected_card = _card(40)
        po[3].selected_card = _card(20)

        play_order = rules.get_cards_in_play_order()
        card_numbers_in_play_order = [c.number for _, c in play_order]

        # Cards come out in DESCENDING order (player_order sequence),
        # NOT ascending (which would be 20, 40, 60, 80).
        assert card_numbers_in_play_order == [80, 60, 40, 20], (
            "Cards must resolve in player_order sequence, not ascending number order"
        )


# ---------------------------------------------------------------------------
# Forced lowest-penalty row (no player choice for smallest card)
# ---------------------------------------------------------------------------

class TestForcedLowestPenaltyRow:
    """
    When a card is smaller than all row-end cards, the game AUTOMATICALLY
    selects the lowest-penalty row.  There is no player choice prompt.
    This is the current repository behaviour and must be preserved for
    multiplayer rule parity.
    """

    def test_card_smaller_than_all_rows_auto_selects_lowest_penalty(self):
        board = Board()
        # Row dangers: row0=7(card66), row1=5(card11), row2=3(card30), row3=1(card1)
        board.initialize_rows([
            _card(66),   # danger 7
            _card(11),   # danger 5
            _card(30),   # danger 3
            _card(99),   # danger 5
        ])

        tiny = _card(1)
        assert board.is_card_smaller_than_all(tiny)

        lowest = board.get_lowest_penalty_row()
        result = board.place_card(tiny, forced_row=lowest)

        assert result.had_to_take_row is True
        assert result.row_index == lowest

    def test_execute_turn_auto_forces_lowest_row_for_smallest_card(self):
        """
        GameRules.execute_turn / execute_single_placement must call
        get_lowest_penalty_row() automatically — no human interaction.
        """
        rules = _make_rules()
        rules.start_new_round()

        # Set up board with known row ends
        rules.board.rows = [[_card(50)], [_card(60)], [_card(70)], [_card(80)]]

        po = rules.player_order
        # Give player_order[0] a card smaller than all rows
        tiny = _card(1)
        po[0].selected_card = tiny
        po[0].hand = [tiny]

        # Give everyone else a valid card
        for i, p in enumerate(po[1:], start=51):
            c = _card(i)
            p.selected_card = c
            p.hand = [c]

        # execute_single_placement should not raise — it picks the row automatically
        play_order = rules.get_cards_in_play_order()
        first_player, first_card = play_order[0]

        result = rules.execute_single_placement(first_player, first_card, order_idx=1)
        # TurnResult wraps PlacementResult; had_to_take_row lives on result.result
        assert result.result.had_to_take_row is True

    def test_no_row_selection_phase_in_current_rules(self):
        """
        The current rules flow never enters RoundPhase.ROW_SELECTION for
        the forced-row case.  ROW_SELECTION exists in the enum but is not
        triggered by execute_turn / execute_single_placement.
        """
        rules = _make_rules()
        rules.start_new_round()

        # Put a tiny card as the only card for player_order[0]
        rules.board.rows = [[_card(50)], [_card(60)], [_card(70)], [_card(80)]]
        po = rules.player_order
        tiny = _card(1)
        po[0].selected_card = tiny
        po[0].hand = [tiny]
        for i, p in enumerate(po[1:], start=51):
            c = _card(i)
            p.selected_card = c
            p.hand = [c]

        play_order = rules.get_cards_in_play_order()
        # Execute all placements
        for idx, (player, card) in enumerate(play_order):
            rules.execute_single_placement(player, card, order_idx=idx + 1)
        rules.check_round_end()

        # Phase should be SELECTING (more turns left) or ROUND_END — never ROW_SELECTION
        assert rules.round_state.phase != RoundPhase.ROW_SELECTION


# ---------------------------------------------------------------------------
# Sixth card penalty
# ---------------------------------------------------------------------------

class TestSixthCardPenalty:
    def test_placing_sixth_card_takes_five_penalty_cards(self):
        board = Board()
        board.initialize_rows([_card(10), _card(30), _card(50), _card(70)])

        # Fill row 0 to 5 cards
        for num in [11, 12, 13, 14]:
            board.place_card(_card(num))
        assert len(board.rows[0]) == 5

        result = board.place_card(_card(15))
        assert len(result.penalty_cards) == 5
        assert result.penalty_score > 0
        assert len(board.rows[0]) == 1
        assert board.rows[0][0].number == 15

    def test_penalty_score_accumulates_in_round_state(self):
        rules = _make_rules()
        rules.start_new_round()

        # Manually set up a board where the first player will take a penalty
        rules.board.rows = [
            [_card(10), _card(11), _card(12), _card(13), _card(14)],  # 5 cards
            [_card(30)], [_card(50)], [_card(70)],
        ]
        po = rules.player_order
        # player_order[0] plays card 15 → 6th card → takes 5 penalty cards
        c15 = _card(15)
        po[0].selected_card = c15
        po[0].hand = [c15]
        for i, p in enumerate(po[1:], start=31):
            c = _card(i)
            p.selected_card = c
            p.hand = [c]

        results = rules.execute_turn()
        first_result = results[0]

        assert first_result.player is po[0]
        penalty = rules.round_state.round_penalties[po[0].player_id]
        assert penalty.card_count == 5
        assert penalty.total_danger > 0


# ---------------------------------------------------------------------------
# Round flow
# ---------------------------------------------------------------------------

class TestRoundFlow:
    def test_start_new_round_deals_ten_cards_per_player(self):
        rules = _make_rules()
        rules.start_new_round()
        for player in rules.players:
            assert player.hand_size == 10

    def test_start_new_round_initialises_board_with_four_rows(self):
        rules = _make_rules()
        rules.start_new_round()
        assert len(rules.board.rows) == 4
        for row in rules.board.rows:
            assert len(row) == 1

    def test_phase_is_selecting_after_deal(self):
        rules = _make_rules()
        rules.start_new_round()
        assert rules.round_state.phase == RoundPhase.SELECTING

    def test_all_players_selected_false_before_selection(self):
        rules = _make_rules()
        rules.start_new_round()
        assert rules.all_players_selected() is False

    def test_all_players_selected_true_after_all_select(self):
        rules = _make_rules()
        rules.start_new_round()
        for player in rules.players:
            player.selected_card = player.hand[0]
        assert rules.all_players_selected() is True

    def test_execute_turn_raises_if_not_all_selected(self):
        rules = _make_rules()
        rules.start_new_round()
        with pytest.raises(ValueError, match="selected"):
            rules.execute_turn()

    def test_round_ends_after_ten_turns(self):
        rules = _make_rules()
        rules.start_new_round()

        # Play 10 full turns
        for _ in range(10):
            for player in rules.players:
                if not player.is_eliminated and player.hand_size > 0:
                    player.selected_card = player.hand[0]
            if rules.all_players_selected():
                rules.execute_turn()

        assert rules.round_state.phase == RoundPhase.ROUND_END

    def test_commit_round_scores_updates_player_penalty_scores(self):
        rules = _make_rules()
        rules.start_new_round()
        # Force a penalty: put tiny card in everyone's hand
        for player in rules.players:
            player.selected_card = player.hand[0]
        # Artificially add some penalty cards to round state
        target = rules.players[0]
        penalty_card = _card(66)  # danger 7
        rules.round_state.round_penalties[target.player_id].cards_taken.append(penalty_card)

        results = rules.commit_round_scores()
        round_danger, new_total = results[target.player_id]
        assert round_danger == 7
        assert target.penalty_score == 7


# ---------------------------------------------------------------------------
# Known assumption: players[0] == human (documented for future replacement)
# ---------------------------------------------------------------------------

class TestPlayerZeroHumanAssumption:
    """
    Documents the current _check_game_end() assumption that self.players[0]
    is always the human seat.

    This assumption exists at rules.py line 305:
        human_eliminated = self.players[0].is_eliminated

    PR-04 will replace this with seat/controller_type checks.
    This test ensures we notice if the assumption is removed prematurely.
    """

    def test_game_ends_when_players_zero_eliminated(self):
        rules = _make_rules()
        rules.start_new_round()

        # Eliminate player 0 (human seat in single-player)
        rules.players[0].is_eliminated = True
        rules._check_game_end()

        assert rules.game_over is True

    def test_game_does_not_end_when_only_an_ai_is_eliminated(self):
        rules = _make_rules()
        rules.start_new_round()

        # Eliminate an AI player (index 1, 2, or 3)
        rules.players[1].is_eliminated = True
        rules._check_game_end()

        # Game continues — still 3 active players including human
        assert rules.game_over is False

    def test_player_zero_is_human_type_in_create_players(self):
        players = create_players()
        assert players[0].player_type == PlayerType.HUMAN
        for p in players[1:]:
            assert p.player_type == PlayerType.AI


# ---------------------------------------------------------------------------
# Penalty tracking per player_id (not per index)
# ---------------------------------------------------------------------------

class TestPenaltyTracking:
    def test_round_penalties_keyed_by_player_id(self):
        rules = _make_rules()
        rules.start_new_round()
        for player in rules.players:
            assert player.player_id in rules.round_state.round_penalties

    def test_penalty_cards_added_to_correct_player(self):
        rules = _make_rules()
        rules.start_new_round()

        target = rules.player_order[0]
        rules.round_state.round_penalties[target.player_id].cards_taken.append(_card(66))

        assert rules.round_state.round_penalties[target.player_id].total_danger == 7
        for p in rules.players:
            if p is not target:
                assert rules.round_state.round_penalties[p.player_id].total_danger == 0

    def test_get_player_round_danger_matches_penalty_total(self):
        rules = _make_rules()
        rules.start_new_round()

        target = rules.players[0]
        rules.round_state.round_penalties[target.player_id].cards_taken.extend(
            [_card(11), _card(22)]  # danger 5 + 5 = 10
        )
        assert rules.get_player_round_danger(target) == 10

    def test_rankings_sorted_by_penalty_score_low_first(self):
        rules = _make_rules()
        rules.players[0].penalty_score = 30
        rules.players[1].penalty_score = 5
        rules.players[2].penalty_score = 20
        rules.players[3].penalty_score = 15

        rankings = rules.get_rankings()
        scores = [p.penalty_score for p in rankings]
        assert scores == sorted(scores)
