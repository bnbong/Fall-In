"""
Game Scene - Main gameplay screen with isometric board
Integrated with actual game rules and AI players
"""

import pygame
from enum import Enum, auto
from typing import Optional

from fall_in.scenes.base_scene import Scene
from fall_in.utils.asset_loader import get_font, AssetLoader
from fall_in.utils.tween import Tween, TweenGroup
from fall_in.core.card import Card
from fall_in.core.player import create_players
from fall_in.core.rules import GameRules, TurnResult
from fall_in.ai.ai_player import create_ai_players
from fall_in.entities.soldier_figure import SoldierFigure
from fall_in.entities.commander import Commander
from fall_in.config import (
    SCREEN_WIDTH,
    SCREEN_HEIGHT,
    AIR_FORCE_BLUE,
    WHITE,
    LIGHT_BLUE,
    DANGER_SAFE,
    DANGER_CAUTION,
    DANGER_WARNING,
    DANGER_DANGER,
    DANGER_CRITICAL,
    NUM_ROWS,
    MAX_CARDS_PER_ROW,
    ISO_TILE_WIDTH,
    ISO_TILE_HEIGHT,
    ROW_SPACING,
    BOARD_OFFSET_X,
    BOARD_OFFSET_Y,
    GAME_OVER_SCORE,
    Difficulty,
)

# Turn timer constant
TURN_TIMEOUT_SECONDS = 30.0


class GamePhase(Enum):
    """UI game phase"""

    STARTING = auto()  # Round starting animation
    DEALING = auto()  # Cards being dealt from barracks
    SELECTING = auto()  # Player selecting card (30s timer)
    AI_THINKING = auto()  # AI players selecting
    REVEALING = auto()  # Cards being revealed
    PLACING_PLAYER = auto()  # Animating single player's card placement
    PENALTY_ANIMATION = auto()  # Animating penalty cards to hangar/player
    ROW_SELECT = auto()  # Player must select row
    ROUND_END = auto()  # Round ended
    GAME_OVER = auto()  # Game over


