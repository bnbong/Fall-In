"""
Game Over Scene - Shows final results, currency rewards, and medals.

# TODO : add game over scene graphics.
"""

import json

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
    COUP_TITLE_COLOR,
    DATA_DIR,
    REWARD_VICTORY_BASE,
    REWARD_VICTORY_PER_ROUND,
    REWARD_DEFEAT_BASE,
    REWARD_DEFEAT_PER_ROUND,
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

        # Check for coup ending
        self.is_coup_ending = self._check_coup_ending()

        # Calculate and apply rewards
        self.reward = self._calculate_reward()

        from fall_in.core.game_manager import GameManager

        GameManager().add_currency(self.reward)
        self._award_medals()

        # If coup ending achieved, unlock prestige
        if self.is_coup_ending:
            from fall_in.core.prestige_manager import PrestigeManager

            PrestigeManager().unlock_coup()

        # Buttons
        self.buttons: list[Button] = []
        self._setup_buttons()

        # UI images — pull from pre-loaded manifest cache
        from fall_in.utils.asset_manifest import AssetManifest

        self._ui_images: dict[str, pygame.Surface] = {}
        for category in ("banners", "panels", "icons"):
            self._ui_images.update(AssetManifest.get_loaded(category))

    def _check_coup_ending(self) -> bool:
        """
        Check if coup ending condition is met.

        Requires:
        - Game over (player lost)
        - All soldiers collected (interviewed)
        - All coup soldiers smuggled (11, 22, 33, 44, 55, 66, 77, 88, 99)
        """
        if self.is_victory:
            return False

        from fall_in.core.medal_manager import MedalManager
        from fall_in.core.smuggling_manager import SmugglingManager

        return (
            MedalManager().has_all_soldiers_collected()
            and SmugglingManager().check_coup_condition()
        )

    def _award_medals(self) -> None:
        """Award medals based on game results."""
        from fall_in.core.medal_manager import MedalManager

        manager = MedalManager()
        self._update_player_stats()

        newly_awarded = manager.check_medal_conditions(
            event_type="coup_ending" if self.is_coup_ending else "game_end",
            win_count=self._get_win_count(),
            survived_rounds=self.round_number,
            final_danger=self.human_player.penalty_score,
            is_victory=self.is_victory,
        )
        self.new_medals = newly_awarded

    def _update_player_stats(self) -> None:
        """Update player statistics in player_data.json."""
        try:
            path = DATA_DIR / "player_data.json"
            data = {}
            if path.exists():
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)

            if self.is_victory:
                data["win_count"] = data.get("win_count", 0) + 1

            current_max = data.get("max_survived_rounds", 0)
            data["max_survived_rounds"] = max(current_max, self.round_number)

            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def _get_win_count(self) -> int:
        """Get total win count from player data."""
        try:
            path = DATA_DIR / "player_data.json"
            if path.exists():
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    return data.get("win_count", 0)
        except Exception:
            pass
        return 0

    def _calculate_reward(self) -> int:
        """
        Calculate currency reward based on result.

        Victory: base + per_round * rounds
        Defeat:  base + per_round * rounds
        """
        if self.is_victory:
            return REWARD_VICTORY_BASE + (self.round_number * REWARD_VICTORY_PER_ROUND)
        else:
            return REWARD_DEFEAT_BASE + (self.round_number * REWARD_DEFEAT_PER_ROUND)

    def _setup_buttons(self) -> None:
        """Setup return button."""
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
        """Return to title screen."""
        from fall_in.core.game_manager import GameManager, GameState
        from fall_in.scenes.title_scene import TitleScene

        game = GameManager()
        game.state = GameState.TITLE
        game.change_scene(TitleScene())

    def handle_event(self, event: pygame.event.Event) -> None:
        """Handle events."""
        for button in self.buttons:
            button.handle_event(event)

        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_SPACE or event.key == pygame.K_RETURN:
                self._return_to_title()

    def update(self, dt: float) -> None:
        """Update scene."""
        for button in self.buttons:
            button.update(dt)

    def render(self, screen: pygame.Surface) -> None:
        """Render game over screen."""
        title_font = get_font(48, "bold")
        header_font = get_font(28, "bold")
        font = get_font(22)
        small_font = get_font(16)

        # Result title
        if self.is_coup_ending:
            title = "🔥 쿠테타 성공! 🔥"
            title_color = COUP_TITLE_COLOR
            banner_key = "banner_coup"
        elif self.is_victory:
            title = "승리!"
            title_color = DANGER_SAFE
            banner_key = "banner_victory"
        else:
            title = "패배..."
            title_color = DANGER_DANGER
            banner_key = "banner_defeat"

        # Draw banner behind title
        if banner_key in self._ui_images:
            banner_img = self._ui_images[banner_key]
            banner_w = min(600, SCREEN_WIDTH - 100)
            aspect = banner_img.get_height() / banner_img.get_width()
            banner_h = int(banner_w * aspect)
            scaled_banner = pygame.transform.smoothscale(
                banner_img, (banner_w, banner_h)
            )
            screen.blit(
                scaled_banner, (SCREEN_WIDTH // 2 - banner_w // 2, 100 - banner_h // 2)
            )

        title_text = title_font.render(title, True, title_color)
        screen.blit(title_text, title_text.get_rect(center=(SCREEN_WIDTH // 2, 100)))

        # Subtitle
        subtitle = (
            f"최종 승자: {self.winner.name}" if self.winner else "모든 플레이어 탈락"
        )
        subtitle_text = header_font.render(subtitle, True, AIR_FORCE_BLUE)
        screen.blit(
            subtitle_text, subtitle_text.get_rect(center=(SCREEN_WIDTH // 2, 160))
        )

        # Stats box
        stats_rect = pygame.Rect(SCREEN_WIDTH // 2 - 200, 220, 400, 200)
        if "panel_stats_box" in self._ui_images:
            stats_img = pygame.transform.smoothscale(
                self._ui_images["panel_stats_box"],
                (stats_rect.width, stats_rect.height),
            )
            screen.blit(stats_img, stats_rect.topleft)
        else:
            pygame.draw.rect(screen, WHITE, stats_rect, border_radius=10)
            pygame.draw.rect(
                screen, AIR_FORCE_BLUE, stats_rect, width=2, border_radius=10
            )

        stats_y = stats_rect.y + 20
        screen.blit(
            font.render(f"진행 라운드: {self.round_number}", True, AIR_FORCE_BLUE),
            (stats_rect.x + 30, stats_y),
        )
        screen.blit(
            font.render(
                f"최종 위험도: {self.human_player.penalty_score}", True, AIR_FORCE_BLUE
            ),
            (stats_rect.x + 30, stats_y + 40),
        )

        # Divider
        pygame.draw.line(
            screen,
            LIGHT_BLUE,
            (stats_rect.x + 30, stats_y + 90),
            (stats_rect.x + stats_rect.width - 30, stats_y + 90),
            1,
        )

        # Reward section
        screen.blit(
            font.render("획득 수당:", True, AIR_FORCE_BLUE),
            (stats_rect.x + 30, stats_y + 110),
        )
        screen.blit(
            header_font.render(f"+{self.reward} 원", True, DANGER_SAFE),
            (stats_rect.x + 150, stats_y + 105),
        )

        # Total currency
        from fall_in.core.game_manager import GameManager

        total_currency = GameManager().currency
        screen.blit(
            small_font.render(
                f"총 보유 수당: {total_currency} 원", True, AIR_FORCE_BLUE
            ),
            (stats_rect.x + 30, stats_y + 150),
        )

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
            screen.blit(
                font.render(
                    f"{i + 1}. {player.name} - {player.penalty_score}점",
                    True,
                    AIR_FORCE_BLUE,
                ),
                (SCREEN_WIDTH // 2 - 100, rank_y),
            )

        # Buttons
        for button in self.buttons:
            button.render(screen)

        # Hint
        hint_text = small_font.render("[SPACE] 또는 버튼 클릭", True, AIR_FORCE_BLUE)
        screen.blit(
            hint_text,
            (SCREEN_WIDTH // 2 - hint_text.get_width() // 2, SCREEN_HEIGHT - 40),
        )
