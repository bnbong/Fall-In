"""
Debug Scene - Debug menu for testing game features
"""

import pygame

from typing import Callable

from fall_in.scenes.base_scene import Scene
from fall_in.ui.button import Button
from fall_in.utils.asset_loader import get_font
from fall_in.core.debug_manager import DebugManager
from fall_in.config import (
    SCREEN_WIDTH,
    SCREEN_HEIGHT,
    AIR_FORCE_BLUE,
    WHITE,
    DANGER_DANGER,
    DANGER_SAFE,
)


class DebugScene(Scene):
    """
    Debug menu screen.
    Accessed via F12 key (only when DEBUG_MODE=True).
    Provides cheat functions for testing game features.
    """

    def __init__(self):
        super().__init__()
        self.buttons: list[Button] = []
        self.message = ""
        self.message_timer = 0.0
        self.message_color = DANGER_SAFE
        self._setup_ui()

    def _setup_ui(self) -> None:
        """Setup debug menu buttons."""
        options = DebugManager.get_debug_options()

        button_width = 250
        button_height = 40
        button_spacing = 50
        start_x = SCREEN_WIDTH // 2 - button_width // 2
        start_y = 120

        # Create option buttons (in two columns if many options)
        for i, (label, callback) in enumerate(options):
            col = i // 6
            row = i % 6

            x = (
                start_x
                + (col * (button_width + 20))
                - (button_width // 2) * (len(options) > 6)
            )
            y = start_y + row * button_spacing

            self.buttons.append(
                Button(
                    x=x,
                    y=y,
                    width=button_width,
                    height=button_height,
                    text=label,
                    callback=lambda cb=callback, lbl=label: self._execute_option(
                        cb, lbl
                    ),
                )
            )

        # Back button
        self.buttons.append(
            Button(
                x=SCREEN_WIDTH // 2 - 100,
                y=SCREEN_HEIGHT - 80,
                width=200,
                height=50,
                text="돌아가기",
                callback=self._go_back,
            )
        )

    def _execute_option(self, callback: Callable, label: str) -> None:
        """Execute a debug option and show feedback."""
        try:
            callback()
            self.message = f"✓ {label} 완료!"
            self.message_color = DANGER_SAFE
        except Exception as e:
            self.message = f"✗ 오류: {str(e)}"
            self.message_color = DANGER_DANGER

        self.message_timer = 3.0

    def _go_back(self) -> None:
        """Return to title scene."""
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
            if event.key == pygame.K_ESCAPE or event.key == pygame.K_F12:
                self._go_back()

    def update(self, dt: float) -> None:
        """Update scene."""
        for button in self.buttons:
            button.update(dt)

        if self.message_timer > 0:
            self.message_timer -= dt
            if self.message_timer <= 0:
                self.message = ""

    def render(self, screen: pygame.Surface) -> None:
        """Render debug menu."""
        # Background overlay
        overlay = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT))
        overlay.fill((20, 20, 40))
        overlay.set_alpha(240)
        screen.blit(overlay, (0, 0))

        # Title
        title_font = get_font(36, "bold")
        title_text = title_font.render("🔧 디버그 메뉴", True, WHITE)
        title_rect = title_text.get_rect(center=(SCREEN_WIDTH // 2, 50))
        screen.blit(title_text, title_rect)

        # Warning
        warning_font = get_font(14)
        warning_text = warning_font.render(
            "⚠ 이 메뉴는 개발/테스트 목적입니다. 게임 진행에 영향을 줄 수 있습니다.",
            True,
            DANGER_DANGER,
        )
        warning_rect = warning_text.get_rect(center=(SCREEN_WIDTH // 2, 85))
        screen.blit(warning_text, warning_rect)

        # Buttons
        for button in self.buttons:
            button.render(screen)

        # Status message
        if self.message:
            msg_font = get_font(20, "bold")
            msg_text = msg_font.render(self.message, True, self.message_color)
            msg_rect = msg_text.get_rect(
                center=(SCREEN_WIDTH // 2, SCREEN_HEIGHT - 130)
            )
            screen.blit(msg_text, msg_rect)

        # Hint
        hint_font = get_font(14)
        hint_text = hint_font.render(
            "[ESC] 또는 [F12]로 돌아가기", True, AIR_FORCE_BLUE
        )
        hint_rect = hint_text.get_rect(center=(SCREEN_WIDTH // 2, SCREEN_HEIGHT - 30))
        screen.blit(hint_text, hint_rect)
