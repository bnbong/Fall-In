"""
Rules - Game rules and round management for 6 Nimmt!
"""

import random
from dataclasses import dataclass, field
from typing import Optional
from enum import Enum, auto

from fall_in.core.card import Card, create_shuffled_deck
from fall_in.core.board import Board, PlacementResult
from fall_in.core.player import Player
from fall_in.config import NUM_PLAYERS, CARDS_PER_PLAYER, NUM_ROWS, GAME_OVER_SCORE


class RoundPhase(Enum):
    """Current phase of a round"""

    DEALING = auto()  # Dealing cards to players
    SELECTING = auto()  # Players selecting cards
    REVEALING = auto()  # Cards being revealed
    PLACING = auto()  # Cards being placed on board
    ROW_SELECTION = auto()  # Player must choose row (card smaller than all)
    ROUND_END = auto()  # Round ended
    GAME_END = auto()  # Game ended


@dataclass
class TurnResult:
    """Result of a single card placement"""

    player: Player
    card: Card
    result: PlacementResult
    placement_order: int = 0  # 1-based order of placement this turn


@dataclass
class RoundPenalty:
    """Tracks penalty cards taken during a round"""

    player: Player
    cards_taken: list[Card] = field(default_factory=list)

    @property
    def card_count(self) -> int:
        return len(self.cards_taken)

    @property
    def total_danger(self) -> int:
        return sum(c.danger for c in self.cards_taken)


@dataclass
class RoundState:
    """State of the current round"""

    round_number: int
    phase: RoundPhase
    turn_results: list[TurnResult] = field(default_factory=list)
    pending_row_selection: Optional[tuple[Player, Card]] = None
    round_penalties: dict[int, RoundPenalty] = field(default_factory=dict)


