"""
Match business logic: authoritative server-side game engine.

Wraps fall_in.core.GameRules to run multiplayer matches.  All methods are
synchronous; async broadcasting is done by the WS handler that calls these.

Key invariants:
  - player_id == seat_index for every seat (simplifies reverse lookup).
  - GameRules requires exactly 4 players; start_room() guarantees this.
  - Bots auto-select their card immediately at the start of each round.
  - board_row_owners[row][pos] = seat_index (-1 for starter cards).
  - last_turn_steps tracks the most recent turn for PublicMatchState serialisation.
"""

from __future__ import annotations

import uuid
from typing import Optional

from fall_in.ai.ai_player import AIPlayer
from fall_in.core.player import Player, PlayerType
from fall_in.core.rules import GameRules, RoundPhase
from fall_in.multiplayer.models import (
    ControllerType,
    MatchCardPublic,
    PrivatePlayerState,
    PublicMatchState,
    SeatIdentity,
)

from app.models.match import ActiveMatch, MatchSeat, RoundSummary, TurnStep
from app.models.room import Room, SeatControllerType
from app.repositories.match_repo import InMemoryMatchRepo


class MatchError(Exception):
    pass


class MatchService:
    def __init__(self, repo: InMemoryMatchRepo) -> None:
        self.repo = repo

    # ------------------------------------------------------------------
    # Create
    # ------------------------------------------------------------------

    def create_match(self, room: Room) -> ActiveMatch:
        """
        Create an ActiveMatch from a STARTING room.

        Builds Player objects for each seat, runs start_new_round(), and
        auto-selects cards for all bot seats.  Raises MatchError if the
        room does not have exactly 4 participants.
        """
        match_id = str(uuid.uuid4())

        players: list[Player] = []
        seats: dict[int, MatchSeat] = {}
        player_to_seat: dict[int, int] = {}

        for seat_idx in range(4):
            participant = room.participants.get(seat_idx)
            if participant is None:
                raise MatchError(
                    f"Room {room.room_code} is missing seat {seat_idx}. "
                    "All 4 seats must be filled before starting a match."
                )

            is_bot = participant.controller_type == SeatControllerType.BOT
            ptype = PlayerType.AI if is_bot else PlayerType.HUMAN
            player = Player(
                name=participant.display_name,
                player_type=ptype,
                player_id=seat_idx,  # player_id == seat_index
            )
            players.append(player)
            player_to_seat[seat_idx] = seat_idx

            ai_ctrl: Optional[AIPlayer] = AIPlayer(player) if is_bot else None

            seats[seat_idx] = MatchSeat(
                seat_index=seat_idx,
                player=player,
                connection_id=participant.connection_id,
                user_id=participant.user_id,
                display_name=participant.display_name,
                controller_type=participant.controller_type,
                ai_controller=ai_ctrl,
            )

        # GameRules.__init__ asserts len(players) == NUM_PLAYERS (4).
        # players are already in seat_index order (0-3).
        # human_seat=None: multiplayer — game ends only when 1 survivor remains,
        # not when any specific seat is eliminated.
        rules = GameRules(players, human_seat=None)

        match = ActiveMatch(
            match_id=match_id,
            room_code=room.room_code,
            rules=rules,
            seats=seats,
            player_to_seat=player_to_seat,
            board_row_owners=[[], [], [], []],
            last_turn_steps=[],
        )

        self.repo.create(match)
        self._start_round(match)
        return match

    # ------------------------------------------------------------------
    # Round management
    # ------------------------------------------------------------------

    def _start_round(self, match: ActiveMatch) -> None:
        """
        Deal cards for a new round and immediately auto-select for bot seats.

        Called by create_match() for the first round, and by start_next_round()
        for subsequent rounds.
        """
        rules: GameRules = match.rules  # type: ignore[assignment]
        rules.start_new_round()

        # Starter cards placed on rows at round start have no owner.
        match.board_row_owners = [[-1] for _ in range(4)]
        match.last_turn_steps = []

        # Bots select immediately; humans will submit CARD_SELECT over WS.
        for seat in match.seats.values():
            if seat.ai_controller is not None and not seat.player.is_eliminated:  # type: ignore[union-attr]
                seat.ai_controller.select_card(rules.board)  # type: ignore[union-attr]

    def start_next_round(self, match: ActiveMatch) -> None:
        """Start the next round (used after ROUND_RESULT is broadcast)."""
        self._start_round(match)

    def reselect_bots(self, match: ActiveMatch) -> None:
        """
        Auto-select cards for all non-eliminated bot seats.

        Must be called after each turn resolution before re-entering the
        SELECTING phase so that bots have a card ready for the next turn.
        (execute_single_placement clears selected_card for every player.)
        """
        rules: GameRules = match.rules  # type: ignore[assignment]
        for seat in match.seats.values():
            if seat.ai_controller is not None and not seat.player.is_eliminated:  # type: ignore[union-attr]
                seat.ai_controller.select_card(rules.board)  # type: ignore[union-attr]

    # ------------------------------------------------------------------
    # Card selection
    # ------------------------------------------------------------------

    def submit_selection(
        self, match: ActiveMatch, seat_index: int, card_number: int
    ) -> None:
        """
        Record a human seat's card selection.

        Raises MatchError on: unknown seat, bot seat, wrong phase, eliminated
        player, already-selected, or card not in hand.
        """
        rules: GameRules = match.rules  # type: ignore[assignment]
        seat = match.seats.get(seat_index)
        if seat is None:
            raise MatchError(f"Seat {seat_index} not found in match")
        if seat.controller_type != SeatControllerType.REMOTE:
            raise MatchError("Only human (REMOTE) seats can submit card selections")
        if rules.round_state.phase != RoundPhase.SELECTING:
            raise MatchError("Not in SELECTING phase")
        if seat.player.is_eliminated:  # type: ignore[union-attr]
            raise MatchError("Eliminated player cannot select a card")
        if seat.player.selected_card is not None:  # type: ignore[union-attr]
            raise MatchError("This seat has already selected a card this turn")

        target_card = next(
            (c for c in seat.player.hand if c.number == card_number),  # type: ignore[union-attr]
            None,
        )
        if target_card is None:
            raise MatchError(f"Card {card_number} is not in seat {seat_index}'s hand")

        seat.player.select_card(target_card)  # type: ignore[union-attr]

    def all_selected(self, match: ActiveMatch) -> bool:
        """True when every non-eliminated player has selected a card."""
        rules: GameRules = match.rules  # type: ignore[assignment]
        return rules.all_players_selected()

    # ------------------------------------------------------------------
    # Turn resolution
    # ------------------------------------------------------------------

    def resolve_turn(self, match: ActiveMatch) -> list[TurnStep]:
        """
        Execute the full turn step by step.

        Returns the ordered list of TurnStep (one per non-eliminated player)
        and updates board_row_owners and last_turn_steps.
        """
        rules: GameRules = match.rules  # type: ignore[assignment]

        # prepare_turn() validates all_selected and sets phase to PLACING.
        play_order = rules.prepare_turn()

        steps: list[TurnStep] = []
        for order_idx, (player, card) in enumerate(play_order):
            turn_result = rules.execute_single_placement(player, card, order_idx + 1)
            placement = turn_result.result  # fall_in.core.board.PlacementResult
            seat_idx = match.player_to_seat[player.player_id]

            # Update board ownership.
            if placement.had_to_take_row or placement.penalty_score > 0:
                # Row was cleared (player took it or placed the 6th card).
                # Our card is now the sole occupant.
                match.board_row_owners[placement.row_index] = [seat_idx]
            else:
                # Normal placement — append to the existing owners list.
                match.board_row_owners[placement.row_index].append(seat_idx)

            steps.append(
                TurnStep(
                    seat_index=seat_idx,
                    card_number=card.number,
                    card_danger=card.danger,
                    row_index=placement.row_index,
                    penalty_score=placement.penalty_score,
                    had_to_take_row=placement.had_to_take_row,
                    order=order_idx + 1,
                )
            )

        # Update phase to SELECTING or ROUND_END.
        rules.check_round_end()

        match.last_turn_steps = steps
        return steps

    def resolve_turn_stepwise(
        self, match: ActiveMatch
    ) -> "list[tuple[TurnStep, PublicMatchState]]":
        """
        Execute the full turn one placement at a time.

        After each placement the board ownership and last_turn_steps are
        updated so that build_public_state() produces an incremental snapshot
        (i.e., the board state *after* that specific card was placed, with
        played_cards_this_turn reflecting only the cards placed so far).

        Returns a list of (TurnStep, PublicMatchState) pairs in placement order.
        The caller should iterate the list to broadcast each step + snapshot.

        After this method returns, last_turn_steps contains all steps and
        check_round_end() has been called to update the phase.
        """
        rules: GameRules = match.rules  # type: ignore[assignment]
        play_order = rules.prepare_turn()

        results: list[tuple[TurnStep, PublicMatchState]] = []
        accumulated: list[TurnStep] = []

        for order_idx, (player, card) in enumerate(play_order):
            turn_result = rules.execute_single_placement(player, card, order_idx + 1)
            placement = turn_result.result
            seat_idx = match.player_to_seat[player.player_id]

            if placement.had_to_take_row or placement.penalty_score > 0:
                match.board_row_owners[placement.row_index] = [seat_idx]
            else:
                match.board_row_owners[placement.row_index].append(seat_idx)

            step = TurnStep(
                seat_index=seat_idx,
                card_number=card.number,
                card_danger=card.danger,
                row_index=placement.row_index,
                penalty_score=placement.penalty_score,
                had_to_take_row=placement.had_to_take_row,
                order=order_idx + 1,
            )
            accumulated.append(step)
            # Temporarily set last_turn_steps so build_public_state reflects
            # only the placements that have happened so far.
            match.last_turn_steps = list(accumulated)
            results.append((step, self.build_public_state(match)))

        rules.check_round_end()
        # last_turn_steps already holds all steps for this turn.
        return results

    # ------------------------------------------------------------------
    # Round finalisation
    # ------------------------------------------------------------------

    def finalize_round(self, match: ActiveMatch) -> RoundSummary:
        """
        Commit round scores and determine if the game is over.

        Must be called after resolve_turn() confirms is_round_over().
        """
        rules: GameRules = match.rules  # type: ignore[assignment]

        # {player_id: (round_danger, new_total)}
        score_results = rules.commit_round_scores()

        round_danger: dict[int, int] = {}
        total_scores: dict[int, int] = {}
        for player_id, (rd, total) in score_results.items():
            seat_idx = match.player_to_seat[player_id]
            round_danger[seat_idx] = rd
            total_scores[seat_idx] = total

        eliminated_seats = [
            seat.seat_index
            for seat in match.seats.values()
            if seat.player.is_eliminated  # type: ignore[union-attr]
        ]

        winner_seat: Optional[int] = None
        if rules.game_over and rules.winner is not None:
            winner_seat = match.player_to_seat[rules.winner.player_id]

        return RoundSummary(
            round_number=rules.round_state.round_number,
            round_danger=round_danger,
            total_scores=total_scores,
            eliminated_seats=eliminated_seats,
            game_over=rules.game_over,
            winner_seat=winner_seat,
        )

    # ------------------------------------------------------------------
    # State snapshots
    # ------------------------------------------------------------------

    def build_public_state(self, match: ActiveMatch) -> PublicMatchState:
        """
        Produce a wire-safe PublicMatchState for broadcasting to all seats.

        Uses board_row_owners for per-card owner_seat values.
        played_cards_this_turn reflects the most recently resolved turn.
        """
        rules: GameRules = match.rules  # type: ignore[assignment]

        # Board rows: zip actual cards with their ownership tracking.
        board_rows: list[list[MatchCardPublic]] = []
        for row_idx, row in enumerate(rules.board.rows):
            owners = (
                match.board_row_owners[row_idx]
                if row_idx < len(match.board_row_owners)
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

        # Player turn order as seat indices (skip eliminated).
        player_order_seats = [
            match.player_to_seat[p.player_id]
            for p in rules.player_order
            if not p.is_eliminated
        ]

        # Cumulative committed scores keyed by seat_index.
        committed_scores = {
            match.player_to_seat[pid]: score
            for pid, score in rules.committed_scores.items()
        }

        # Seat identity list for all four seats.
        seat_identities: list[SeatIdentity] = [
            SeatIdentity(
                seat_index=seat.seat_index,
                controller_type=(
                    ControllerType.BOT
                    if seat.controller_type == SeatControllerType.BOT
                    else ControllerType.REMOTE
                ),
                display_name=seat.display_name,
                user_id=seat.user_id,
            )
            for seat in sorted(match.seats.values(), key=lambda s: s.seat_index)
        ]

        # Cards placed during the most recently resolved turn.
        played_this_turn: list[MatchCardPublic] = [
            MatchCardPublic(
                number=step.card_number,
                danger=step.card_danger,
                owner_seat=step.seat_index,
            )
            for step in match.last_turn_steps
        ]

        return PublicMatchState(
            match_id=match.match_id,
            round_number=rules.round_state.round_number,
            phase=rules.round_state.phase.name,
            player_order_seats=player_order_seats,
            board_rows=board_rows,
            played_cards_this_turn=played_this_turn,
            committed_scores=committed_scores,
            seats=seat_identities,
        )

    def build_private_state(
        self, match: ActiveMatch, seat_index: int
    ) -> PrivatePlayerState:
        """
        Produce a PrivatePlayerState for unicasting to the given seat only.

        owner_seat on hand cards is always seat_index (the viewer's own seat).
        """
        seat = match.seats.get(seat_index)
        if seat is None:
            raise MatchError(f"Seat {seat_index} not found in match {match.match_id}")

        hand = [
            MatchCardPublic(
                number=c.number,
                danger=c.danger,
                owner_seat=seat_index,
            )
            for c in seat.player.hand  # type: ignore[union-attr]
        ]

        return PrivatePlayerState(
            seat_index=seat_index,
            hand=hand,
            has_selected=seat.player.selected_card is not None,  # type: ignore[union-attr]
        )

    # ------------------------------------------------------------------
    # Lookup helpers
    # ------------------------------------------------------------------

    def get_match(self, match_id: str) -> Optional[ActiveMatch]:
        return self.repo.get(match_id)

    def get_match_by_room(self, room_code: str) -> Optional[ActiveMatch]:
        return self.repo.get_by_room(room_code)

    def delete_match(self, match_id: str) -> None:
        self.repo.delete(match_id)

    def reset(self) -> None:
        """Clear all active matches.  Called between tests."""
        self.repo.clear()
