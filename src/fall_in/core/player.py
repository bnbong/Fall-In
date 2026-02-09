"""
Player - Represents a player (human or AI) in the game.
"""

from dataclasses import dataclass, field
from typing import Optional
from enum import Enum, auto

from fall_in.core.card import Card
from fall_in.config import GAME_OVER_SCORE


class PlayerType(Enum):
    """Type of player."""

    HUMAN = auto()
    AI = auto()


@dataclass
class Player:
    """
    Represents a player in the game.

    Manages the player's hand, penalty score, and game state.
    """

    name: str
    player_type: PlayerType
    player_id: int = 0

    # Game state
    hand: list[Card] = field(default_factory=list)
    penalty_score: int = 0
    selected_card: Optional[Card] = None
    is_eliminated: bool = False

    def add_cards(self, cards: list[Card]) -> None:
        """Add cards to player's hand and sort them."""
        self.hand.extend(cards)
        self.hand.sort()

    def remove_card(self, card: Card) -> None:
        """Remove a card from hand."""
        if card in self.hand:
            self.hand.remove(card)

    def select_card(self, card: Card) -> None:
        """Select a card to play this turn."""
        if card not in self.hand:
            raise ValueError(f"Card {card} not in hand")
        self.selected_card = card

    def select_card_by_index(self, index: int) -> Card:
        """Select a card by index in hand."""
        if not 0 <= index < len(self.hand):
            raise ValueError(f"Invalid card index: {index}")
        self.selected_card = self.hand[index]
        return self.selected_card

    def play_selected_card(self) -> Card:
        """Remove and return the selected card."""
        if self.selected_card is None:
            raise ValueError("No card selected")
        card = self.selected_card
        self.remove_card(card)
        self.selected_card = None
        return card

    def add_penalty(self, score: int) -> None:
        """Add penalty points to player."""
        self.penalty_score += score

    def check_elimination(self, threshold: int = GAME_OVER_SCORE) -> bool:
        """
        Check if player is eliminated (score >= threshold).

        Args:
            threshold: Elimination score threshold (default from config).

        Returns:
            True if the player is eliminated.
        """
        if self.penalty_score >= threshold:
            self.is_eliminated = True
        return self.is_eliminated

    def clear_hand(self) -> None:
        """Clear the player's hand."""
        self.hand.clear()
        self.selected_card = None

    def reset_for_new_round(self) -> None:
        """Reset player state for a new round (keep penalty score)."""
        self.hand.clear()
        self.selected_card = None

    def reset_for_new_game(self) -> None:
        """Reset player state for a new game."""
        self.hand.clear()
        self.selected_card = None
        self.penalty_score = 0
        self.is_eliminated = False

    @property
    def hand_size(self) -> int:
        """Number of cards in hand."""
        return len(self.hand)

    @property
    def is_ai(self) -> bool:
        """Check if player is AI."""
        return self.player_type == PlayerType.AI

    def __repr__(self) -> str:
        return (
            f"Player({self.name}, score={self.penalty_score}, cards={self.hand_size})"
        )


def create_players(
    human_name: str = "플레이어",
    ai_count: int = 3,
    ai_names: Optional[list[str]] = None,
) -> list[Player]:
    """
    Create a list of players for the game.

    Args:
        human_name: Name for the human player.
        ai_count: Number of AI players (default 3).
        ai_names: Optional list of AI names.

    Returns:
        List of Player objects (1 human + AI players).
    """
    players = []

    # Human player
    players.append(Player(name=human_name, player_type=PlayerType.HUMAN, player_id=0))

    # AI players
    default_ai_names = ["AI 1", "AI 2", "AI 3"]
    names = ai_names or default_ai_names[:ai_count]

    for i in range(ai_count):
        ai_name = names[i] if i < len(names) else f"AI {i + 1}"
        players.append(Player(name=ai_name, player_type=PlayerType.AI, player_id=i + 1))

    return players
