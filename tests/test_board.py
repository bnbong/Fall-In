"""
Tests for board module
"""
import pytest

from fall_in.core.card import Card
from fall_in.core.board import Board, PlacementResult


class TestBoard:
    """Test Board class"""
    
    def test_initialize_board_with_starter_cards(self):
        """Test board initialization with 4 starter cards"""
        board = Board()
        starters = [
            Card(number=10, danger=3),
            Card(number=30, danger=3),
            Card(number=50, danger=3),
            Card(number=70, danger=3),
        ]
        board.initialize_rows(starters)
        
        # Cards should be sorted and one per row
        assert len(board.rows) == 4
        for row in board.rows:
            assert len(row) == 1
        
        # Verify sorted order
        row_ends = board.get_row_end_numbers()
        assert row_ends == [10, 30, 50, 70]
    
    def test_find_target_row_normal_case(self):
        """Test finding correct row for card placement"""
        board = Board()
        board.initialize_rows([
            Card(10, 3), Card(30, 3), Card(50, 3), Card(70, 3)
        ])
        
        # Card 25 should go to row with 10 (closest lower)
        card = Card(25, 1)
        target = board.find_target_row(card)
        assert target == 0  # Row with 10
        
        # Card 45 should go to row with 30
        card = Card(45, 2)
        target = board.find_target_row(card)
        assert target == 1  # Row with 30
        
        # Card 100 should go to row with 70
        card = Card(100, 3)
        target = board.find_target_row(card)
        assert target == 3  # Row with 70
    
    def test_find_target_row_returns_none_for_smallest(self):
        """Card smaller than all rows returns None"""
        board = Board()
        board.initialize_rows([
            Card(10, 3), Card(30, 3), Card(50, 3), Card(70, 3)
        ])
        
        card = Card(5, 2)
        target = board.find_target_row(card)
        assert target is None
    
    def test_place_card_normal(self):
        """Test normal card placement"""
        board = Board()
        board.initialize_rows([
            Card(10, 3), Card(30, 3), Card(50, 3), Card(70, 3)
        ])
        
        card = Card(25, 1)
        result = board.place_card(card)
        
        assert result.row_index == 0
        assert result.penalty_score == 0
        assert len(result.penalty_cards) == 0
        assert len(board.rows[0]) == 2
    
    def test_place_sixth_card_takes_penalty(self):
        """Placing 6th card takes the 5 existing cards as penalty"""
        board = Board()
        board.initialize_rows([
            Card(10, 3), Card(30, 3), Card(50, 3), Card(70, 3)
        ])
        
        # Add 4 more cards to row 0
        for num in [11, 12, 13, 14]:
            board.place_card(Card(num, 1))
        
        assert len(board.rows[0]) == 5
        
        # 6th card should take penalty
        card = Card(15, 2)
        result = board.place_card(card)
        
        assert result.penalty_score > 0
        assert len(result.penalty_cards) == 5
        assert len(board.rows[0]) == 1  # New row started
        assert board.rows[0][0].number == 15
    
    def test_place_small_card_with_forced_row(self):
        """Placing card smaller than all rows requires forced row selection"""
        board = Board()
        board.initialize_rows([
            Card(10, 3), Card(30, 3), Card(50, 3), Card(70, 3)
        ])
        
        # Card 5 is smaller than all rows
        card = Card(5, 2)
        
        # Without forced_row, should raise
        with pytest.raises(ValueError):
            board.place_card(card)
        
        # With forced_row, takes that row
        result = board.place_card(card, forced_row=0)
        
        assert result.had_to_take_row == True
        assert result.penalty_score == 3  # Original card had danger 3
        assert len(board.rows[0]) == 1
        assert board.rows[0][0].number == 5
    
    def test_get_lowest_penalty_row(self):
        """Test finding row with lowest danger"""
        board = Board()
        board.initialize_rows([
            Card(55, 7),   # Row 0: danger 7
            Card(30, 3),   # Row 1: danger 3
            Card(50, 3),   # Row 2: danger 3
            Card(11, 5),   # Row 3: danger 5
        ])
        
        # Row 1 and 2 have lowest danger (3), should return first one found
        lowest = board.get_lowest_penalty_row()
        assert lowest in [1, 2]


class TestPlacementResult:
    """Test PlacementResult dataclass"""
    
    def test_default_values(self):
        """Test default values for PlacementResult"""
        result = PlacementResult(row_index=0)
        
        assert result.row_index == 0
        assert result.penalty_cards == []
        assert result.penalty_score == 0
        assert result.had_to_take_row == False
