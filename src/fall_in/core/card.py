"""
Card - Represents a soldier card in the game
"""
from dataclasses import dataclass
from typing import Optional


@dataclass
class Card:
    """
    Represents a soldier card (병사 카드).
    
    Based on 6 Nimmt! rules:
    - Cards numbered 1-104
    - Each card has a danger level (위험도) from 1-7
    - Danger rules:
        - Normal cards: 1 danger
        - Cards ending in 5: 2 danger
        - Cards ending in 0: 3 danger
        - Double digit cards (11,22,33...): 5 danger  
        - Card 55: 7 danger (ends in 5 AND double digit)
    """
    number: int
    danger: int
    
    # Soldier data (for collected/interviewed soldiers)
    is_collected: bool = False
    name: Optional[str] = None
    unit: Optional[str] = None  # 소속 대대
    note: Optional[str] = None  # 특이 사항
    
    def __post_init__(self):
        """Validate card data"""
        if not 1 <= self.number <= 104:
            raise ValueError(f"Card number must be 1-104, got {self.number}")
        if not 1 <= self.danger <= 7:
            raise ValueError(f"Danger must be 1-7, got {self.danger}")
    
    def __lt__(self, other: 'Card') -> bool:
        """Cards are compared by number for sorting"""
        return self.number < other.number
    
    def __eq__(self, other: object) -> bool:
        """Cards are equal if they have the same number"""
        if not isinstance(other, Card):
            return NotImplemented
        return self.number == other.number
    
    def __hash__(self) -> int:
        return hash(self.number)
    
    def __repr__(self) -> str:
        return f"Card({self.number}, danger={self.danger})"


def calculate_danger(number: int) -> int:
    """
    Calculate the danger level for a card number based on 6 Nimmt! rules.
    
    Rules:
    - Normal cards: 1 danger (소 머리 1개)
    - Cards ending in 5: 2 danger (소 머리 2개)
    - Cards ending in 0: 3 danger (소 머리 3개)
    - Double digit cards (11,22,33,...,99): 5 danger (소 머리 5개)
    - Card 55: 7 danger (ends in 5 AND double digit = 2+5)
    
    Args:
        number: Card number (1-104)
        
    Returns:
        Danger level (1-7)
    """
    danger = 1
    
    # Check for double digit (11, 22, 33, ..., 99)
    is_double = (10 <= number <= 99) and (number % 11 == 0)
    
    # Check ending digit
    ends_in_5 = (number % 10 == 5)
    ends_in_0 = (number % 10 == 0) and (number > 0)
    
    if is_double and ends_in_5:  # Special case: 55
        danger = 7
    elif is_double:
        danger = 5
    elif ends_in_0:
        danger = 3
    elif ends_in_5:
        danger = 2
    
    return danger


def create_deck() -> list[Card]:
    """
    Create a standard deck of 104 cards with proper danger levels.
    
    Returns:
        List of 104 Card objects
    """
    deck = []
    for number in range(1, 105):
        danger = calculate_danger(number)
        deck.append(Card(number=number, danger=danger))
    return deck


def create_shuffled_deck() -> list[Card]:
    """
    Create a shuffled deck of 104 cards.
    
    Returns:
        Shuffled list of 104 Card objects
    """
    import random
    deck = create_deck()
    random.shuffle(deck)
    return deck
