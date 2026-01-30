"""
Board - Manages the 4-row game board
"""
from dataclasses import dataclass, field
from typing import Optional

from fall_in.core.card import Card
from fall_in.config import NUM_ROWS, MAX_CARDS_PER_ROW


@dataclass
class PlacementResult:
    """Result of placing a card on the board"""
    row_index: int
    penalty_cards: list[Card] = field(default_factory=list)
    penalty_score: int = 0
    had_to_take_row: bool = False


class Board:
    """
    Manages the 4-row game board following 6 Nimmt! rules.
    
    Rules:
    - Board has 4 rows
    - Each row starts with 1 card (dealt at game start)
    - Cards are placed in ascending order to the row with closest lower card
    - If a card is smaller than all row-end cards, player must take a row
    - When 6th card is placed, player takes the 5 cards and starts new row
    """
    
    def __init__(self):
        self.rows: list[list[Card]] = [[] for _ in range(NUM_ROWS)]
    
    def initialize_rows(self, starter_cards: list[Card]) -> None:
        """
        Initialize board with 4 starter cards, one per row.
        
        Args:
            starter_cards: List of exactly 4 cards to start the rows
        """
        if len(starter_cards) != NUM_ROWS:
            raise ValueError(f"Need exactly {NUM_ROWS} starter cards")
        
        # Sort starter cards and place one in each row
        sorted_cards = sorted(starter_cards)
        for i, card in enumerate(sorted_cards):
            self.rows[i] = [card]
    
    def get_row_end_cards(self) -> list[Card]:
        """
        Get the last card of each row.
        
        Returns:
            List of 4 cards (end card of each row)
        """
        return [row[-1] for row in self.rows if row]
    
    def get_row_end_numbers(self) -> list[int]:
        """
        Get the number of the last card in each row.
        
        Returns:
            List of 4 integers
        """
        return [row[-1].number for row in self.rows if row]
    
    def find_target_row(self, card: Card) -> Optional[int]:
        """
        Find which row a card should be placed in.
        
        Rule: Card goes to the row whose end card is the largest
        number that is still smaller than the played card.
        
        Args:
            card: Card to place
            
        Returns:
            Row index (0-3) or None if card is smaller than all row ends
        """
        best_row = None
        best_diff = float('inf')
        
        for i, row in enumerate(self.rows):
            if not row:
                continue
            
            end_number = row[-1].number
            
            # Card must be larger than row end
            if card.number > end_number:
                diff = card.number - end_number
                if diff < best_diff:
                    best_diff = diff
                    best_row = i
        
        return best_row
    
    def _take_row(self, row_index: int) -> list[Card]:
        """
        Take all cards from a row and clear it.
        
        Args:
            row_index: Index of row to take
            
        Returns:
            List of taken cards
        """
        taken = self.rows[row_index].copy()
        self.rows[row_index] = []
        return taken
    
    def place_card(self, card: Card, forced_row: Optional[int] = None) -> PlacementResult:
        """
        Place a card on the board following 6 Nimmt! rules.
        
        Args:
            card: Card to place
            forced_row: If card is smaller than all rows, player chooses row to take
            
        Returns:
            PlacementResult with row index, any penalty cards, and score
        """
        result = PlacementResult(row_index=-1)
        
        # Find target row
        target_row = self.find_target_row(card)
        
        if target_row is None:
            # Card is smaller than all row ends - must take a row
            if forced_row is None:
                raise ValueError("Card smaller than all rows - must specify forced_row")
            
            # Take the chosen row
            penalty_cards = self._take_row(forced_row)
            penalty_score = sum(c.danger for c in penalty_cards)
            
            # Place our card as new row starter
            self.rows[forced_row] = [card]
            
            result.row_index = forced_row
            result.penalty_cards = penalty_cards
            result.penalty_score = penalty_score
            result.had_to_take_row = True
            
        else:
            # Normal placement
            row = self.rows[target_row]
            
            if len(row) >= MAX_CARDS_PER_ROW:
                # 6th card - take the 5 cards as penalty
                penalty_cards = self._take_row(target_row)
                penalty_score = sum(c.danger for c in penalty_cards)
                
                # Place our card as new row starter
                self.rows[target_row] = [card]
                
                result.row_index = target_row
                result.penalty_cards = penalty_cards
                result.penalty_score = penalty_score
            else:
                # Normal add to row
                row.append(card)
                result.row_index = target_row
        
        return result
    
    def get_lowest_penalty_row(self) -> int:
        """
        Get the row with lowest total danger (for AI decision).
        
        Returns:
            Index of row with lowest penalty
        """
        min_penalty = float('inf')
        best_row = 0
        
        for i, row in enumerate(self.rows):
            penalty = sum(c.danger for c in row)
            if penalty < min_penalty:
                min_penalty = penalty
                best_row = i
        
        return best_row
    
    def get_row_danger(self, row_index: int) -> int:
        """
        Get total danger of a specific row.
        
        Args:
            row_index: Index of row
            
        Returns:
            Sum of danger values in the row
        """
        return sum(c.danger for c in self.rows[row_index])
    
    def is_card_smaller_than_all(self, card: Card) -> bool:
        """
        Check if a card is smaller than all row-end cards.
        
        Args:
            card: Card to check
            
        Returns:
            True if player must choose a row to take
        """
        return self.find_target_row(card) is None
    
    def clear(self) -> None:
        """Clear the board"""
        self.rows = [[] for _ in range(NUM_ROWS)]
    
    def __repr__(self) -> str:
        lines = []
        for i, row in enumerate(self.rows):
            cards_str = ", ".join(str(c.number) for c in row)
            danger = sum(c.danger for c in row)
            lines.append(f"Row {i+1}: [{cards_str}] (danger: {danger})")
        return "\n".join(lines)
