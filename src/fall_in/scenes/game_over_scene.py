"""
Game Over Scene - Shows final results and rewards
"""

import pygame
from typing import Optional

from fall_in.scenes.base_scene import Scene
from fall_in.ui.button import Button
from fall_in.utils.asset_loader import get_font
from fall_in.core.player import Player, PlayerType
from fall_in.config import (
    SCREEN_WIDTH,
    SCREEN_HEIGHT,
    AIR_FORCE_BLUE,
    WHITE,
    LIGHT_BLUE,
    DANGER_SAFE,
    DANGER_DANGER,
)


class GameOverScene(Scene):
    """
    Game over scene showing final results and currency rewards.
    """

    def __init__(
        self, winner: Optional[Player], players: list[Player], round_number: int
    ):
        super().__init__()
        self.winner = winner
        self.players = players
        self.round_number = round_number

        # Find human player
        self.human_player = next(
            p for p in players if p.player_type == PlayerType.HUMAN
        )
        self.is_victory = (winner == self.human_player) if winner else False

        # Calculate rewards
        self.reward = self._calculate_reward()

        # Apply reward
        from fall_in.core.game_manager import GameManager

        GameManager().add_currency(self.reward)

        # Buttons
        self.buttons: list[Button] = []
        self._setup_buttons()

    def _calculate_reward(self) -> int:
        """
        Calculate currency reward based on result.

        Victory: 100 base + 10 per round
        Defeat: 30 base + 5 per survival round
        """
        if self.is_victory:
            return 100 + (self.round_number * 10)
        else:
            return 30 + (self.round_number * 5)

    def _setup_buttons(self) -> None:
        """Setup return button"""
        button_width = 200
        button_height = 50
        button_x = SCREEN_WIDTH // 2 - button_width // 2
        button_y = SCREEN_HEIGHT - 100

        self.buttons.append(
            Button(
                x=button_x,
                y=button_y,
                width=button_width,
                height=button_height,
                text="타이틀로",
                callback=self._return_to_title,
            )
        )

    def _return_to_title(self) -> None:
        """Return to title screen"""
        from fall_in.core.game_manager import GameManager, GameState
        from fall_in.scenes.title_scene import TitleScene

        game = GameManager()
        game.state = GameState.TITLE
        game.change_scene(TitleScene())

    def handle_event(self, event: pygame.event.Event) -> None:
        """Handle events"""
        for button in self.buttons:
            button.handle_event(event)

        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_SPACE or event.key == pygame.K_RETURN:
                self._return_to_title()

    def update(self, dt: float) -> None:
        """Update scene"""
        for button in self.buttons:
            button.update(dt)

    def render(self, screen: pygame.Surface) -> None:
        """Render game over screen"""
        title_font = get_font(48, "bold")
        header_font = get_font(28, "bold")
        font = get_font(22)
        small_font = get_font(16)

        # Result title
        if self.is_victory:
            title = "승리!"
            title_color = DANGER_SAFE
        else:
            title = "패배..."
            title_color = DANGER_DANGER

        title_text = title_font.render(title, True, title_color)
        title_rect = title_text.get_rect(center=(SCREEN_WIDTH // 2, 100))
        screen.blit(title_text, title_rect)

        # Subtitle
        if self.winner:
            subtitle = f"최종 승자: {self.winner.name}"
        else:
            subtitle = "모든 플레이어 탈락"
        subtitle_text = header_font.render(subtitle, True, AIR_FORCE_BLUE)
        subtitle_rect = subtitle_text.get_rect(center=(SCREEN_WIDTH // 2, 160))
        screen.blit(subtitle_text, subtitle_rect)

        # Stats box
        stats_rect = pygame.Rect(SCREEN_WIDTH // 2 - 200, 220, 400, 200)
        pygame.draw.rect(screen, WHITE, stats_rect, border_radius=10)
        pygame.draw.rect(screen, AIR_FORCE_BLUE, stats_rect, width=2, border_radius=10)

        # Stats content
        stats_y = stats_rect.y + 20

        round_text = font.render(
            f"진행 라운드: {self.round_number}", True, AIR_FORCE_BLUE
        )
        screen.blit(round_text, (stats_rect.x + 30, stats_y))

        score_text = font.render(
            f"최종 위험도: {self.human_player.penalty_score}", True, AIR_FORCE_BLUE
        )
        screen.blit(score_text, (stats_rect.x + 30, stats_y + 40))

        # Divider
        pygame.draw.line(
            screen,
            LIGHT_BLUE,
            (stats_rect.x + 30, stats_y + 90),
            (stats_rect.x + stats_rect.width - 30, stats_y + 90),
            1,
        )

        # Reward section
        reward_label = font.render("획득 수당:", True, AIR_FORCE_BLUE)
        screen.blit(reward_label, (stats_rect.x + 30, stats_y + 110))

        reward_text = header_font.render(f"+{self.reward} 원", True, DANGER_SAFE)
        screen.blit(reward_text, (stats_rect.x + 150, stats_y + 105))

        # Total currency
        from fall_in.core.game_manager import GameManager

        total_currency = GameManager().currency

        total_text = small_font.render(
            f"총 보유 수당: {total_currency} 원", True, AIR_FORCE_BLUE
        )
        screen.blit(total_text, (stats_rect.x + 30, stats_y + 150))

        # Final rankings
        rankings_y = stats_rect.y + stats_rect.height + 30
        rankings_title = header_font.render("최종 순위", True, AIR_FORCE_BLUE)
        screen.blit(
            rankings_title,
            (SCREEN_WIDTH // 2 - rankings_title.get_width() // 2, rankings_y),
        )

        sorted_players = sorted(self.players, key=lambda p: p.penalty_score)
        for i, player in enumerate(sorted_players):
            rank_y = rankings_y + 40 + i * 30
            rank_text = font.render(
                f"{i + 1}. {player.name} - {player.penalty_score}점",
                True,
                AIR_FORCE_BLUE,
            )
            screen.blit(rank_text, (SCREEN_WIDTH // 2 - 100, rank_y))

        # Buttons
        for button in self.buttons:
            button.render(screen)

        # Hint
        hint_text = small_font.render("[SPACE] 또는 버튼 클릭", True, AIR_FORCE_BLUE)
        screen.blit(
            hint_text,
            (SCREEN_WIDTH // 2 - hint_text.get_width() // 2, SCREEN_HEIGHT - 40),
        )
