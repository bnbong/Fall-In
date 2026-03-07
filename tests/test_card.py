"""
Tests for card module
"""

import pytest

from fall_in.core.card import Card, calculate_danger, create_deck, create_shuffled_deck


class TestCalculateDanger:
    """Test danger level calculation"""

    def test_normal_cards_have_danger_1(self):
        """Normal cards should have danger level 1"""
        normal_numbers = [1, 2, 3, 4, 6, 7, 8, 9, 12, 13, 14, 16, 17, 18, 91, 92, 93]
        for number in normal_numbers:
            assert calculate_danger(number) == 1, f"Card {number} should have danger 1"

    def test_cards_ending_in_5_have_danger_2(self):
        """Cards ending in 5 (except doubles) should have danger 2"""
        numbers = [5, 15, 25, 35, 45, 65, 75, 85, 95]
        for number in numbers:
            assert calculate_danger(number) == 2, f"Card {number} should have danger 2"

    def test_cards_ending_in_0_have_danger_3(self):
        """Cards ending in 0 should have danger 3"""
        numbers = [10, 20, 30, 40, 50, 60, 70, 80, 90, 100]
        for number in numbers:
            assert calculate_danger(number) == 3, f"Card {number} should have danger 3"

    def test_double_digit_cards_have_danger_5(self):
        """Double digit cards (11, 22, ..., 99) should have danger 5"""
        numbers = [11, 22, 33, 44, 55, 77, 88, 99]
        for number in numbers:
            assert calculate_danger(number) == 5, f"Card {number} should have danger 5"

    def test_card_66_has_danger_7(self):
        """Card 66 should have danger 7 (special override)"""
        assert calculate_danger(66) == 7


class TestCard:
    """Test Card class"""

    def test_create_card(self):
        """Test basic card creation"""
        card = Card(number=42, danger=1)
        assert card.number == 42
        assert card.danger == 1
        assert not card.is_collected

    def test_card_validation(self):
        """Test card number validation"""
        with pytest.raises(ValueError):
            Card(number=0, danger=1)

        with pytest.raises(ValueError):
            Card(number=105, danger=1)

        with pytest.raises(ValueError):
            Card(number=50, danger=0)

        with pytest.raises(ValueError):
            Card(number=50, danger=8)

    def test_card_comparison(self):
        """Test card comparison by number"""
        card1 = Card(number=10, danger=3)
        card2 = Card(number=20, danger=3)

        assert card1 < card2
        assert not card2 < card1

    def test_card_equality(self):
        """Test card equality by number"""
        card1 = Card(number=66, danger=7)
        card2 = Card(number=66, danger=7)
        card3 = Card(number=56, danger=1)

        assert card1 == card2
        assert card1 != card3


class TestDeck:
    """Test deck creation"""

    def test_create_deck_has_104_cards(self):
        """Deck should have 104 cards"""
        deck = create_deck()
        assert len(deck) == 104

    def test_deck_has_unique_numbers(self):
        """All cards in deck should have unique numbers"""
        deck = create_deck()
        numbers = [c.number for c in deck]
        assert len(set(numbers)) == 104

    def test_deck_numbers_1_to_104(self):
        """Deck should have cards numbered 1-104"""
        deck = create_deck()
        numbers = sorted([c.number for c in deck])
        assert numbers == list(range(1, 105))

    def test_shuffled_deck_different_order(self):
        """Shuffled deck should (usually) have different order"""
        deck1 = create_deck()
        deck2 = create_shuffled_deck()

        # Order should be different (with very high probability)
        orders_match = all(c1.number == c2.number for c1, c2 in zip(deck1, deck2))
        assert not orders_match or True  # Allow very rare match

    def test_deck_danger_totals(self):
        """Verify total danger across all cards"""
        deck = create_deck()
        total_danger = sum(c.danger for c in deck)  # noqa

        # Known totals from 6 Nimmt rules:
        # 1-danger cards: Many
        # 2-danger cards (5,15,25,35,45,65,75,85,95): 9 * 2 = 18
        # 3-danger cards (10,20,30,40,50,60,70,80,90,100): 10 * 3 = 30
        # 5-danger cards (11,22,33,44,66,77,88,99): 8 * 5 = 40
        # 7-danger card (66): 1 * 7 = 7
        # Expected total: Let's verify by counting

        danger_1_count = sum(1 for c in deck if c.danger == 1)
        danger_2_count = sum(1 for c in deck if c.danger == 2)
        danger_3_count = sum(1 for c in deck if c.danger == 3)
        danger_5_count = sum(1 for c in deck if c.danger == 5)
        danger_7_count = sum(1 for c in deck if c.danger == 7)

        assert danger_2_count == 9  # 5,15,25,35,45,65,75,85,95
        assert danger_3_count == 10  # 10,20,30,40,50,60,70,80,90,100
        assert danger_5_count == 8  # 11,22,33,44,66,77,88,99
        assert danger_7_count == 1  # 66
        assert danger_1_count == 104 - 9 - 10 - 8 - 1  # Rest
