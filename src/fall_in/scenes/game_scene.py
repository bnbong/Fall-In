"""
Game Scene - Main gameplay screen with isometric board.

Integrates actual game rules, AI players, and sequential card placement
animations on a 4-row isometric board.
"""

import random
from enum import Enum, auto
from typing import Optional

import pygame

from fall_in.scenes.base_scene import Scene
from fall_in.utils.asset_loader import get_font, AssetLoader
from fall_in.utils.tween import Tween, TweenGroup
from fall_in.utils.danger_utils import (
    TileType,
    get_danger_color,
    get_tile_type_by_danger,
)
from fall_in.utils.text_utils import draw_outlined_text
from fall_in.core.card import Card
from fall_in.core.player import create_players
from fall_in.core.rules import GameRules, TurnResult
from fall_in.ai.ai_player import create_ai_players
from fall_in.entities.soldier_figure import SoldierFigure
from fall_in.entities.commander import Commander
from fall_in.entities.battalion_card import BattalionCard
from fall_in.entities.dust_particle import DustEffect
from fall_in.config import (
    SCREEN_WIDTH,
    SCREEN_HEIGHT,
    AIR_FORCE_BLUE,
    WHITE,
    LIGHT_BLUE,
    DANGER_SAFE,
    DANGER_WARNING,
    DANGER_DANGER,
    NUM_ROWS,
    MAX_CARDS_PER_ROW,
    ISO_TILE_WIDTH,
    ISO_TILE_HEIGHT,
    ROW_SPACING,
    BOARD_OFFSET_X,
    BOARD_OFFSET_Y,
    GAME_OVER_SCORE,
    Difficulty,
    TURN_TIMEOUT_SECONDS,
    TIMER_WARNING_THRESHOLD,
    TIMER_DANGER_THRESHOLD,
    # Hand layout
    HAND_FAN_SPREAD,
    HAND_CARD_OVERLAP,
    HAND_Y_OFFSET,
    HAND_HOVER_POP_DISTANCE,
    HAND_HOVER_SCALE,
    # Board
    ROW_OFFSETS,
    BARRACKS_X,
    BARRACKS_Y,
    # UI
    UI_TOP_BAR_Y,
    UI_TOP_BAR_HEIGHT,
    UI_ELEMENT_PLAYER_ORDER_X,
    UI_ELEMENT_DANGER_GAUGE_WIDTH,
    UI_ELEMENT_DANGER_GAUGE_HEIGHT,
    ICON_HANGER_X,
    TURN_LOG_X,
    TURN_LOG_Y,
    TURN_LOG_WIDTH,
    DEALING_CARD_COLOR,
    DEALING_CARD_BORDER_COLOR,
    TOP_BAR_BG_COLOR,
    TOP_BAR_OUTLINE_COLOR,
    SCREEN_SHAKE_DURATION,
    SCREEN_SHAKE_PADDING,
    CARD_DEAL_DELAY,
    CARD_DEAL_DURATION,
    AI_THINKING_DURATION,
    PLACEMENT_PAUSE_DURATION,
)


class GamePhase(Enum):
    """UI game phase states."""

    STARTING = auto()
    DEALING = auto()
    SELECTING = auto()
    AI_THINKING = auto()
    REVEALING = auto()
    PLACING_PLAYER = auto()
    PENALTY_ANIMATION = auto()
    ROW_SELECT = auto()
    ROUND_END = auto()
    GAME_OVER = auto()