class GameRules:
    """
    Manages game rules and flow following 6 Nimmt! mechanics.

    Game Flow:
    1. Deal 10 cards to each player
    2. Place 4 cards on board as row starters
    3. Each turn:
       - All players simultaneously select a card
       - Cards are revealed and placed in ascending order
       - If 6th card placed or card smaller than all rows, take penalty
    4. After 10 turns, round ends
    5. On ResultScene: calculate penalties, check for 66+ points (탈락)
    """

    def __init__(self, players: list[Player]):
        if len(players) != NUM_PLAYERS:
            raise ValueError(f"Need exactly {NUM_PLAYERS} players")

        self.players = players
        self.board = Board()
        self.deck: list[Card] = []

        # Player order (randomized at game start)
        self.player_order: list[Player] = []
        self._randomize_player_order()

        self.round_state = RoundState(round_number=0, phase=RoundPhase.DEALING)

        # Track committed scores (applied in ResultScene)
        self.committed_scores: dict[int, int] = {p.player_id: 0 for p in players}

        self.game_over = False
        self.winner: Optional[Player] = None

    def _randomize_player_order(self) -> None:
        """Randomize player order at game start"""
        self.player_order = self.players.copy()
        random.shuffle(self.player_order)

    def _rotate_player_order(self) -> None:
        """Rotate player order - first player moves to end"""
        if len(self.player_order) > 1:
            self.player_order = self.player_order[1:] + [self.player_order[0]]

    def get_player_order_position(self, player: Player) -> int:
        """Get 1-based position of player in order"""
        if player in self.player_order:
            return self.player_order.index(player) + 1
        return 0

    def start_new_round(self) -> None:
        """Start a new round"""
        # Rotate player order (except for first round)
        if self.round_state.round_number > 0:
            self._rotate_player_order()

        self.round_state.round_number += 1
        self.round_state.phase = RoundPhase.DEALING
        self.round_state.turn_results.clear()
        self.round_state.pending_row_selection = None
        self.round_state.round_penalties = {
            p.player_id: RoundPenalty(player=p) for p in self.players
        }

        # Reset player hands
        for player in self.players:
            player.reset_for_new_round()

        # Create and shuffle deck
        self.deck = create_shuffled_deck()

        # Deal cards to players
        for player in self.players:
            cards = [self.deck.pop() for _ in range(CARDS_PER_PLAYER)]
            player.add_cards(cards)

        # Setup board with 4 starter cards
        starter_cards = [self.deck.pop() for _ in range(NUM_ROWS)]
        self.board.initialize_rows(starter_cards)

        self.round_state.phase = RoundPhase.SELECTING

    def all_players_selected(self) -> bool:
        """Check if all players have selected a card"""
        return all(
            p.selected_card is not None for p in self.players if not p.is_eliminated
        )

    def get_cards_in_play_order(self) -> list[tuple[Player, Card]]:
        """
        Get selected cards in player order (fixed order for the round).

        Returns:
            List of (player, card) tuples in player_order sequence
        """
        selections = []
        # Use fixed player_order (determined at round start)
        for player in self.player_order:
            if not player.is_eliminated and player.selected_card:
                selections.append((player, player.selected_card))

        return selections

    def execute_turn(self) -> list[TurnResult]:
        """
        Execute a full turn - all players place their selected cards.

        Returns:
            List of TurnResults for each placement
        """
        if not self.all_players_selected():
            raise ValueError("Not all players have selected cards")

        self.round_state.phase = RoundPhase.PLACING
        turn_results = []

        # Get cards in play order
        play_order = self.get_cards_in_play_order()

        for order_idx, (player, card) in enumerate(play_order):
            if player.is_eliminated:
                continue

            # Remove card from hand
            player.selected_card = None
            player.remove_card(card)

            # Check if requires row selection
            if self.board.is_card_smaller_than_all(card):
                # Automatically choose lowest penalty row
                forced_row = self.board.get_lowest_penalty_row()
                result = self.board.place_card(card, forced_row)
            else:
                result = self.board.place_card(card, None)

            if result.penalty_score > 0:
                self.round_state.round_penalties[player.player_id].cards_taken.extend(
                    result.penalty_cards
                )

            turn_result = TurnResult(
                player=player, card=card, result=result, placement_order=order_idx + 1
            )
            turn_results.append(turn_result)
            self.round_state.turn_results.append(turn_result)

        # Check for round end (all hands empty)
        if all(p.hand_size == 0 for p in self.players if not p.is_eliminated):
            self.round_state.phase = RoundPhase.ROUND_END
        else:
            self.round_state.phase = RoundPhase.SELECTING

        return turn_results

    def prepare_turn(self) -> list[tuple[Player, Card]]:
        """
        Prepare a turn - returns the play order without executing.
        Used for sequential display of placements.

        Returns:
            List of (player, card) tuples in play order
        """
        if not self.all_players_selected():
            raise ValueError("Not all players have selected cards")

        self.round_state.phase = RoundPhase.PLACING
        return self.get_cards_in_play_order()

    def execute_single_placement(
        self, player: Player, card: Card, order_idx: int
    ) -> TurnResult:
        """
        Execute a single card placement and update the board.

        Args:
            player: Player placing the card
            card: Card to place
            order_idx: Placement order (1-based)

        Returns:
            TurnResult for this placement
        """
        # Remove card from hand
        player.selected_card = None
        player.remove_card(card)

        # Check if requires row selection
        if self.board.is_card_smaller_than_all(card):
            # Automatically choose lowest penalty row
            forced_row = self.board.get_lowest_penalty_row()
            result = self.board.place_card(card, forced_row)
        else:
            result = self.board.place_card(card, None)

        if result.penalty_score > 0:
            self.round_state.round_penalties[player.player_id].cards_taken.extend(
                result.penalty_cards
            )

        turn_result = TurnResult(
            player=player, card=card, result=result, placement_order=order_idx
        )
        self.round_state.turn_results.append(turn_result)

        return turn_result

    def check_round_end(self) -> None:
        """Check and update phase if round has ended"""
        if all(p.hand_size == 0 for p in self.players if not p.is_eliminated):
            self.round_state.phase = RoundPhase.ROUND_END
        else:
            self.round_state.phase = RoundPhase.SELECTING

    def get_round_penalties(self) -> dict[int, RoundPenalty]:
        """Get all penalty info for current round"""
        return self.round_state.round_penalties

    def get_player_round_penalty_count(self, player: Player) -> int:
        """Get number of penalty cards taken this round"""
        return self.round_state.round_penalties[player.player_id].card_count

    def get_player_round_danger(self, player: Player) -> int:
        """Get total danger from penalty cards this round"""
        return self.round_state.round_penalties[player.player_id].total_danger

    def get_player_committed_score(self, player: Player) -> int:
        """Get committed score before this round"""
        return self.committed_scores[player.player_id]

    def commit_round_scores(self) -> dict[int, tuple[int, int]]:
        """
        Commit round penalties to player scores.
        Called from ResultScene after showing round results.

        Returns:
            Dict of player_id -> (round_danger, new_total)
        """
        results = {}

        for player in self.players:
            round_danger = self.get_player_round_danger(player)
            new_total = self.committed_scores[player.player_id] + round_danger
            self.committed_scores[player.player_id] = new_total
            player.penalty_score = new_total
            results[player.player_id] = (round_danger, new_total)

            # Check for elimination
            if player.check_elimination(GAME_OVER_SCORE):
                pass  # Will be handled in check_game_end

        self._check_game_end()
        return results

    def _check_game_end(self) -> None:
        """Check if game should end"""
        active_players = [p for p in self.players if not p.is_eliminated]

        # Game ends if human player is eliminated OR only 1 player left
        human_eliminated = self.players[0].is_eliminated  # Player 0 is always human

        if len(active_players) <= 1 or human_eliminated:
            self.game_over = True
            self.round_state.phase = RoundPhase.GAME_END

            if human_eliminated:
                # Human lost - AI with lowest score wins
                ai_players = [p for p in self.players[1:] if not p.is_eliminated]
                if ai_players:
                    self.winner = min(ai_players, key=lambda p: p.penalty_score)
                else:
                    self.winner = min(self.players, key=lambda p: p.penalty_score)
            elif active_players:
                self.winner = active_players[0]
            else:
                # All eliminated - winner is the one with lowest score
                self.winner = min(self.players, key=lambda p: p.penalty_score)

    def is_round_over(self) -> bool:
        """Check if current round is over"""
        return self.round_state.phase in (RoundPhase.ROUND_END, RoundPhase.GAME_END)

    def get_active_players(self) -> list[Player]:
        """Get list of non-eliminated players"""
        return [p for p in self.players if not p.is_eliminated]

    def get_rankings(self) -> list[Player]:
        """Get players ranked by penalty score (low to high)"""
        return sorted(self.players, key=lambda p: p.penalty_score)

    def get_danger_level(self, player: Player) -> str:
        """
        Get danger level description for a player's score.

        Returns:
            Korean danger level name
        """
        score = self.committed_scores[player.player_id]

        if score < 20:
            return "안전"
        elif score < 35:
            return "주의"
        elif score < 50:
            return "경고"
        elif score < 60:
            return "위험"
        elif score < 66:
            return "극한"
        else:
            return "탈락"