class GameScene(Scene):
    """
    Main game scene with isometric 4x6 board.
    Integrated with game rules for actual gameplay.
    """

    def __init__(
        self, difficulty: str = Difficulty.NORMAL, rules: Optional[GameRules] = None
    ):
        super().__init__()

        # Create or reuse game rules
        if rules is None:
            self.players = create_players()
            self.rules = GameRules(self.players)
            self.is_new_game = True
        else:
            self.rules = rules
            self.players = rules.players
            self.is_new_game = False

        self.human_player = self.players[0]
        self.ai_controllers = create_ai_players(self.players, difficulty)
        self.difficulty = difficulty

        # Game UI state
        self.phase = GamePhase.STARTING
        self.selected_card_index: Optional[int] = None
        self.dragging = False
        self.drag_pos = (0, 0)

        # Turn timer (30 seconds)
        self.turn_timer = TURN_TIMEOUT_SECONDS

        # Turn log for display
        self.turn_log: list[TurnResult] = []

        # Sequential placement state
        self.placement_queue: list[tuple] = []  # (player, card, order_idx) tuples
        self.current_placement: Optional[TurnResult] = None
        self.placement_tween: Optional[Tween] = None
        self.penalty_tweens: TweenGroup = TweenGroup()
        self.penalty_cards_animating: list[tuple[Card, Tween]] = []

        # Dealing animation state
        self.dealing_cards: list[
            tuple[Card, Tween]
        ] = []  # (card, tween) for flying cards
        self.dealt_card_count = 0  # Number of cards that have arrived

        # Animation state
        self.phase_timer = 0.0
        self.message = ""
        self.message_timer = 0.0

        # Commander (left side)
        self.commander = Commander()

        # Load images
        loader = AssetLoader()
        self.background_image = loader.load_image(
            "ui/backgrounds/ingame_background.png"
        )
        self.background_image = pygame.transform.scale(
            self.background_image, (SCREEN_WIDTH, SCREEN_HEIGHT)
        )

        # Start round
        self._start_new_round()

    def _start_new_round(self) -> None:
        """Start a new round"""
        self.rules.start_new_round()
        self.turn_log.clear()
        self.placement_queue.clear()
        self.message = f"라운드 {self.rules.round_state.round_number} 시작!"
        self.message_timer = 2.0

        # Start dealing animation
        self._start_dealing_animation()

    def _start_dealing_animation(self) -> None:
        """Start cards dealing animation from barracks to hand"""
        self.phase = GamePhase.DEALING
        self.dealing_cards.clear()
        self.dealt_card_count = 0

        # Barracks position (source) - hangar/barracks entrance in background
        barracks_x = SCREEN_WIDTH - 150  # Right side hangar entrance
        barracks_y = 200  # Lower to match building entrance

        # Hand positions (targets)
        hand = self.human_player.hand
        num_cards = len(hand)
        card_width = 60
        spacing = 65
        total_width = num_cards * card_width + (num_cards - 1) * (spacing - card_width)
        start_x = (SCREEN_WIDTH - total_width) // 2
        hand_y = SCREEN_HEIGHT - 120

        # Create tweens for each card with staggered start
        for i, card in enumerate(hand):
            target_x = start_x + i * spacing + card_width // 2
            target_y = hand_y + 40

            # Delay based on card index (0.1s per card)
            delay = i * 0.1

            tween = Tween(
                start=(barracks_x, barracks_y),
                end=(target_x, target_y),
                duration=0.4,
                easing="ease_out",
                delay=delay,
            )
            self.dealing_cards.append((card, tween))

    def _update_dealing_animation(self, dt: float) -> None:
        """Update dealing animation and check for completion"""
        all_complete = True
        arrived_count = 0

        for card, tween in self.dealing_cards:
            tween.update(dt)
            if tween.is_complete:
                arrived_count += 1
            else:
                all_complete = False

        self.dealt_card_count = arrived_count

        if all_complete:
            # All cards dealt, move to selecting phase
            self.phase = GamePhase.SELECTING
            self.turn_timer = TURN_TIMEOUT_SECONDS
            self.dealing_cards.clear()

    ROW_OFFSETS = [
        (0, 0),  # Row 0 - base position
        (23, 0),  # Row 1 - slight right shift
        (46, 0),  # Row 2 - more right shift
        (69, 0),  # Row 3 - most right shift
    ]

    def _cart_to_iso(self, x: int, y: int) -> tuple[int, int]:
        """Convert cartesian coordinates to isometric.

        x = column position within row (card index)
        y = row index (0-3 for the 4 game rows)

        ROW_SPACING adds extra vertical space between rows only.
        ROW_OFFSETS corrects position so first tiles align diagonally.
        """
        # Get row-specific offset
        row_x_offset, row_y_offset = (
            self.ROW_OFFSETS[y] if y < len(self.ROW_OFFSETS) else (0, 0)
        )

        iso_x = BOARD_OFFSET_X + (y - x) * (ISO_TILE_WIDTH // 2) + row_x_offset
        iso_y = (
            BOARD_OFFSET_Y
            + (x + y) * (ISO_TILE_HEIGHT // 2)
            + y * ROW_SPACING
            + row_y_offset
        )
        return iso_x, iso_y

    def _get_danger_color(self, score: int) -> tuple[int, int, int]:
        """Get color based on danger score"""
        if score < 20:
            return DANGER_SAFE
        elif score < 35:
            return DANGER_CAUTION
        elif score < 50:
            return DANGER_WARNING
        elif score < 60:
            return DANGER_DANGER
        else:
            return DANGER_CRITICAL

    def _draw_isometric_tile(
        self,
        screen: pygame.Surface,
        x: int,
        y: int,
        color: tuple,
        border_color: tuple = AIR_FORCE_BLUE,
    ) -> None:
        """Draw a single isometric tile (empty slot)"""
        iso_x, iso_y = self._cart_to_iso(x, y)

        # Diamond points
        points = [
            (iso_x, iso_y - ISO_TILE_HEIGHT // 2),
            (iso_x + ISO_TILE_WIDTH // 2, iso_y),
            (iso_x, iso_y + ISO_TILE_HEIGHT // 2),
            (iso_x - ISO_TILE_WIDTH // 2, iso_y),
        ]

        pygame.draw.polygon(screen, color, points)
        pygame.draw.polygon(screen, border_color, points, width=2)

    def _draw_board(self, screen: pygame.Surface) -> None:
        """Draw the isometric game board with soldier figures"""
        board = self.rules.board

        # First pass: draw all tiles (back to front for z-order)
        for row_idx in range(NUM_ROWS):
            for col in range(MAX_CARDS_PER_ROW + 1):
                visual_col = MAX_CARDS_PER_ROW - col
                row = board.rows[row_idx]

                if col < len(row):
                    card = row[col]
                    danger = card.danger
                    if danger <= 2:
                        color = DANGER_SAFE
                    elif danger <= 4:
                        color = DANGER_WARNING
                    else:
                        color = DANGER_DANGER
                    color = tuple(min(255, c + 60) for c in color)
                else:
                    color = (235, 225, 210)

                self._draw_isometric_tile(screen, visual_col, row_idx, color)

        # Second pass: draw soldier figures
        # Sort by isometric depth: draw back (low row + high visual_col) first
        # Collect all cards with positions
        soldiers_to_draw = []
        for row_idx in range(NUM_ROWS):
            row = board.rows[row_idx]
            for col in range(len(row)):
                visual_col = MAX_CARDS_PER_ROW - col
                card = row[col]
                iso_x, iso_y = self._cart_to_iso(visual_col, row_idx)
                # Depth: higher iso_y = more in front
                depth = iso_y
                soldiers_to_draw.append((depth, iso_x, iso_y, card))

        # Sort by depth (draw smaller iso_y first = back)
        soldiers_to_draw.sort(key=lambda s: s[0])

        for depth, iso_x, iso_y, card in soldiers_to_draw:
            figure = SoldierFigure(card)
            figure.render(screen, iso_x, iso_y, ISO_TILE_HEIGHT)

    def _draw_outlined_text(
        self,
        screen: pygame.Surface,
        text: str,
        font: pygame.font.Font,
        pos: tuple[int, int],
        color: tuple[int, int, int],
        outline_color: tuple[int, int, int] = WHITE,
    ) -> None:
        """Draw text with outline for better readability"""
        x, y = pos
        # Draw outline (white shadow in 4 directions)
        outline_surface = font.render(text, True, outline_color)
        for dx, dy in [(-1, -1), (-1, 1), (1, -1), (1, 1)]:
            screen.blit(outline_surface, (x + dx, y + dy))
        # Draw main text on top
        text_surface = font.render(text, True, color)
        screen.blit(text_surface, pos)

    def _draw_ui(self, screen: pygame.Surface) -> None:
        """Draw UI elements with new layout"""
        title_font = get_font(24, "bold")
        font = get_font(18)
        small_font = get_font(14)
        mini_font = get_font(12)

        # === TOP BAR BACKGROUND ===
        top_bar_height = 70
        top_bar_surface = pygame.Surface(
            (SCREEN_WIDTH, top_bar_height), pygame.SRCALPHA
        )
        top_bar_surface.fill((30, 60, 90, 200))  # Semi-transparent dark blue
        screen.blit(top_bar_surface, (0, 0))
        # Top bar bottom border
        pygame.draw.line(
            screen,
            AIR_FORCE_BLUE,
            (0, top_bar_height),
            (SCREEN_WIDTH, top_bar_height),
            2,
        )

        # === TOP BAR (Left to Right) ===
        top_y = 15

        # 1. Round indicator (left) - with outline for visibility
        self._draw_outlined_text(
            screen,
            f"ROUND {self.rules.round_state.round_number}",
            title_font,
            (20, top_y),
            WHITE,
            (10, 30, 50),
        )

        # 2. Hangar icon + penalty cards count (next to round)
        hangar_x = 150
        hangar_points = [
            (hangar_x, top_y + 25),
            (hangar_x + 15, top_y + 5),
            (hangar_x + 45, top_y + 5),
            (hangar_x + 60, top_y + 25),
        ]
        pygame.draw.polygon(screen, LIGHT_BLUE, hangar_points)
        pygame.draw.polygon(screen, WHITE, hangar_points, width=2)

        cards_taken = self.rules.get_player_round_penalty_count(self.human_player)
        self._draw_outlined_text(
            screen,
            str(cards_taken),
            font,
            (hangar_x + 22, top_y + 30),
            WHITE,
            AIR_FORCE_BLUE,
        )

        # 3. Player order display (below round/hangar)
        order_y = top_y + 35
        self._draw_outlined_text(
            screen, "순서:", mini_font, (20, order_y), WHITE, (10, 30, 50)
        )

        order_x = 55
        for i, player in enumerate(self.rules.player_order):
            if player == self.human_player:
                name = "나"
                color = DANGER_SAFE
            else:
                name = player.name.replace("AI ", "")
                color = LIGHT_BLUE

            is_current = (
                self.current_placement
                and self.current_placement.player == player
                and self.phase
                in [GamePhase.PLACING_PLAYER, GamePhase.PENALTY_ANIMATION]
            )

            if is_current:
                pygame.draw.rect(
                    screen,
                    DANGER_WARNING,
                    (order_x - 2, order_y - 2, 20, 16),
                    border_radius=3,
                )

            self._draw_outlined_text(
                screen,
                name,
                mini_font,
                (order_x, order_y),
                WHITE if is_current else color,
                (10, 30, 50),
            )

            if i < len(self.rules.player_order) - 1:
                self._draw_outlined_text(
                    screen,
                    "→",
                    mini_font,
                    (order_x + 14, order_y),
                    LIGHT_BLUE,
                    (10, 30, 50),
                )
            order_x += 28

        # 4. Danger gauge (center-right)
        committed = self.rules.get_player_committed_score(self.human_player)
        gauge_x = SCREEN_WIDTH // 2 + 50

        pygame.draw.polygon(
            screen,
            DANGER_DANGER,
            [
                (gauge_x, top_y + 5),
                (gauge_x - 12, top_y + 25),
                (gauge_x + 12, top_y + 25),
            ],
        )
        warning_text = small_font.render("!", True, WHITE)
        screen.blit(warning_text, (gauge_x - 3, top_y + 8))

        self._draw_outlined_text(
            screen,
            f"{committed}/{GAME_OVER_SCORE}",
            font,
            (gauge_x + 20, top_y + 5),
            WHITE,
            (10, 30, 50),
        )

        bar_x = gauge_x + 80
        bar_width = 100
        bar_height = 16
        fill_ratio = min(committed / GAME_OVER_SCORE, 1.0)

        pygame.draw.rect(
            screen,
            (200, 200, 200),
            (bar_x, top_y + 8, bar_width, bar_height),
            border_radius=3,
        )
        if fill_ratio > 0:
            fill_color = self._get_danger_color(committed)
            pygame.draw.rect(
                screen,
                fill_color,
                (bar_x, top_y + 8, int(bar_width * fill_ratio), bar_height),
                border_radius=3,
            )
        pygame.draw.rect(
            screen,
            AIR_FORCE_BLUE,
            (bar_x, top_y + 8, bar_width, bar_height),
            width=1,
            border_radius=3,
        )

        # === AI PLAYERS (Right sidebar, below top bar) ===
        for i, player in enumerate(self.players[1:]):
            ai_rect = pygame.Rect(SCREEN_WIDTH - 100, 90 + i * 60, 85, 55)
            bg_color = DANGER_DANGER if player.is_eliminated else LIGHT_BLUE
            pygame.draw.rect(screen, bg_color, ai_rect, border_radius=6)
            pygame.draw.rect(screen, AIR_FORCE_BLUE, ai_rect, width=2, border_radius=6)

            order_pos = self.rules.get_player_order_position(player)
            ai_name = small_font.render(f"{order_pos}.{player.name}", True, WHITE)
            screen.blit(ai_name, (ai_rect.x + 5, ai_rect.y + 5))

            ai_committed = self.rules.get_player_committed_score(player)
            ai_score = mini_font.render(f"위험: {ai_committed}", True, WHITE)
            screen.blit(ai_score, (ai_rect.x + 5, ai_rect.y + 23))

            ai_cards = self.rules.get_player_round_penalty_count(player)
            ai_cards_text = mini_font.render(f"벌칙: {ai_cards}장", True, WHITE)
            screen.blit(ai_cards_text, (ai_rect.x + 5, ai_rect.y + 38))

        # Turn log (bottom right with container)
        if self.turn_log:
            log_x = SCREEN_WIDTH - 180
            log_y = SCREEN_HEIGHT - 120
            log_width = 170
            log_height = 20 + min(len(self.turn_log), 4) * 18

            # Container background
            log_container = pygame.Surface((log_width, log_height), pygame.SRCALPHA)
            log_container.fill((30, 60, 90, 180))
            screen.blit(log_container, (log_x, log_y))
            pygame.draw.rect(
                screen,
                AIR_FORCE_BLUE,
                (log_x, log_y, log_width, log_height),
                width=2,
                border_radius=4,
            )

            # Title
            self._draw_outlined_text(
                screen,
                "이번 턴:",
                small_font,
                (log_x + 8, log_y + 4),
                WHITE,
                AIR_FORCE_BLUE,
            )

            for i, result in enumerate(self.turn_log[-4:]):  # Show last 4
                entry_text = f"{result.placement_order}. {result.player.name[:4]} → #{result.card.number}"
                self._draw_outlined_text(
                    screen,
                    entry_text,
                    mini_font,
                    (log_x + 10, log_y + 22 + i * 18),
                    WHITE,
                    (20, 40, 60),
                )

        # Game message
        if self.message and self.message_timer > 0:
            msg_surface = font.render(self.message, True, AIR_FORCE_BLUE)
            msg_rect = msg_surface.get_rect(
                center=(SCREEN_WIDTH // 2, SCREEN_HEIGHT // 2 - 50)
            )
            bg_rect = msg_rect.inflate(20, 10)
            pygame.draw.rect(screen, WHITE, bg_rect, border_radius=5)
            pygame.draw.rect(screen, AIR_FORCE_BLUE, bg_rect, width=1, border_radius=5)
            screen.blit(msg_surface, msg_rect)

        # Phase indicator
        phase_text = small_font.render(
            f"[{self._get_phase_text()}]", True, AIR_FORCE_BLUE
        )
        screen.blit(phase_text, (SCREEN_WIDTH - 120, SCREEN_HEIGHT - 20))

    def _get_commander_message(self) -> str:
        """Get commander message based on player's danger score"""
        committed = self.rules.get_player_committed_score(self.human_player)

        if committed < 20:
            return "순조롭군!"
        elif committed < 35:
            return "조심해라..."
        elif committed < 50:
            return "정신차려!"
        elif committed < 60:
            return "집무실로 와!"
        else:
            return "진급 포기냐?"

    def _get_phase_text(self) -> str:
        """Get current phase description"""
        phase_texts = {
            GamePhase.STARTING: "라운드 시작",
            GamePhase.SELECTING: "카드 선택",
            GamePhase.AI_THINKING: "AI 선택 중",
            GamePhase.REVEALING: "카드 공개",
            GamePhase.PLACING_PLAYER: "카드 배치",
            GamePhase.PENALTY_ANIMATION: "벌점 처리",
            GamePhase.ROW_SELECT: "열 선택",
            GamePhase.ROUND_END: "라운드 종료",
            GamePhase.GAME_OVER: "게임 종료",
        }
        return phase_texts.get(self.phase, "")

    def _draw_hand(self, screen: pygame.Surface) -> None:
        """Draw player's hand cards at the bottom"""
        hand = self.human_player.hand
        if not hand:
            return

        # During dealing, track which cards have arrived
        arrived_cards = set()
        if self.phase == GamePhase.DEALING:
            for card, tween in self.dealing_cards:
                if tween.is_complete:
                    arrived_cards.add(card)

        card_width = 70
        card_height = 100
        spacing = 8
        total_width = len(hand) * (card_width + spacing) - spacing
        start_x = SCREEN_WIDTH // 2 - total_width // 2
        y = SCREEN_HEIGHT - card_height - 25

        font = get_font(16)
        small_font = get_font(12)

        for i, card in enumerate(hand):
            x = start_x + i * (card_width + spacing)

            # During dealing, skip cards that haven't arrived yet
            if self.phase == GamePhase.DEALING and card not in arrived_cards:
                continue

            if self.dragging and i == self.selected_card_index:
                continue

            mouse_pos = pygame.mouse.get_pos()
            card_rect = pygame.Rect(x, y, card_width, card_height)
            is_hovered = card_rect.collidepoint(mouse_pos)
            is_selected = i == self.selected_card_index

            draw_y = y - 20 if (is_hovered or is_selected) else y

            # Card background
            bg_color = (220, 220, 220) if is_selected else (200, 200, 200)
            pygame.draw.rect(
                screen, bg_color, (x, draw_y, card_width, card_height), border_radius=8
            )
            border_width = 3 if is_selected else 2
            pygame.draw.rect(
                screen,
                AIR_FORCE_BLUE,
                (x, draw_y, card_width, card_height),
                width=border_width,
                border_radius=8,
            )

            # Card number
            num_text = font.render(f"#{card.number}", True, AIR_FORCE_BLUE)
            screen.blit(num_text, (x + 8, draw_y + 8))

            # Danger indicator
            if card.danger <= 2:
                danger_color = DANGER_SAFE
            elif card.danger <= 4:
                danger_color = DANGER_WARNING
            else:
                danger_color = DANGER_DANGER

            pygame.draw.circle(
                screen, danger_color, (x + card_width - 12, draw_y + 12), 8
            )
            danger_text = small_font.render(str(card.danger), True, WHITE)
            screen.blit(danger_text, (x + card_width - 16, draw_y + 7))

            # Soldier placeholder
            soldier_rect = pygame.Rect(x + 8, draw_y + 35, card_width - 16, 45)
            pygame.draw.rect(screen, LIGHT_BLUE, soldier_rect, border_radius=4)

    def handle_event(self, event: pygame.event.Event) -> None:
        """Handle pygame events"""
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                from fall_in.core.game_manager import GameManager
                from fall_in.scenes.title_scene import TitleScene

                GameManager().change_scene(TitleScene())
            elif event.key == pygame.K_SPACE:
                if (
                    self.phase == GamePhase.SELECTING
                    and self.selected_card_index is not None
                ):
                    self._confirm_card_selection()

        if self.phase == GamePhase.SELECTING:
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                self._handle_card_click(event.pos)
            elif event.type == pygame.MOUSEMOTION and self.dragging:
                self.drag_pos = event.pos
            elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
                if self.dragging:
                    self.dragging = False

    def _handle_card_click(self, pos: tuple[int, int]) -> None:
        """Handle clicking on a card in hand"""
        hand = self.human_player.hand
        if not hand:
            return

        card_width = 70
        card_height = 100
        spacing = 8
        total_width = len(hand) * (card_width + spacing) - spacing
        start_x = SCREEN_WIDTH // 2 - total_width // 2
        y = SCREEN_HEIGHT - card_height - 25

        for i in range(len(hand)):
            x = start_x + i * (card_width + spacing)
            card_rect = pygame.Rect(x, y - 20, card_width, card_height + 20)

            if card_rect.collidepoint(pos):
                if self.selected_card_index == i:
                    self._confirm_card_selection()
                else:
                    self.selected_card_index = i
                break

    def _confirm_card_selection(self) -> None:
        """Confirm card selection and proceed to AI phase"""
        if self.selected_card_index is None:
            return

        card = self.human_player.hand[self.selected_card_index]
        self.human_player.select_card(card)
        self.phase = GamePhase.AI_THINKING
        self.phase_timer = 0.5
        self.message = "AI가 카드를 선택 중..."
        self.message_timer = 0.5

    def _ai_select_cards(self) -> None:
        """Have all AI players select cards"""
        for ai in self.ai_controllers:
            if not ai.player.is_eliminated:
                ai.select_card(self.rules.board)

        # Get play order without executing - we'll execute one at a time
        play_order = self.rules.prepare_turn()

        # Convert to queue of (player, card, order_idx)
        self.placement_queue = [
            (player, card, idx + 1) for idx, (player, card) in enumerate(play_order)
        ]
        self.turn_log.clear()

        # Start sequential placement
        self._start_next_placement()

    def _start_next_placement(self) -> None:
        """Execute and animate the next player's card placement"""
        if not self.placement_queue:
            # All placements done
            self.rules.check_round_end()
            self._finish_turn()
            return

        # Get next placement
        player, card, order_idx = self.placement_queue.pop(0)

        # Execute this single placement (updates board immediately)
        result = self.rules.execute_single_placement(player, card, order_idx)
        self.turn_log.append(result)
        self.current_placement = result

        self.message = f"{result.player.name}: #{result.card.number}"
        self.message_timer = 1.0

        # Check if this placement resulted in penalty
        if result.result.penalty_score > 0:
            self.phase = GamePhase.PENALTY_ANIMATION
            self._start_penalty_animation(result)
        else:
            self.phase = GamePhase.PLACING_PLAYER
            self.phase_timer = 0.5  # Brief pause to show placement

    def _start_penalty_animation(self, result: TurnResult) -> None:
        """Start animation of penalty cards going to hangar or player"""
        self.penalty_cards_animating.clear()
        self.penalty_tweens = TweenGroup()

        # Penalty cards were taken from a row
        taken_cards = result.result.penalty_cards

        if result.player == self.human_player:
            # Animate to hangar icon (left side, x=150)
            target_x, target_y = 180, 40
        else:
            # Animate to AI player box (right side)
            player_idx = self.players.index(result.player) - 1
            target_x = SCREEN_WIDTH - 60
            target_y = 90 + player_idx * 60

        # Create tweens for each penalty card
        for i, card in enumerate(taken_cards):
            # Start position (approximate board center)
            start_x = BOARD_OFFSET_X
            start_y = BOARD_OFFSET_Y + 50

            # Stagger the animation
            tween = Tween(
                start=(start_x, start_y),
                end=(target_x, target_y),
                duration=0.4 + i * 0.1,
                easing="ease_in",
            )
            self.penalty_cards_animating.append((card, tween))
            self.penalty_tweens.add(tween)

        # Commander speaks when penalties happen
        if taken_cards:
            self.commander.say_penalty_taken()

    def _finish_turn(self) -> None:
        """Finish the turn after all placements are animated"""
        has_penalties = any(r.result.penalty_score > 0 for r in self.turn_log)

        if has_penalties:
            self.message = "배치 및 벌점 부여 완료!"
        else:
            self.message = "카드 배치 완료!"
        self.message_timer = 1.0

        # Check for round end
        if self.rules.is_round_over():
            self.phase = GamePhase.ROUND_END
            self.phase_timer = 1.0
            self.message = "라운드 종료! 잠시 후 정산..."
        else:
            self.selected_card_index = None
            self.turn_timer = TURN_TIMEOUT_SECONDS  # Reset timer for next turn
            self.phase = GamePhase.SELECTING

    def _auto_select_card(self) -> None:
        """Auto-select a card when timer runs out"""
        hand = self.human_player.hand
        if hand:
            # Select random card when timeout
            import random

            card = random.choice(hand)
            self.human_player.select_card(card)
            self.message = "시간 초과! 자동 선택됨"
            self.message_timer = 1.0
            self.phase = GamePhase.AI_THINKING
            self.phase_timer = 0.3

    def _go_to_result_scene(self) -> None:
        """Navigate to ResultScene for round settlement"""
        from fall_in.core.game_manager import GameManager
        from fall_in.scenes.result_scene import ResultScene

        result_scene = ResultScene(self.rules, self.players)
        GameManager().change_scene(result_scene)

    def update(self, dt: float) -> None:
        """Update scene state"""
        # Update timers
        if self.message_timer > 0:
            self.message_timer -= dt

        # Update dealing animation
        if self.phase == GamePhase.DEALING:
            self._update_dealing_animation(dt)
            return

        # Update turn timer during selection phase
        if self.phase == GamePhase.SELECTING:
            self.turn_timer -= dt
            if self.turn_timer <= 0:
                self._auto_select_card()
                return

        # Update commander (expression based on danger)
        committed = self.rules.get_player_committed_score(self.human_player)
        self.commander.set_expression_from_danger(committed)
        self.commander.update(dt)

        # Update penalty animations
        if self.phase == GamePhase.PENALTY_ANIMATION:
            if self.penalty_tweens.update(dt):
                # Animation complete, move to next placement
                self.penalty_cards_animating.clear()
                self._start_next_placement()
            return

        if self.phase_timer > 0:
            self.phase_timer -= dt
            return

        # Phase transitions
        if self.phase == GamePhase.AI_THINKING:
            self._ai_select_cards()
        elif self.phase == GamePhase.PLACING_PLAYER:
            self._start_next_placement()
        elif self.phase == GamePhase.ROUND_END:
            self._go_to_result_scene()

    def render(self, screen: pygame.Surface) -> None:
        """Render scene to screen"""
        # Draw background first
        screen.blit(self.background_image, (0, 0))

        # Draw board first (background layer)
        self._draw_board(screen)

        # Draw commander on top of board (speech bubble visible)
        self.commander.render(screen)

        self._draw_ui(screen)
        self._draw_hand(screen)

        # Draw dealing card animations
        if self.phase == GamePhase.DEALING:
            self._draw_dealing_animation(screen)
            font = get_font(18)
            hint = font.render("카드 배급 중...", True, AIR_FORCE_BLUE)
            screen.blit(
                hint, (SCREEN_WIDTH // 2 - hint.get_width() // 2, SCREEN_HEIGHT - 50)
            )

        # Draw penalty card animations
        self._draw_penalty_animation(screen)

        # Timer display during selection
        if self.phase == GamePhase.SELECTING:
            self._draw_turn_timer(screen)
            font = get_font(14)
            hint = font.render(
                "카드를 클릭하여 선택, 다시 클릭 또는 [SPACE]로 확정",
                True,
                AIR_FORCE_BLUE,
            )
            screen.blit(
                hint, (SCREEN_WIDTH // 2 - hint.get_width() // 2, SCREEN_HEIGHT - 18)
            )

    def _draw_turn_timer(self, screen: pygame.Surface) -> None:
        """Draw the 30 second turn timer"""
        timer_font = get_font(28, "bold")
        seconds = max(0, int(self.turn_timer))

        # Color changes as time runs out
        if seconds > 15:
            color = WHITE  # Changed from AIR_FORCE_BLUE for better visibility
        elif seconds > 5:
            color = DANGER_WARNING
        else:
            color = DANGER_DANGER

        # Use outlined text for better readability
        self._draw_outlined_text(
            screen, f"{seconds}s", timer_font, (230, 20), color, (10, 30, 50)
        )

    def _draw_dealing_animation(self, screen: pygame.Surface) -> None:
        """Draw cards flying from barracks to hand positions"""
        for card, tween in self.dealing_cards:
            if not tween.is_started:
                continue  # Wait for delay

            if tween.is_complete:
                continue  # Already arrived

            pos = tween.get_current_int()

            # Draw flying card
            card_width = 50
            card_height = 70
            card_rect = pygame.Rect(
                pos[0] - card_width // 2,
                pos[1] - card_height // 2,
                card_width,
                card_height,
            )

            # Card back (blue color during dealing)
            pygame.draw.rect(screen, LIGHT_BLUE, card_rect, border_radius=5)
            pygame.draw.rect(
                screen, AIR_FORCE_BLUE, card_rect, width=2, border_radius=5
            )

            # Card number
            num_font = get_font(14, "bold")
            num_text = num_font.render(f"#{card.number}", True, AIR_FORCE_BLUE)
            screen.blit(
                num_text,
                (
                    card_rect.centerx - num_text.get_width() // 2,
                    card_rect.centery - num_text.get_height() // 2,
                ),
            )

    def _draw_penalty_animation(self, screen: pygame.Surface) -> None:
        """Draw cards being sucked into hangar/player"""
        for card, tween in self.penalty_cards_animating:
            if tween.is_complete:
                continue

            pos = tween.get_current_int()
            progress = tween.get_progress()

            # Card shrinks as it moves
            scale = 1.0 - progress * 0.7
            card_width = int(40 * scale)
            card_height = int(55 * scale)

            if card_width > 5 and card_height > 5:
                # Draw small card representation
                card_rect = pygame.Rect(
                    pos[0] - card_width // 2,
                    pos[1] - card_height // 2,
                    card_width,
                    card_height,
                )

                # Card color based on danger
                if card.danger <= 2:
                    color = DANGER_SAFE
                elif card.danger <= 4:
                    color = DANGER_WARNING
                else:
                    color = DANGER_DANGER

                pygame.draw.rect(screen, color, card_rect, border_radius=3)
                pygame.draw.rect(
                    screen, AIR_FORCE_BLUE, card_rect, width=1, border_radius=3
                )

                # Card number
                if scale > 0.5:
                    num_font = get_font(int(12 * scale))
                    num_text = num_font.render(str(card.number), True, WHITE)
                    num_rect = num_text.get_rect(center=card_rect.center)
                    screen.blit(num_text, num_rect)
