"""
Result Scene - Round settlement screen showing penalties and scores
"""

import pygame

from fall_in.scenes.base_scene import Scene
from fall_in.ui.button import Button
from fall_in.utils.asset_loader import get_font
from fall_in.utils.danger_utils import get_danger_color
from fall_in.core.player import Player
from fall_in.core.rules import GameRules
from fall_in.config import (
    SCREEN_WIDTH,
    SCREEN_HEIGHT,
    AIR_FORCE_BLUE,
    DANGER_SAFE,
    DANGER_WARNING,
    DANGER_DANGER,
    GAME_OVER_SCORE,
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

        # Calculate scores
        self.round_results = rules.commit_round_scores()

        # Check for eliminations
        self.eliminated_players = [p for p in players if p.is_eliminated]
        self.game_over = rules.game_over
        self.winner = rules.winner

        # Buttons
        self.buttons: list[Button] = []
        self._setup_buttons()

    def _setup_buttons(self) -> None:
        """Setup continue/title buttons"""
        button_width = 200
        button_height = 50
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

    def _continue_game(self) -> None:
        """Continue to next round"""
        from fall_in.core.game_manager import GameManager
        from fall_in.scenes.game_scene import GameScene

        # Create new game scene with same rules
        game_scene = GameScene(rules=self.rules)
        GameManager().change_scene(game_scene)

    def _go_to_game_over(self) -> None:
        """Go to game over scene"""
        from fall_in.core.game_manager import GameManager
        from fall_in.scenes.game_over_scene import GameOverScene

        game_over_scene = GameOverScene(
            winner=self.winner, players=self.players, round_number=self.round_number
        )
        GameManager().change_scene(game_over_scene)

    def handle_event(self, event: pygame.event.Event) -> None:
        """Handle events"""
        for button in self.buttons:
            button.handle_event(event)

        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_SPACE or event.key == pygame.K_RETURN:
                if self.game_over:
                    self._go_to_game_over()
                else:
                    self._continue_game()

    def update(self, dt: float) -> None:
        """Update scene"""
        for button in self.buttons:
            button.update(dt)

    def render(self, screen: pygame.Surface) -> None:
        """Render result screen"""
        title_font = get_font(36, "bold")
        header_font = get_font(24, "bold")
        font = get_font(20)
        small_font = get_font(16)

        # Title
        title = title_font.render(
            f"라운드 {self.round_number} 정산", True, AIR_FORCE_BLUE
        )
        title_rect = title.get_rect(center=(SCREEN_WIDTH // 2, 50))
        screen.blit(title, title_rect)

        # Table header
        start_y = 120
        col_x = [150, 350, 500, 650]  # Name, Round penalty, Total, Status

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
        row_height = 60

        for player in self.players:
            player_id = player.player_id
            round_danger, total = self.round_results.get(player_id, (0, 0))

            # Highlight row if eliminated
            if player.is_eliminated:
                pygame.draw.rect(
                    screen,
                    (255, 200, 200),
                    (100, row_y - 5, SCREEN_WIDTH - 200, row_height - 10),
                    border_radius=5,
                )

            # Player name
            name_text = font.render(player.name, True, AIR_FORCE_BLUE)
            screen.blit(name_text, (col_x[0], row_y + 10))

            # Round penalty
            penalty_color = DANGER_DANGER if round_danger > 0 else DANGER_SAFE
            penalty_text = font.render(f"+{round_danger}", True, penalty_color)
            screen.blit(penalty_text, (col_x[1], row_y + 10))

            # Total score with gauge
            gauge_width = 100
            gauge_height = 20
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

            # Status
            if player.is_eliminated:
                status_text = font.render("탈락!", True, DANGER_DANGER)
            elif total >= 50:
                status_text = font.render("위험", True, DANGER_WARNING)
            else:
                status_text = font.render("생존", True, DANGER_SAFE)
            screen.blit(status_text, (col_x[3], row_y + 10))

            row_y += row_height

        # Game over message
        if self.game_over:
            msg_y = SCREEN_HEIGHT - 150
            if self.eliminated_players:
                msg = f"{', '.join(p.name for p in self.eliminated_players)} 탈락!"
            else:
                msg = "게임 종료!"

            msg_text = header_font.render(msg, True, DANGER_DANGER)
            msg_rect = msg_text.get_rect(center=(SCREEN_WIDTH // 2, msg_y))
            screen.blit(msg_text, msg_rect)

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
