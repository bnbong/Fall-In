"""
LocalGameAdapter — wraps GameRules for the single-player path.

Provides the same query interface as RemoteGameAdapter so that rendering
code can be written against one interface regardless of whether a match
is local or remote.

Design notes:
  - seat_index 0 is always the local human player.
  - Seats 1-3 are AI-controlled bots.
  - player_id == seat_index (same convention as the server MatchService).
  - board_row_owners mirrors the server's tracking: -1 for starter cards,
    seat_index for any subsequently placed card.
  - get_public_state() / get_private_state() never include private cosmetic
    fields from Card; only MatchCardPublic (number / danger / owner_seat) is
    returned.
"""

from __future__ import annotations

from typing import Optional

from fall_in.ai.ai_player import AIPlayer
from fall_in.core.rules import GameRules, RoundPhase
from fall_in.multiplayer.models import (
    ControllerType,
    MatchCardPublic,
    PrivatePlayerState,
    PublicMatchState,
    SeatIdentity,
)


class LocalGameAdapter:
    """
    Adapter for single-player (or offline) mode.

    Usage::

        rules = GameRules(create_players())
        ais   = create_ai_players(rules.players)
        adapter = LocalGameAdapter(rules, ais)

        adapter.start_round()
        adapter.select_card_for_human(42)       # human picks card 42
        if adapter.all_selected():
            for seat, card in adapter.resolve_turn():
                ...                             # render each placement
        if adapter.is_round_over():
            scores = adapter.commit_round()
        if adapter.is_game_over():
            ...
    """

    def __init__(
        self,
        rules: GameRules,
        ai_controllers: list[AIPlayer],
        match_id: str = "local",
    ) -> None:
        self._rules = rules
        self._ai: dict[int, AIPlayer] = {
            ai.player.player_id: ai for ai in ai_controllers
        }
        self._match_id = match_id
        # player_id == seat_index throughout single-player.
        self._player_to_seat: dict[int, int] = {
            p.player_id: p.player_id for p in rules.players
        }
        # Board row ownership parallel to rules.board.rows.
        # -1 = starter card (no owner).
        self._board_row_owners: list[list[int]] = [[], [], [], []]

    # ------------------------------------------------------------------
    # Round management
    # ------------------------------------------------------------------

    def start_round(self) -> None:
        """Deal cards for a new round and auto-select for bot seats."""
        self._rules.start_new_round()
        self._board_row_owners = [[-1] for _ in range(4)]
        for player_id, ai in self._ai.items():
            player = next(p for p in self._rules.players if p.player_id == player_id)
            if not player.is_eliminated:
                ai.select_card(self._rules.board)

    # ------------------------------------------------------------------
    # Card selection
    # ------------------------------------------------------------------

    def select_card_for_human(self, card_number: int) -> None:
        """Local human (seat 0) selects a card by number."""
        human = self._rules.players[0]
        target = next((c for c in human.hand if c.number == card_number), None)
        if target is None:
            raise ValueError(f"Card {card_number} is not in the human player's hand")
        human.select_card(target)

    def all_selected(self) -> bool:
        """True when every non-eliminated player has selected a card."""
        return self._rules.all_players_selected()

    # ------------------------------------------------------------------
    # Turn resolution
    # ------------------------------------------------------------------

    def resolve_turn(self) -> list[tuple[int, MatchCardPublic]]:
        """
        Execute the full turn step by step.

        Returns a list of (seat_index, MatchCardPublic) pairs in placement
        order.  The caller should iterate and render each entry sequentially.

        Updates board_row_owners after each placement.
        """
        play_order = self._rules.prepare_turn()
        results: list[tuple[int, MatchCardPublic]] = []

        for order_idx, (player, card) in enumerate(play_order):
            turn_result = self._rules.execute_single_placement(player, card, order_idx + 1)
            placement = turn_result.result  # fall_in.core.board.PlacementResult
            seat_idx = self._player_to_seat[player.player_id]

            if placement.had_to_take_row or placement.penalty_score > 0:
                self._board_row_owners[placement.row_index] = [seat_idx]
            else:
                self._board_row_owners[placement.row_index].append(seat_idx)

            pub_card = MatchCardPublic(
                number=card.number,
                danger=card.danger,
                owner_seat=seat_idx,
            )
            results.append((seat_idx, pub_card))

        self._rules.check_round_end()
        return results

    # ------------------------------------------------------------------
    # Round finalisation
    # ------------------------------------------------------------------

    def is_round_over(self) -> bool:
        return self._rules.is_round_over()

    def is_game_over(self) -> bool:
        return self._rules.game_over

    def commit_round(self) -> dict[int, tuple[int, int]]:
        """
        Commit round scores.

        Returns {seat_index: (round_danger, new_total)}.
        """
        raw = self._rules.commit_round_scores()  # {player_id: (rd, total)}
        return {self._player_to_seat[pid]: vals for pid, vals in raw.items()}

    # ------------------------------------------------------------------
    # State snapshots
    # ------------------------------------------------------------------

    def get_public_state(self) -> PublicMatchState:
        """Produce a PublicMatchState from the current local game state."""
        rules = self._rules

        board_rows: list[list[MatchCardPublic]] = []
        for row_idx, row in enumerate(rules.board.rows):
            owners = (
                self._board_row_owners[row_idx]
                if row_idx < len(self._board_row_owners)
                else []
            )
            board_rows.append([
                MatchCardPublic(
                    number=c.number,
                    danger=c.danger,
                    owner_seat=owners[pos] if pos < len(owners) else -1,
                )
                for pos, c in enumerate(row)
            ])

        player_order_seats = [
            self._player_to_seat[p.player_id]
            for p in rules.player_order
            if not p.is_eliminated
        ]

        committed_scores = {
            self._player_to_seat[pid]: score
            for pid, score in rules.committed_scores.items()
        }

        seats = [
            SeatIdentity(
                seat_index=p.player_id,
                controller_type=(
                    ControllerType.LOCAL if p.player_id == 0 else ControllerType.BOT
                ),
                display_name=p.name,
                user_id=None,
            )
            for p in sorted(rules.players, key=lambda pl: pl.player_id)
        ]

        return PublicMatchState(
            match_id=self._match_id,
            round_number=rules.round_state.round_number,
            phase=rules.round_state.phase.name,
            player_order_seats=player_order_seats,
            board_rows=board_rows,
            played_cards_this_turn=[],  # populated by the caller during reveal
            committed_scores=committed_scores,
            seats=seats,
        )

    def get_private_state(self) -> PrivatePlayerState:
        """Return the local human player's private state (seat 0)."""
        human = self._rules.players[0]
        hand = [
            MatchCardPublic(number=c.number, danger=c.danger, owner_seat=0)
            for c in human.hand
        ]
        return PrivatePlayerState(
            seat_index=0,
            hand=hand,
            has_selected=human.selected_card is not None,
        )
