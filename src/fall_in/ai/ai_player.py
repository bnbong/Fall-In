"""
AI Player - Artificial intelligence for card selection
"""
import random
from typing import Optional

from fall_in.core.card import Card
from fall_in.core.board import Board
from fall_in.core.player import Player, PlayerType
from fall_in.config import Difficulty


class AIPlayer:
    """
    AI logic for card selection based on difficulty level.
    
    Strategies:
    - EASY: Random card selection
    - NORMAL: Basic heuristics (avoid placing 6th card, prefer lower danger)
    - HARD: Advanced analysis of board state and opponent hands
    """
    
    def __init__(self, player: Player, difficulty: str = Difficulty.NORMAL):
        if player.player_type != PlayerType.AI:
            raise ValueError("AIPlayer can only control AI players")
        
        self.player = player
        self.difficulty = difficulty
    
    def select_card(self, board: Board) -> Card:
        """
        Select a card to play based on difficulty and board state.
        
        Args:
            board: Current game board state
            
        Returns:
            Selected Card from player's hand
        """
        if not self.player.hand:
            raise ValueError("No cards in hand")
        
        if self.difficulty == Difficulty.EASY:
            return self._select_random()
        elif self.difficulty == Difficulty.NORMAL:
            return self._select_normal(board)
        else:  # HARD
            return self._select_hard(board)
    
    def _select_random(self) -> Card:
        """EASY: Random card selection"""
        card = random.choice(self.player.hand)
        self.player.select_card(card)
        return card
    
    def _select_normal(self, board: Board) -> Card:
        """
        NORMAL: Basic heuristics
        - Prefer cards that won't trigger 6th card penalty
        - Avoid cards smaller than all row ends
        - Prefer cards with lower danger when taking penalties
        """
        row_ends = board.get_row_end_numbers()
        row_sizes = [len(row) for row in board.rows]
        
        best_card: Optional[Card] = None
        best_score = float('inf')
        
        for card in self.player.hand:
            score = self._evaluate_card(card, row_ends, row_sizes, board)
            if score < best_score:
                best_score = score
                best_card = card
        
        if best_card is None:
            best_card = random.choice(self.player.hand)
        
        self.player.select_card(best_card)
        return best_card
    
    def _evaluate_card(
        self, 
        card: Card, 
        row_ends: list[int], 
        row_sizes: list[int],
        board: Board
    ) -> float:
        """
        Evaluate a card's desirability (lower is better).
        
        Factors:
        - Being smaller than all rows is very bad (100 points)
        - Placing 6th card into a row (row penalty)
        - Normal placement is neutral (danger value)
        """
        # Check if card is smaller than all row ends
        target_row = board.find_target_row(card)
        
        if target_row is None:
            # Must take a row - very bad
            # Score based on lowest row penalty we'd take
            lowest_penalty = min(board.get_row_danger(i) for i in range(4))
            return 100 + lowest_penalty
        
        # Check if this would be 6th card
        if row_sizes[target_row] >= 5:
            # Would trigger penalty
            penalty = board.get_row_danger(target_row)
            return 50 + penalty
        
        # Check how close to row end
        # Prefer cards that leave room for more cards
        diff = card.number - row_ends[target_row]
        
        # Lower danger cards are slightly preferred
        return card.danger + (diff / 100)
    
    def _select_hard(self, board: Board) -> Card:
        """
        HARD: Advanced analysis
        - Consider opponent hand ranges
        - Calculate probability of being overtaken
        - Strategic timing of high/low cards
        """
        # For now, use enhanced normal logic
        # TODO: Implement opponent modeling
        
        row_ends = board.get_row_end_numbers()
        row_sizes = [len(row) for row in board.rows]
        
        candidates: list[tuple[Card, float]] = []
        
        for card in self.player.hand:
            score = self._evaluate_card_advanced(card, row_ends, row_sizes, board)
            candidates.append((card, score))
        
        # Sort by score (lower is better)
        candidates.sort(key=lambda x: x[1])
        
        # Sometimes add randomness to be less predictable
        if len(candidates) >= 3 and random.random() < 0.2:
            # 20% chance to pick from top 3 instead of best
            selected = random.choice(candidates[:3])
        else:
            selected = candidates[0]
        
        self.player.select_card(selected[0])
        return selected[0]
    
    def _evaluate_card_advanced(
        self, 
        card: Card, 
        row_ends: list[int], 
        row_sizes: list[int],
        board: Board
    ) -> float:
        """
        Advanced card evaluation for HARD difficulty.
        """
        base_score = self._evaluate_card(card, row_ends, row_sizes, board)
        
        # Additional factors for hard mode
        
        # Prefer saving high cards for later when rows are shorter
        avg_row_size = sum(row_sizes) / 4
        if avg_row_size < 3:
            # Early game - prefer playing low/medium cards
            if card.number < 50:
                base_score -= 5
        else:
            # Late game - high cards are safer
            if card.number > 70:
                base_score -= 3
        
        # Avoid cards that leave us vulnerable
        target_row = board.find_target_row(card)
        if target_row is not None:
            # Check how many cards could overtake us
            gap_above = 104 - card.number
            if gap_above < 20:
                # High card, less likely to be overtaken
                base_score -= 2
        
        return base_score
    
    def choose_row_to_take(self, board: Board) -> int:
        """
        Choose which row to take when card is smaller than all rows.
        
        Returns:
            Index of row to take (0-3)
        """
        # Always take the row with lowest penalty
        min_penalty = float('inf')
        best_row = 0
        
        for i in range(4):
            penalty = board.get_row_danger(i)
            if penalty < min_penalty:
                min_penalty = penalty
                best_row = i
        
        return best_row


def create_ai_players(
    players: list[Player], 
    difficulty: str = Difficulty.NORMAL
) -> list[AIPlayer]:
    """
    Create AI controllers for all AI players.
    
    Args:
        players: List of all players
        difficulty: AI difficulty level
        
    Returns:
        List of AIPlayer controllers for AI players
    """
    ai_controllers = []
    
    for player in players:
        if player.player_type == PlayerType.AI:
            ai_controllers.append(AIPlayer(player, difficulty))
    
    return ai_controllers
