"""
Result Scene - Round settlement screen showing penalties and scores.
"""

import pygame

from fall_in.scenes.base_scene import Scene
from fall_in.ui.button import Button
from fall_in.utils.asset_loader import get_font
from fall_in.utils.danger_utils import get_danger_color
from fall_in.core.card import Card
from fall_in.core.player import Player, PlayerType
from fall_in.core.rules import GameRules
from fall_in.config import (
    SCREEN_WIDTH,
    SCREEN_HEIGHT,
    AIR_FORCE_BLUE,
    WHITE,
    DANGER_SAFE,
    DANGER_WARNING,
    DANGER_DANGER,
    GAME_OVER_SCORE,
    DANGER_SCORE_THRESHOLDS,
    SCENE_BUTTON_WIDTH,
    SCENE_BUTTON_HEIGHT,
    RESULT_TABLE_ROW_HEIGHT,
    RESULT_TABLE_GAUGE_WIDTH,
    RESULT_TABLE_GAUGE_HEIGHT,
    RESULT_TABLE_BADGE_ICON_SIZE,
    RESULT_TABLE_START_Y,
)


class ResultScene(Scene):
    """
    Round result/settlement scene.
    Shows penalties earned this round and cumulative scores.
    """

    def __init__(self, rules: GameRules, players: list[Player]):
        super().__init__()
        self.rules = rules
        self.players = players
        self.round_number = rules.round_state.round_number

        # Track human player's penalty cards for smuggling
        self.human_player = next(
            (p for p in players if p.player_type == PlayerType.HUMAN), None
        )

        # Get penalty cards before committing scores
        self.human_penalty_cards: list[Card] = []
        if self.human_player:
            round_penalties = rules.get_round_penalties()
            human_penalty = round_penalties.get(self.human_player.player_id)
            if human_penalty:
                self.human_penalty_cards = list(human_penalty.cards_taken)

        # Calculate scores (this commits the penalties)
        self.round_results = rules.commit_round_scores()

        # Check for eliminations
        self.eliminated_players = [p for p in players if p.is_eliminated]
        self.game_over = rules.game_over
        self.winner = rules.winner

        # Buttons
        self.buttons: list[Button] = []
        self._setup_buttons()

        # UI images — pull from pre-loaded manifest cache
        from fall_in.utils.asset_manifest import AssetManifest

        self._ui_images: dict[str, pygame.Surface] = {}
        for category in ("panels", "icons"):
            self._ui_images.update(AssetManifest.get_loaded(category))

    def _setup_buttons(self) -> None:
        """Setup continue/title buttons."""
        button_width = SCENE_BUTTON_WIDTH
        button_height = SCENE_BUTTON_HEIGHT
        button_x = SCREEN_WIDTH // 2 - button_width // 2
        button_y = SCREEN_HEIGHT - 80

        if self.game_over:
            self.buttons.append(
                Button(
                    x=button_x,
                    y=button_y,
                    width=button_width,
                    height=button_height,
                    text="결과 확인",
                    callback=self._go_to_game_over,
                )
            )
        else:
            self.buttons.append(
                Button(
                    x=button_x,
                    y=button_y,
                    width=button_width,
                    height=button_height,
                    text="다음 라운드",
                    callback=self._continue_game,
                )
            )

    # ------------------------------------------------------------------
    # Navigation helpers (shared smuggling check logic)
    # ------------------------------------------------------------------

    def _get_collected_penalty_cards(self) -> list[Card]:
        """Filter penalty cards to only collected (interviewed) soldiers."""
        from fall_in.core.smuggling_manager import SmugglingManager

        smuggling = SmugglingManager()
        smuggling.update_max_count()
        return [
            card
            for card in self.human_penalty_cards
            if smuggling.is_soldier_collected(card.number)
        ]

    def _navigate_via_smuggling_or_direct(self, *, is_game_over: bool) -> None:
        """
        Navigate to smuggling scene if there are collected penalty cards,
        otherwise go directly to the next scene.

        Args:
            is_game_over: If True, the destination after smuggling is GameOverScene.
        """
        from fall_in.core.game_manager import GameManager

        collected_penalty_cards = self._get_collected_penalty_cards()

        if collected_penalty_cards:
            from fall_in.scenes.smuggling_scene import SmugglingScene

            round_penalty = (
                self.round_results.get(self.human_player.player_id, (0, 0))[0]
                if self.human_player
                else 0
            )
            smuggling_scene = SmugglingScene(
                rules=self.rules,
                penalty_cards=collected_penalty_cards,
                round_penalty=round_penalty,
                is_game_over=is_game_over,
            )
            GameManager().change_scene(smuggling_scene)
        elif is_game_over:
            from fall_in.scenes.game_over_scene import GameOverScene

            GameManager().change_scene(
                GameOverScene(
                    winner=self.winner,
                    players=self.players,
                    round_number=self.round_number,
                )
            )
        else:
            from fall_in.scenes.game_scene import GameScene

            GameManager().change_scene(GameScene(rules=self.rules))

    def _continue_game(self) -> None:
        """Continue to next round (optionally via smuggling)."""
        self._navigate_via_smuggling_or_direct(is_game_over=False)

    def _go_to_game_over(self) -> None:
        """Go to game over scene (optionally via smuggling)."""
        self._navigate_via_smuggling_or_direct(is_game_over=True)

    # ------------------------------------------------------------------
    # Event / Update / Render
    # ------------------------------------------------------------------

    def handle_event(self, event: pygame.event.Event) -> None:
        """Handle events."""
        for button in self.buttons:
            button.handle_event(event)

        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_SPACE or event.key == pygame.K_RETURN:
                if self.game_over:
                    self._go_to_game_over()
                else:
                    self._continue_game()

    def update(self, dt: float) -> None:
        """Update scene."""
        for button in self.buttons:
            button.update(dt)

    def render(self, screen: pygame.Surface) -> None:
        """Render result screen."""
        title_font = get_font(36, "bold")
        header_font = get_font(24, "bold")
        font = get_font(20)
        small_font = get_font(16)

        # Result table background panel
        table_rect = pygame.Rect(0, 0, SCREEN_WIDTH, SCREEN_HEIGHT)
        if "panel_result_table" in self._ui_images:
            raw = self._ui_images["panel_result_table"]
            img_w, img_h = raw.get_size()
            # Scale to fill screen width while preserving aspect ratio
            scale = SCREEN_WIDTH / img_w
            scaled_w = SCREEN_WIDTH
            scaled_h = int(img_h * scale)
            # If height exceeds screen, scale by height instead
            if scaled_h > SCREEN_HEIGHT:
                scale = SCREEN_HEIGHT / img_h
                scaled_w = int(img_w * scale)
                scaled_h = SCREEN_HEIGHT
            table_bg = pygame.transform.smoothscale(raw, (scaled_w, scaled_h))
            # Center on screen
            bg_x = (SCREEN_WIDTH - scaled_w) // 2
            bg_y = (SCREEN_HEIGHT - scaled_h) // 2
            screen.blit(table_bg, (bg_x, bg_y))
        else:
            pygame.draw.rect(screen, WHITE, table_rect, border_radius=12)
            pygame.draw.rect(
                screen, AIR_FORCE_BLUE, table_rect, width=2, border_radius=12
            )

        # Title
        title = title_font.render(
            f"라운드 {self.round_number} 정산", True, AIR_FORCE_BLUE
        )
        title_rect = title.get_rect(center=(SCREEN_WIDTH // 2, 50))
        screen.blit(title, title_rect)

        # Table header
        start_y = RESULT_TABLE_START_Y
        col_x = [150, 350, 500, 680]

        headers = ["플레이어", "이번 라운드", "누적 위험도", "상태"]
        for i, header in enumerate(headers):
            text = header_font.render(header, True, AIR_FORCE_BLUE)
            screen.blit(text, (col_x[i], start_y))

        # Divider
        pygame.draw.line(
            screen,
            AIR_FORCE_BLUE,
            (100, start_y + 35),
            (SCREEN_WIDTH - 100, start_y + 35),
            2,
        )

        # Player rows
        row_y = start_y + 50
        row_height = RESULT_TABLE_ROW_HEIGHT

        for player in self.players:
            player_id = player.player_id
            round_danger, total = self.round_results.get(player_id, (0, 0))

            if player.is_eliminated:
                pygame.draw.rect(
                    screen,
                    (255, 200, 200),
                    (100, row_y - 5, SCREEN_WIDTH - 200, row_height - 10),
                    border_radius=5,
                )

            # Player name
            screen.blit(
                font.render(player.name, True, AIR_FORCE_BLUE), (col_x[0], row_y + 10)
            )

            # Round penalty
            penalty_color = DANGER_DANGER if round_danger > 0 else DANGER_SAFE
            screen.blit(
                font.render(f"+{round_danger}", True, penalty_color),
                (col_x[1], row_y + 10),
            )

            # Total score with gauge
            gauge_width = RESULT_TABLE_GAUGE_WIDTH
            gauge_height = RESULT_TABLE_GAUGE_HEIGHT
            fill_ratio = min(total / GAME_OVER_SCORE, 1.0)
            fill_color = get_danger_color(total)

            pygame.draw.rect(
                screen,
                (200, 200, 200),
                (col_x[2], row_y + 12, gauge_width, gauge_height),
                border_radius=3,
            )
            if fill_ratio > 0:
                pygame.draw.rect(
                    screen,
                    fill_color,
                    (col_x[2], row_y + 12, int(gauge_width * fill_ratio), gauge_height),
                    border_radius=3,
                )
            pygame.draw.rect(
                screen,
                AIR_FORCE_BLUE,
                (col_x[2], row_y + 12, gauge_width, gauge_height),
                width=1,
                border_radius=3,
            )

            total_text = small_font.render(
                f"{total}/{GAME_OVER_SCORE}", True, AIR_FORCE_BLUE
            )
            screen.blit(total_text, (col_x[2] + gauge_width + 10, row_y + 12))

            # Status with badge icons
            if player.is_eliminated:
                badge_key = "badge_eliminated"
                status_text = font.render("탈락!", True, DANGER_DANGER)
            elif total >= DANGER_SCORE_THRESHOLDS["danger"]:
                badge_key = "badge_danger"
                status_text = font.render("위험", True, DANGER_WARNING)
            else:
                badge_key = "badge_survived"
                status_text = font.render("생존", True, DANGER_SAFE)

            if badge_key in self._ui_images:
                raw_icon = self._ui_images[badge_key]
                icon_h = RESULT_TABLE_BADGE_ICON_SIZE
                aspect = raw_icon.get_width() / max(raw_icon.get_height(), 1)
                icon_w = int(icon_h * aspect)
                badge_icon = pygame.transform.smoothscale(raw_icon, (icon_w, icon_h))
                screen.blit(badge_icon, (col_x[3], row_y + 8))
            else:
                screen.blit(status_text, (col_x[3], row_y + 10))

            row_y += row_height

        # Game over message
        if self.game_over:
            msg_y = SCREEN_HEIGHT - 150
            if self.eliminated_players:
                msg = f"{', '.join(p.name for p in self.eliminated_players)} 탈락!"
            else:
                msg = "게임 종료!"

            # Popup background
            msg_text = header_font.render(msg, True, DANGER_DANGER)
            popup_w = msg_text.get_width() + 40
            popup_h = 50
            popup_rect = pygame.Rect(
                SCREEN_WIDTH // 2 - popup_w // 2,
                msg_y - popup_h // 2,
                popup_w,
                popup_h,
            )
            if "popup_message" in self._ui_images:
                popup_bg = pygame.transform.smoothscale(
                    self._ui_images["popup_message"],
                    (popup_rect.width, popup_rect.height),
                )
                screen.blit(popup_bg, popup_rect.topleft)
            else:
                pygame.draw.rect(screen, (255, 240, 240), popup_rect, border_radius=8)
                pygame.draw.rect(
                    screen, DANGER_DANGER, popup_rect, width=2, border_radius=8
                )
            screen.blit(msg_text, msg_text.get_rect(center=popup_rect.center))

        # Buttons
        for button in self.buttons:
            button.render(screen)

        # Hint
        hint_text = small_font.render(
            "[SPACE] 또는 버튼 클릭으로 계속", True, AIR_FORCE_BLUE
        )
        screen.blit(
            hint_text,
            (SCREEN_WIDTH // 2 - hint_text.get_width() // 2, SCREEN_HEIGHT - 30),
        )
