"""
Prestige Scene - Prestige/rebirth confirmation screen

TODO : add story line animation or cutscene at Prestige ending.
"""

import pygame

from fall_in.scenes.base_scene import Scene
from fall_in.ui.button import Button
from fall_in.utils.asset_loader import get_font
from fall_in.core.prestige_manager import PrestigeManager
from fall_in.config import (
    SCREEN_WIDTH,
    SCREEN_HEIGHT,
    AIR_FORCE_BLUE,
    WHITE,
    DANGER_DANGER,
    DANGER_WARNING,
)


class PrestigePhase:
    """Phases of the prestige scene"""

    CUTSCENE = "cutscene"
    WARNING = "warning"
    CONFIRM = "confirm"
    FADEOUT = "fadeout"


class PrestigeScene(Scene):
    """
    Prestige (rebirth) confirmation screen.
    Accessible after achieving the coup ending via the 're-enlist' button.
    Displays data reset warnings before executing prestige.
    """

    def __init__(self):
        super().__init__()
        self.phase = PrestigePhase.CUTSCENE
        self.phase_timer = 0.0
        self.fade_alpha = 0
        self.buttons: list[Button] = []
        self.prestige_manager = PrestigeManager()
        self.current_prestige = self.prestige_manager.get_prestige_count()

    def _setup_confirm_buttons(self) -> None:
        """Setup confirmation buttons."""
        self.buttons.clear()

        button_width = 150
        button_height = 50
        button_y = SCREEN_HEIGHT - 150

        # Yes button
        self.buttons.append(
            Button(
                x=SCREEN_WIDTH // 2 - button_width - 30,
                y=button_y,
                width=button_width,
                height=button_height,
                text="예",
                callback=self._on_confirm_yes,
            )
        )

        # No button
        self.buttons.append(
            Button(
                x=SCREEN_WIDTH // 2 + 30,
                y=button_y,
                width=button_width,
                height=button_height,
                text="아니오",
                callback=self._on_confirm_no,
            )
        )

    def _on_confirm_yes(self) -> None:
        """Confirm prestige - execute rebirth."""
        self.phase = PrestigePhase.FADEOUT
        self.phase_timer = 0.0

    def _on_confirm_no(self) -> None:
        """Cancel prestige - return to title."""
        self._return_to_title()

    def _return_to_title(self) -> None:
        """Return to title screen."""
        from fall_in.core.game_manager import GameManager, GameState
        from fall_in.scenes.title_scene import TitleScene

        game = GameManager()
        game.state = GameState.TITLE
        game.change_scene(TitleScene())

    def _execute_prestige(self) -> None:
        """Execute prestige and return to title."""
        success = self.prestige_manager.execute_prestige()
        if success:
            # Reload game manager state
            from fall_in.core.game_manager import GameManager

            GameManager().load_currency()

        self._return_to_title()

    def handle_event(self, event: pygame.event.Event) -> None:
        """Handle events."""
        for button in self.buttons:
            button.handle_event(event)

        if event.type == pygame.KEYDOWN:
            if self.phase == PrestigePhase.CUTSCENE:
                # Skip cutscene
                self.phase = PrestigePhase.WARNING
                self.phase_timer = 0.0
            elif self.phase == PrestigePhase.WARNING:
                # Skip to confirm
                self.phase = PrestigePhase.CONFIRM
                self._setup_confirm_buttons()
            elif event.key == pygame.K_ESCAPE:
                self._on_confirm_no()

        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.phase == PrestigePhase.CUTSCENE:
                self.phase = PrestigePhase.WARNING
                self.phase_timer = 0.0
            elif self.phase == PrestigePhase.WARNING:
                self.phase = PrestigePhase.CONFIRM
                self._setup_confirm_buttons()

    def update(self, dt: float) -> None:
        """Update scene."""
        self.phase_timer += dt

        for button in self.buttons:
            button.update(dt)

        # Auto-advance phases
        if self.phase == PrestigePhase.CUTSCENE and self.phase_timer > 5.0:
            self.phase = PrestigePhase.WARNING
            self.phase_timer = 0.0

        elif self.phase == PrestigePhase.WARNING and self.phase_timer > 4.0:
            self.phase = PrestigePhase.CONFIRM
            self._setup_confirm_buttons()

        elif self.phase == PrestigePhase.FADEOUT:
            self.fade_alpha = min(255, self.fade_alpha + int(dt * 200))
            if self.fade_alpha >= 255 and self.phase_timer > 1.5:
                self._execute_prestige()

    def render(self, screen: pygame.Surface) -> None:
        """Render prestige scene."""
        # Dark background
        screen.fill((20, 20, 30))

        if self.phase == PrestigePhase.CUTSCENE:
            self._render_cutscene(screen)
        elif self.phase == PrestigePhase.WARNING:
            self._render_warning(screen)
        elif self.phase == PrestigePhase.CONFIRM:
            self._render_confirm(screen)

        # Fade overlay
        if self.phase == PrestigePhase.FADEOUT:
            fade_surface = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT))
            fade_surface.fill((0, 0, 0))
            fade_surface.set_alpha(self.fade_alpha)
            screen.blit(fade_surface, (0, 0))

            if self.fade_alpha > 200:
                font = get_font(24)
                text = font.render("재입대 중...", True, WHITE)
                rect = text.get_rect(center=(SCREEN_WIDTH // 2, SCREEN_HEIGHT // 2))
                screen.blit(text, rect)

    def _render_cutscene(self, screen: pygame.Surface) -> None:
        """Render cutscene phase."""
        title_font = get_font(36, "bold")
        font = get_font(22)
        small_font = get_font(16)

        # Title
        title = title_font.render("쿠테타 이후...", True, DANGER_DANGER)
        title_rect = title.get_rect(center=(SCREEN_WIDTH // 2, 100))
        screen.blit(title, title_rect)

        # Cutscene text (appears gradually based on timer)
        lines = [
            "모든 것이 무너졌다.",
            "중대장은 해임되고, 부대는 혼란에 빠졌다.",
            "하지만 당신은... 다시 시작할 수 있다.",
            "",
            "처음부터, 모든 것을 다시.",
        ]

        y = 200
        for i, line in enumerate(lines):
            if self.phase_timer > i * 0.8:
                alpha = min(255, int((self.phase_timer - i * 0.8) * 200))
                line_surface = font.render(line, True, WHITE)
                line_surface.set_alpha(alpha)
                line_rect = line_surface.get_rect(center=(SCREEN_WIDTH // 2, y))
                screen.blit(line_surface, line_rect)
            y += 50

        # Skip hint
        hint = small_font.render("[아무 키나 눌러 계속]", True, AIR_FORCE_BLUE)
        hint_rect = hint.get_rect(center=(SCREEN_WIDTH // 2, SCREEN_HEIGHT - 50))
        screen.blit(hint, hint_rect)

    def _render_warning(self, screen: pygame.Surface) -> None:
        """Render warning phase."""
        title_font = get_font(32, "bold")
        font = get_font(20)
        small_font = get_font(16)

        # Warning title
        title = title_font.render("⚠ 경고: 데이터 리셋", True, DANGER_WARNING)
        title_rect = title.get_rect(center=(SCREEN_WIDTH // 2, 100))
        screen.blit(title, title_rect)

        # Warning messages
        warnings = [
            "환생을 진행하면 다음 데이터가 초기화됩니다:",
            "",
            "• 보유 수당 (재화)",
            "• 면담한 병사 정보",
            "• 대부분의 훈장",
            "• 게임 통계",
            "",
            "다음 항목은 유지됩니다:",
            "",
            f"• 프레스티지 카운트 ({self.current_prestige} → {self.current_prestige + 1})",
            "• 쿠테타 달성 훈장",
            "• 프레스티지 아이콘 테두리",
            f"• 빼돌리기 슬롯 +1 (기본 {2 + self.current_prestige}개)",
        ]

        y = 160
        for line in warnings:
            color = (
                DANGER_DANGER
                if line.startswith("•") and "초기화" not in line
                else WHITE
            )
            if "유지" in line:
                color = (100, 200, 100)
            text = font.render(line, True, color)
            text_rect = text.get_rect(center=(SCREEN_WIDTH // 2, y))
            screen.blit(text, text_rect)
            y += 30

        # Skip hint
        hint = small_font.render("[아무 키나 눌러 계속]", True, AIR_FORCE_BLUE)
        hint_rect = hint.get_rect(center=(SCREEN_WIDTH // 2, SCREEN_HEIGHT - 50))
        screen.blit(hint, hint_rect)

    def _render_confirm(self, screen: pygame.Surface) -> None:
        """Render confirmation phase."""
        title_font = get_font(36, "bold")
        font = get_font(24)

        # Title
        title = title_font.render(
            "감나무에서 떨어진 채로 재입대하시겠습니까?", True, WHITE
        )
        title_rect = title.get_rect(center=(SCREEN_WIDTH // 2, 150))
        screen.blit(title, title_rect)

        # Subtitle
        subtitle = font.render("이 작업은 되돌릴 수 없습니다.", True, DANGER_WARNING)
        subtitle_rect = subtitle.get_rect(center=(SCREEN_WIDTH // 2, 220))
        screen.blit(subtitle, subtitle_rect)

        # Reward preview
        rewards_font = get_font(18)
        rewards_text = rewards_font.render(
            f"환생 보상: 프레스티지 Lv.{self.current_prestige + 1}, 빼돌리기 슬롯 +1",
            True,
            (100, 200, 100),
        )
        rewards_rect = rewards_text.get_rect(center=(SCREEN_WIDTH // 2, 280))
        screen.blit(rewards_text, rewards_rect)

        # Buttons
        for button in self.buttons:
            button.render(screen)