class GameScene(Scene):
    """
    Main game scene with isometric 4x6 board.
    Integrates with game rules for actual gameplay.
    """

    ROW_OFFSETS = ROW_OFFSETS

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

        # Turn timer
        self.turn_timer = TURN_TIMEOUT_SECONDS

        # Turn log for display
        self.turn_log: list[TurnResult] = []

        # Sequential placement state
        self.placement_queue: list[tuple] = []
        self.current_placement: Optional[TurnResult] = None
        self.placement_tween: Optional[Tween] = None
        self.penalty_tweens: TweenGroup = TweenGroup()
        self.penalty_cards_animating: list[tuple[Card, Tween]] = []

        # Dealing animation state
        self.dealing_cards: list[tuple[Card, Tween]] = []
        self.dealt_card_count = 0

        # Animation state
        self.phase_timer = 0.0
        self.message = ""
        self.message_timer = 0.0

        # Commander (left side)
        self.commander = Commander()

        # Dust effect system
        self.dust_effect = DustEffect()

        # Screen shake state
        self.screen_shake_timer = 0.0
        self.screen_shake_intensity = 0
        self.screen_shake_offset = (0, 0)

        # Persistent soldier figures on board (card.number -> SoldierFigure)
        self.soldier_figures: dict[int, SoldierFigure] = {}

        # Load background image (with extra padding for shake)
        loader = AssetLoader()
        self.background_image = loader.load_image(
            "ui/backgrounds/ingame_background.png"
        )
        self.background_image = pygame.transform.smoothscale(
            self.background_image,
            (
                SCREEN_WIDTH + SCREEN_SHAKE_PADDING * 2,
                SCREEN_HEIGHT + SCREEN_SHAKE_PADDING * 2,
            ),
        )

        # Load tile images
        self.tile_images = {
            TileType.EMPTY.value: loader.load_image("entity/tile_1.png"),
            TileType.SAFE.value: loader.load_image("entity/tile_2.png"),
            TileType.WARNING.value: loader.load_image("entity/tile_3.png"),
            TileType.DANGER.value: loader.load_image("entity/tile_4.png"),
        }
        for key in self.tile_images:
            self.tile_images[key] = pygame.transform.smoothscale(
                self.tile_images[key], (int(ISO_TILE_WIDTH), int(ISO_TILE_HEIGHT))
            )

        # Start round
        self._start_new_round()

    # ------------------------------------------------------------------
    # Round lifecycle
    # ------------------------------------------------------------------

    def _start_new_round(self) -> None:
        """Start a new round."""
        self.rules.start_new_round()
        self.turn_log.clear()
        self.placement_queue.clear()
        self.message = f"라운드 {self.rules.round_state.round_number} 시작!"
        self.message_timer = 2.0

        committed = self.rules.get_player_committed_score(self.human_player)
        self.commander.set_expression_from_danger(committed)

        self._start_dealing_animation()

    def _start_dealing_animation(self) -> None:
        """Start cards dealing animation from barracks to hand."""
        self.phase = GamePhase.DEALING
        self.dealing_cards.clear()
        self.dealt_card_count = 0

        hand = self.human_player.hand
        num_cards = len(hand)
        card_width = 60
        spacing = 65
        total_width = num_cards * card_width + (num_cards - 1) * (spacing - card_width)
        start_x = (SCREEN_WIDTH - total_width) // 2
        hand_y = SCREEN_HEIGHT - 120

        for i, card in enumerate(hand):
            target_x = start_x + i * spacing + card_width // 2
            target_y = hand_y + 40

            tween = Tween(
                start=(BARRACKS_X, BARRACKS_Y),
                end=(target_x, target_y),
                duration=CARD_DEAL_DURATION,
                easing="ease_out",
                delay=i * CARD_DEAL_DELAY,
            )
            self.dealing_cards.append((card, tween))

    def _update_dealing_animation(self, dt: float) -> None:
        """Update dealing animation and check for completion."""
        all_complete = True
        arrived_count = 0

        for _, tween in self.dealing_cards:
            tween.update(dt)
            if tween.is_complete:
                arrived_count += 1
            else:
                all_complete = False

        self.dealt_card_count = arrived_count

        if all_complete:
            self.phase = GamePhase.SELECTING
            self.turn_timer = TURN_TIMEOUT_SECONDS
            self.dealing_cards.clear()

    # ------------------------------------------------------------------
    # Isometric helpers
    # ------------------------------------------------------------------

    def _cart_to_iso(self, x: int, y: int) -> tuple[int, int]:
        """
        Convert cartesian (col, row) to isometric screen coordinates.

        Args:
            x: Column position within row (card index).
            y: Row index (0-3).

        Returns:
            (iso_x, iso_y) screen coordinates.
        """
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
        return int(iso_x), int(iso_y)

    # ------------------------------------------------------------------
    # Board drawing
    # ------------------------------------------------------------------

    def _draw_isometric_tile(
        self,
        screen: pygame.Surface,
        x: int,
        y: int,
        tile_type: TileType = TileType.EMPTY,
    ) -> None:
        """Draw a single isometric tile using tile images."""
        iso_x, iso_y = self._cart_to_iso(x, y)
        tile_image = self.tile_images.get(
            tile_type.value, self.tile_images[TileType.EMPTY.value]
        )
        tile_rect = tile_image.get_rect(center=(iso_x, iso_y))
        screen.blit(tile_image, tile_rect)

    def _draw_board(self, screen: pygame.Surface) -> None:
        """Draw the isometric game board with soldier figures."""
        board = self.rules.board

        # Collect all tiles with depth for proper z-ordering
        tiles_to_draw = []
        for row_idx in range(NUM_ROWS):
            for col in range(MAX_CARDS_PER_ROW + 1):
                visual_col = MAX_CARDS_PER_ROW - col
                row = board.rows[row_idx]

                tile_type = (
                    get_tile_type_by_danger(row[col].danger)
                    if col < len(row)
                    else TileType.EMPTY
                )
                iso_x, iso_y = self._cart_to_iso(visual_col, row_idx)
                tiles_to_draw.append((iso_y, visual_col, row_idx, tile_type))

        tiles_to_draw.sort(key=lambda t: t[0])

        for _, visual_col, row_idx, tile_type in tiles_to_draw:
            self._draw_isometric_tile(screen, visual_col, row_idx, tile_type)

        # Draw soldier figures (sorted by depth)
        soldiers_to_draw = []
        for row_idx in range(NUM_ROWS):
            row = board.rows[row_idx]
            for col in range(len(row)):
                visual_col = MAX_CARDS_PER_ROW - col
                card = row[col]
                iso_x, iso_y = self._cart_to_iso(visual_col, row_idx)
                soldiers_to_draw.append((iso_y, iso_x, iso_y, card))

        soldiers_to_draw.sort(key=lambda s: s[0])

        for _, iso_x, iso_y, card in soldiers_to_draw:
            if card.number not in self.soldier_figures:
                figure = SoldierFigure(card)
                figure.start_drop(iso_y)
                self.soldier_figures[card.number] = figure
            else:
                figure = self.soldier_figures[card.number]
            figure.render(screen, iso_x, iso_y, int(ISO_TILE_HEIGHT))

    # ------------------------------------------------------------------
    # UI drawing
    # ------------------------------------------------------------------

    def _draw_ui(self, screen: pygame.Surface) -> None:
        """Draw UI elements: top bar, AI sidebar, turn log, messages."""
        title_font = get_font(24, "bold")
        font = get_font(18)
        small_font = get_font(14)
        mini_font = get_font(12)

        # === TOP BAR ===
        top_bar_surface = pygame.Surface(
            (SCREEN_WIDTH, UI_TOP_BAR_HEIGHT), pygame.SRCALPHA
        )
        top_bar_surface.fill(TOP_BAR_BG_COLOR)
        screen.blit(top_bar_surface, (0, 0))
        pygame.draw.line(
            screen,
            AIR_FORCE_BLUE,
            (0, UI_TOP_BAR_HEIGHT),
            (SCREEN_WIDTH, UI_TOP_BAR_HEIGHT),
            2,
        )

        top_y = UI_TOP_BAR_Y

        # Round indicator
        draw_outlined_text(
            screen,
            f"ROUND {self.rules.round_state.round_number}",
            title_font,
            (20, top_y),
            WHITE,
            TOP_BAR_OUTLINE_COLOR,
        )

        # Hangar icon + penalty cards count
        hangar_x = ICON_HANGER_X
        hangar_points = [
            (hangar_x, top_y + 25),
            (hangar_x + 15, top_y + 5),
            (hangar_x + 45, top_y + 5),
            (hangar_x + 60, top_y + 25),
        ]
        pygame.draw.polygon(screen, LIGHT_BLUE, hangar_points)
        pygame.draw.polygon(screen, WHITE, hangar_points, width=2)

        cards_taken = self.rules.get_player_round_penalty_count(self.human_player)
        draw_outlined_text(
            screen,
            str(cards_taken),
            font,
            (hangar_x + 22, top_y + 30),
            WHITE,
            AIR_FORCE_BLUE,
        )

        # Player order display
        order_y = top_y + 35
        draw_outlined_text(
            screen, "순서:", mini_font, (20, order_y), WHITE, TOP_BAR_OUTLINE_COLOR
        )

        order_x = UI_ELEMENT_PLAYER_ORDER_X
        for i, player in enumerate(self.rules.player_order):
            name = (
                "나" if player == self.human_player else player.name.replace("AI ", "")
            )
            color = DANGER_SAFE if player == self.human_player else LIGHT_BLUE

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

            draw_outlined_text(
                screen,
                name,
                mini_font,
                (order_x, order_y),
                WHITE if is_current else color,
                TOP_BAR_OUTLINE_COLOR,
            )

            if i < len(self.rules.player_order) - 1:
                draw_outlined_text(
                    screen,
                    "→",
                    mini_font,
                    (order_x + 14, order_y),
                    LIGHT_BLUE,
                    TOP_BAR_OUTLINE_COLOR,
                )
            order_x += 28

        # Danger gauge (center-right)
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
        screen.blit(small_font.render("!", True, WHITE), (gauge_x - 3, top_y + 8))

        draw_outlined_text(
            screen,
            f"{committed}/{GAME_OVER_SCORE}",
            font,
            (gauge_x + 20, top_y + 5),
            WHITE,
            TOP_BAR_OUTLINE_COLOR,
        )

        bar_x = gauge_x + 80
        bar_w = UI_ELEMENT_DANGER_GAUGE_WIDTH
        bar_h = UI_ELEMENT_DANGER_GAUGE_HEIGHT
        fill_ratio = min(committed / GAME_OVER_SCORE, 1.0)

        pygame.draw.rect(
            screen, (200, 200, 200), (bar_x, top_y + 8, bar_w, bar_h), border_radius=3
        )
        if fill_ratio > 0:
            pygame.draw.rect(
                screen,
                get_danger_color(committed),
                (bar_x, top_y + 8, int(bar_w * fill_ratio), bar_h),
                border_radius=3,
            )
        pygame.draw.rect(
            screen,
            AIR_FORCE_BLUE,
            (bar_x, top_y + 8, bar_w, bar_h),
            width=1,
            border_radius=3,
        )

        # Player icon (far right)
        self._draw_player_icon_ui(screen, top_y)

        # === AI PLAYERS (Right sidebar) ===
        for i, player in enumerate(self.players[1:]):
            ai_rect = pygame.Rect(SCREEN_WIDTH - 100, 90 + i * 60, 85, 55)
            bg_color = DANGER_DANGER if player.is_eliminated else LIGHT_BLUE
            pygame.draw.rect(screen, bg_color, ai_rect, border_radius=6)
            pygame.draw.rect(screen, AIR_FORCE_BLUE, ai_rect, width=2, border_radius=6)

            order_pos = self.rules.get_player_order_position(player)
            screen.blit(
                small_font.render(f"{order_pos}.{player.name}", True, WHITE),
                (ai_rect.x + 5, ai_rect.y + 5),
            )

            ai_committed = self.rules.get_player_committed_score(player)
            screen.blit(
                mini_font.render(f"위험: {ai_committed}", True, WHITE),
                (ai_rect.x + 5, ai_rect.y + 23),
            )

            ai_cards = self.rules.get_player_round_penalty_count(player)
            screen.blit(
                mini_font.render(f"벌칙: {ai_cards}장", True, WHITE),
                (ai_rect.x + 5, ai_rect.y + 38),
            )

        # Turn log
        if self.turn_log:
            log_x = TURN_LOG_X
            log_y = TURN_LOG_Y
            log_width = TURN_LOG_WIDTH
            log_height = 20 + min(len(self.turn_log), 4) * 18

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

            draw_outlined_text(
                screen,
                "이번 턴:",
                small_font,
                (log_x + 8, log_y + 4),
                WHITE,
                AIR_FORCE_BLUE,
            )

            for i, result in enumerate(self.turn_log[-4:]):
                entry_text = f"{result.placement_order}. {result.player.name[:4]} → #{result.card.number}"
                draw_outlined_text(
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

    def _draw_player_icon_ui(self, screen: pygame.Surface, top_y: int) -> None:
        """Draw player icon and currency in top bar (far right)."""
        icon_x = SCREEN_WIDTH - 50
        icon_y = top_y + 20
        icon_radius = 18

        pygame.draw.circle(screen, (80, 100, 130), (icon_x, icon_y), icon_radius)
        pygame.draw.circle(screen, AIR_FORCE_BLUE, (icon_x, icon_y), icon_radius, 2)

        icon_font = get_font(18)
        icon_text = icon_font.render("👤", True, WHITE)
        screen.blit(icon_text, icon_text.get_rect(center=(icon_x, icon_y)))

    def _get_phase_text(self) -> str:
        """Get current phase description in Korean."""
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

    # ------------------------------------------------------------------
    # Hand drawing
    # ------------------------------------------------------------------

    def _draw_hand(self, screen: pygame.Surface) -> None:
        """Draw player's hand cards in a fan layout at the bottom."""
        hand = self.human_player.hand
        if not hand:
            return

        arrived_cards = set()
        if self.phase == GamePhase.DEALING:
            for card, tween in self.dealing_cards:
                if tween.is_complete:
                    arrived_cards.add(card)

        card_width = BattalionCard.CARD_WIDTH
        card_height = BattalionCard.CARD_HEIGHT
        num_cards = len(hand)

        total_width = card_width + (num_cards - 1) * (card_width - HAND_CARD_OVERLAP)
        start_x = SCREEN_WIDTH // 2 - total_width // 2
        base_y = SCREEN_HEIGHT - card_height + HAND_Y_OFFSET

        # Determine hovered card (check from right to left)
        mouse_pos = pygame.mouse.get_pos()
        hovered_index = None
        for i in range(num_cards - 1, -1, -1):
            x = start_x + i * (card_width - HAND_CARD_OVERLAP)
            card_rect = pygame.Rect(
                x,
                base_y - HAND_HOVER_POP_DISTANCE,
                card_width,
                card_height + HAND_HOVER_POP_DISTANCE,
            )
            if card_rect.collidepoint(mouse_pos):
                hovered_index = i
                break

        # Draw cards (hovered card last for z-order)
        draw_order = list(range(num_cards))
        if hovered_index is not None:
            draw_order.remove(hovered_index)
            draw_order.append(hovered_index)

        for i in draw_order:
            card = hand[i]

            if self.phase == GamePhase.DEALING and card not in arrived_cards:
                continue
            if self.dragging and i == self.selected_card_index:
                continue

            x = start_x + i * (card_width - HAND_CARD_OVERLAP)

            center_index = (num_cards - 1) / 2
            offset_from_center = i - center_index
            rotation = (
                (offset_from_center / max(1, num_cards - 1)) * HAND_FAN_SPREAD
                if num_cards > 1
                else 0
            )

            is_hovered = i == hovered_index
            is_selected = i == self.selected_card_index

            if is_hovered or is_selected:
                draw_y = base_y - HAND_HOVER_POP_DISTANCE
                scale = HAND_HOVER_SCALE
                rotation = 0
            else:
                draw_y = base_y
                scale = 1.0

            BattalionCard.render(
                screen,
                card,
                x,
                draw_y,
                is_interviewed=card.is_collected,
                is_selected=is_selected,
                is_hovered=is_hovered,
                rotation=rotation,
                scale=scale,
            )

    # ------------------------------------------------------------------
    # Event handling
    # ------------------------------------------------------------------

    def handle_event(self, event: pygame.event.Event) -> None:
        """Handle pygame events."""
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
        """Handle clicking on a card in hand (fan layout)."""
        hand = self.human_player.hand
        if not hand:
            return

        card_width = BattalionCard.CARD_WIDTH
        card_height = BattalionCard.CARD_HEIGHT
        num_cards = len(hand)

        total_width = card_width + (num_cards - 1) * (card_width - HAND_CARD_OVERLAP)
        start_x = SCREEN_WIDTH // 2 - total_width // 2
        base_y = SCREEN_HEIGHT - card_height + HAND_Y_OFFSET

        for i in range(num_cards - 1, -1, -1):
            x = start_x + i * (card_width - HAND_CARD_OVERLAP)
            card_rect = pygame.Rect(
                x,
                base_y - HAND_HOVER_POP_DISTANCE,
                card_width,
                card_height + HAND_HOVER_POP_DISTANCE,
            )

            if card_rect.collidepoint(pos):
                if self.selected_card_index == i:
                    self._confirm_card_selection()
                else:
                    self.selected_card_index = i
                break

    # ------------------------------------------------------------------
    # Card selection / AI / placement
    # ------------------------------------------------------------------

    def _confirm_card_selection(self) -> None:
        """Confirm card selection and proceed to AI phase."""
        if self.selected_card_index is None:
            return

        card = self.human_player.hand[self.selected_card_index]
        self.human_player.select_card(card)
        self.selected_card_index = None

        self.phase = GamePhase.AI_THINKING
        self.phase_timer = AI_THINKING_DURATION
        self.message = "AI가 카드를 선택 중..."
        self.message_timer = AI_THINKING_DURATION

    def _ai_select_cards(self) -> None:
        """Have all AI players select cards."""
        for ai in self.ai_controllers:
            if not ai.player.is_eliminated:
                ai.select_card(self.rules.board)

        play_order = self.rules.prepare_turn()
        self.placement_queue = [
            (player, card, idx + 1) for idx, (player, card) in enumerate(play_order)
        ]
        self.turn_log.clear()
        self._start_next_placement()

    def _start_next_placement(self) -> None:
        """Execute and animate the next player's card placement."""
        if not self.placement_queue:
            self.rules.check_round_end()
            self._finish_turn()
            return

        player, card, order_idx = self.placement_queue.pop(0)
        result = self.rules.execute_single_placement(player, card, order_idx)
        self.turn_log.append(result)
        self.current_placement = result

        self.message = f"{result.player.name}: #{result.card.number}"
        self.message_timer = 1.0

        if result.result.penalty_score > 0:
            self.phase = GamePhase.PENALTY_ANIMATION
            self._start_penalty_animation(result)
        else:
            self.phase = GamePhase.PLACING_PLAYER
            self.phase_timer = PLACEMENT_PAUSE_DURATION

    def _start_penalty_animation(self, result: TurnResult) -> None:
        """Start animation of penalty cards moving to hangar or player."""
        self.penalty_cards_animating.clear()
        self.penalty_tweens = TweenGroup()

        taken_cards = result.result.penalty_cards

        if result.player == self.human_player:
            target_x, target_y = 180, 40
        else:
            player_idx = self.players.index(result.player) - 1
            target_x = SCREEN_WIDTH - 60
            target_y = 90 + player_idx * 60

        for i, card in enumerate(taken_cards):
            tween = Tween(
                start=(BOARD_OFFSET_X, BOARD_OFFSET_Y + 50),
                end=(target_x, target_y),
                duration=0.4 + i * 0.1,
                easing="ease_in",
            )
            self.penalty_cards_animating.append((card, tween))
            self.penalty_tweens.add(tween)

        if taken_cards and result.player == self.human_player:
            self.commander.say_penalty_taken()

    def _finish_turn(self) -> None:
        """Finish the turn after all placements are animated."""
        has_penalties = any(r.result.penalty_score > 0 for r in self.turn_log)
        self.message = "배치 및 벌점 부여 완료!" if has_penalties else "카드 배치 완료!"
        self.message_timer = 1.0

        if self.rules.is_round_over():
            self.phase = GamePhase.ROUND_END
            self.phase_timer = 1.0
            self.message = "라운드 종료! 잠시 후 정산..."
        else:
            self.selected_card_index = None
            self.turn_timer = TURN_TIMEOUT_SECONDS
            self.phase = GamePhase.SELECTING

    def _auto_select_card(self) -> None:
        """Auto-select a random card when timer runs out."""
        hand = self.human_player.hand
        if hand:
            card = random.choice(hand)
            self.human_player.select_card(card)
            self.message = "시간 초과! 자동 선택됨"
            self.message_timer = 1.0
            self.phase = GamePhase.AI_THINKING
            self.phase_timer = 0.3

    def _go_to_result_scene(self) -> None:
        """Navigate to ResultScene for round settlement."""
        from fall_in.core.game_manager import GameManager
        from fall_in.scenes.result_scene import ResultScene

        GameManager().change_scene(ResultScene(self.rules, self.players))

    # ------------------------------------------------------------------
    # Update / Render
    # ------------------------------------------------------------------

    def update(self, dt: float) -> None:
        """Update scene state."""
        if self.message_timer > 0:
            self.message_timer -= dt

        # Screen shake
        if self.screen_shake_timer > 0:
            self.screen_shake_timer -= dt
            intensity = self.screen_shake_intensity
            self.screen_shake_offset = (
                random.randint(-intensity, intensity),
                random.randint(-intensity, intensity),
            )
            if self.screen_shake_timer <= 0:
                self.screen_shake_offset = (0, 0)

        # Dust particles
        self.dust_effect.update(dt)

        # Update soldier figures and trigger effects
        board = self.rules.board
        for row_idx in range(NUM_ROWS):
            for col in range(len(board.rows[row_idx])):
                card = board.rows[row_idx][col]
                if card.number in self.soldier_figures:
                    figure = self.soldier_figures[card.number]
                    spawn_dust, trigger_shake = figure.update(dt)

                    if spawn_dust or trigger_shake:
                        visual_col = MAX_CARDS_PER_ROW - col
                        iso_x, iso_y = self._cart_to_iso(visual_col, row_idx)

                        if spawn_dust:
                            self.dust_effect.spawn(
                                iso_x, iso_y, figure.get_dust_count()
                            )
                        if trigger_shake:
                            self.screen_shake_intensity = figure.get_shake_intensity()
                            self.screen_shake_timer = SCREEN_SHAKE_DURATION

        # Dealing animation
        if self.phase == GamePhase.DEALING:
            self._update_dealing_animation(dt)
            self.commander.update(dt)
            return

        # Turn timer during selection
        if self.phase == GamePhase.SELECTING:
            self.turn_timer -= dt
            if self.turn_timer <= 0:
                self._auto_select_card()
                return

        # Commander expression
        committed = self.rules.get_player_committed_score(self.human_player)
        self.commander.set_expression_from_danger(committed)
        self.commander.update(dt)

        # Penalty animations
        if self.phase == GamePhase.PENALTY_ANIMATION:
            if self.penalty_tweens.update(dt):
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
        """Render scene to screen."""
        shake_x, shake_y = self.screen_shake_offset

        # Background (with shake + padding offset)
        screen.blit(
            self.background_image,
            (shake_x - SCREEN_SHAKE_PADDING, shake_y - SCREEN_SHAKE_PADDING),
        )

        self._draw_board(screen)
        self.dust_effect.render(screen, self.screen_shake_offset)
        self.commander.render(screen)
        self._draw_ui(screen)
        self._draw_hand(screen)

        # Dealing animation
        if self.phase == GamePhase.DEALING:
            self._draw_dealing_animation(screen)
            hint = get_font(18).render("카드 배급 중...", True, AIR_FORCE_BLUE)
            screen.blit(
                hint, (SCREEN_WIDTH // 2 - hint.get_width() // 2, SCREEN_HEIGHT - 50)
            )

        # Penalty card animations
        self._draw_penalty_animation(screen)

        # Timer & hint during selection
        if self.phase == GamePhase.SELECTING:
            self._draw_turn_timer(screen)
            hint = get_font(14).render(
                "카드를 클릭하여 선택, 다시 클릭 또는 [SPACE]로 확정",
                True,
                AIR_FORCE_BLUE,
            )
            screen.blit(
                hint, (SCREEN_WIDTH // 2 - hint.get_width() // 2, SCREEN_HEIGHT - 18)
            )

    def _draw_turn_timer(self, screen: pygame.Surface) -> None:
        """Draw the turn timer with color-coded urgency."""
        timer_font = get_font(28, "bold")
        seconds = max(0, int(self.turn_timer))

        if seconds > TIMER_WARNING_THRESHOLD:
            color = WHITE
        elif seconds > TIMER_DANGER_THRESHOLD:
            color = DANGER_WARNING
        else:
            color = DANGER_DANGER

        draw_outlined_text(
            screen, f"{seconds}s", timer_font, (230, 20), color, TOP_BAR_OUTLINE_COLOR
        )

    def _draw_dealing_animation(self, screen: pygame.Surface) -> None:
        """Draw cards flying from barracks to hand positions."""
        for card, tween in self.dealing_cards:
            if not tween.is_started or tween.is_complete:
                continue

            pos = tween.get_current_int()
            card_w, card_h = 50, 70
            card_rect = pygame.Rect(
                pos[0] - card_w // 2, pos[1] - card_h // 2, card_w, card_h  # type: ignore
            )

            pygame.draw.rect(screen, DEALING_CARD_COLOR, card_rect, border_radius=5)
            pygame.draw.rect(
                screen, DEALING_CARD_BORDER_COLOR, card_rect, width=2, border_radius=5
            )

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
        """Draw penalty cards shrinking and moving toward hangar/player."""
        for card, tween in self.penalty_cards_animating:
            if tween.is_complete:
                continue

            pos = tween.get_current_int()
            progress = tween.get_progress()

            scale = 1.0 - progress * 0.7
            card_w = int(40 * scale)
            card_h = int(55 * scale)

            if card_w > 5 and card_h > 5:
                card_rect = pygame.Rect(
                    pos[0] - card_w // 2, pos[1] - card_h // 2, card_w, card_h  # type: ignore
                )

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

                if scale > 0.5:
                    num_font = get_font(int(12 * scale))
                    num_text = num_font.render(str(card.number), True, WHITE)
                    screen.blit(num_text, num_text.get_rect(center=card_rect.center))
