"""
Debug Overlay Mixin - Reusable debug overlay functionality for any Scene.

Provides F12-toggled debug overlay with configurable hotkeys.
Each scene defines its own hotkey list; the mixin handles rendering
and event processing.
"""

from dataclasses import dataclass
from typing import Callable

import pygame

from fall_in.utils.asset_loader import get_font
from fall_in.config import (
    SCREEN_WIDTH,
    SCREEN_HEIGHT,
    AIR_FORCE_BLUE,
    WHITE,
    LIGHT_BLUE,
    DANGER_WARNING,
    DANGER_DANGER,
    DANGER_SAFE,
)


@dataclass
class DebugHotkey:
    """A single debug hotkey entry."""

    key: int  # pygame key constant (e.g. pygame.K_F1)
    label: str  # Display label (e.g. "강제 패배")
    callback: Callable[[], None]  # Function to call when key is pressed
    hotkey_name: str = ""  # Display name for the key (e.g. "F1")

    def __post_init__(self) -> None:
        if not self.hotkey_name:
            self.hotkey_name = pygame.key.name(self.key).upper()


class DebugOverlayMixin:
    """
    Mixin that provides F12 debug overlay functionality to any Scene.

    Usage::

        class MyScene(Scene, DebugOverlayMixin):
            def __init__(self):
                super().__init__()
                self.init_debug_overlay(self._get_debug_hotkeys())

            def _get_debug_hotkeys(self) -> list[DebugHotkey]:
                return [
                    DebugHotkey(pygame.K_F1, "강제 패배", self._force_lose),
                    DebugHotkey(pygame.K_F2, "강제 승리", self._force_win),
                ]

            def handle_event(self, event):
                if self.handle_debug_event(event):
                    return
                # ... normal event handling ...

            def render(self, screen):
                # ... normal rendering ...
                self.draw_debug_overlay(screen)
    """

    # ------------------------------------------------------------------
    # Initialization
    # ------------------------------------------------------------------

    def init_debug_overlay(self, hotkeys: list[DebugHotkey] | None = None) -> None:
        """Initialize the debug overlay state with the given hotkeys."""
        self._debug_overlay_active: bool = False
        self._debug_hotkeys: list[DebugHotkey] = hotkeys or []
        self._debug_message: str = ""
        self._debug_message_timer: float = 0.0
        self._debug_message_color: tuple = DANGER_SAFE

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def is_debug_active(self) -> bool:
        """Whether the debug overlay is currently showing."""
        return self._debug_overlay_active

    @is_debug_active.setter
    def is_debug_active(self, value: bool) -> None:
        self._debug_overlay_active = value

    # ------------------------------------------------------------------
    # Event handling
    # ------------------------------------------------------------------

    def handle_debug_event(self, event: pygame.event.Event) -> bool:
        """
        Process debug-related events.

        Returns True if the event was consumed (caller should skip
        normal processing). Returns False otherwise.
        """
        if event.type != pygame.KEYDOWN:
            return False

        # ESC closes the overlay if it's active
        if event.key == pygame.K_ESCAPE and self._debug_overlay_active:
            self._debug_overlay_active = False
            return True

        # F12 toggles overlay (only when DEBUG_MODE is on)
        if event.key == pygame.K_F12:
            from fall_in.config import DEBUG_MODE

            if DEBUG_MODE:
                self._debug_overlay_active = not self._debug_overlay_active
            return True

        # When overlay is active, check hotkeys
        if self._debug_overlay_active:
            for hotkey in self._debug_hotkeys:
                if event.key == hotkey.key:
                    self._execute_debug_hotkey(hotkey)
                    return True

        return False

    def _execute_debug_hotkey(self, hotkey: DebugHotkey) -> None:
        """Execute a debug hotkey callback with feedback message."""
        try:
            hotkey.callback()
            self._debug_message = f"✓ {hotkey.label} 완료!"
            self._debug_message_color = DANGER_SAFE
        except Exception as e:
            self._debug_message = f"✗ 오류: {str(e)}"
            self._debug_message_color = DANGER_DANGER
        self._debug_message_timer = 3.0

    # ------------------------------------------------------------------
    # Update (call from scene's update method)
    # ------------------------------------------------------------------

    def update_debug_overlay(self, dt: float) -> None:
        """Update debug overlay timers. Call from the scene's update()."""
        if self._debug_message_timer > 0:
            self._debug_message_timer -= dt
            if self._debug_message_timer <= 0:
                self._debug_message = ""

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------

    def draw_debug_overlay(self, screen: pygame.Surface) -> None:
        """
        Render the debug overlay if active.

        Call at the END of the scene's render() so it draws on top.
        """
        if not self._debug_overlay_active:
            return

        # Semi-transparent background
        overlay = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 150))
        screen.blit(overlay, (0, 0))

        # Panel dimensions (auto-size based on hotkey count)
        item_height = 30
        num_items = len(self._debug_hotkeys)
        panel_w = 340
        panel_h = max(120, 50 + num_items * item_height + 40)
        panel_x = SCREEN_WIDTH // 2 - panel_w // 2
        panel_y = SCREEN_HEIGHT // 2 - panel_h // 2

        # Panel background
        pygame.draw.rect(
            screen,
            (20, 20, 50),
            (panel_x, panel_y, panel_w, panel_h),
            border_radius=10,
        )
        pygame.draw.rect(
            screen,
            AIR_FORCE_BLUE,
            (panel_x, panel_y, panel_w, panel_h),
            width=2,
            border_radius=10,
        )

        title_font = get_font(20, "bold")
        item_font = get_font(14)

        # Title
        title = title_font.render("🔧 디버그", True, WHITE)
        screen.blit(
            title, (panel_x + panel_w // 2 - title.get_width() // 2, panel_y + 12)
        )

        # Hotkey items
        for i, hotkey in enumerate(self._debug_hotkeys):
            y = panel_y + 50 + i * item_height
            key_text = item_font.render(f"[{hotkey.hotkey_name}]", True, DANGER_WARNING)
            desc_text = item_font.render(f" {hotkey.label}", True, WHITE)
            screen.blit(key_text, (panel_x + 20, y))
            screen.blit(desc_text, (panel_x + 20 + key_text.get_width(), y))

        # Feedback message
        if self._debug_message:
            msg_font = get_font(16, "bold")
            msg_text = msg_font.render(
                self._debug_message, True, self._debug_message_color
            )
            msg_rect = msg_text.get_rect(
                center=(SCREEN_WIDTH // 2, panel_y + panel_h + 30)
            )
            screen.blit(msg_text, msg_rect)

        # Close hint
        hint = item_font.render("[ESC/F12] 닫기", True, LIGHT_BLUE)
        screen.blit(
            hint,
            (panel_x + panel_w // 2 - hint.get_width() // 2, panel_y + panel_h - 28),
        )
