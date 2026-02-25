"""
Title Debug Scene - Debug menu accessible from the title screen.

Accessed via F12 key (only when DEBUG_MODE=True).
Provides cheat functions for testing game features via hotkey overlay.
"""

import pygame

from fall_in.scenes.base_scene import Scene
from fall_in.utils.debug_overlay import DebugOverlayMixin, DebugHotkey
from fall_in.core.debug_manager import DebugManager


class DebugScene(Scene, DebugOverlayMixin):
    """
    Debug menu screen for the title scene.
    Accessed via F12 key (only when DEBUG_MODE=True).
    Provides cheat functions for testing game features.
    """

    def __init__(self):
        super().__init__()
        self.init_debug_overlay(self._get_debug_hotkeys())
        # Open overlay immediately since user explicitly entered this scene
        self.is_debug_active = True

    def _get_debug_hotkeys(self) -> list[DebugHotkey]:
        """Build hotkey list from DebugManager options."""
        options = DebugManager.get_debug_options()

        # Map F1-F11 keys to the debug options
        f_keys = [
            pygame.K_F1,
            pygame.K_F2,
            pygame.K_F3,
            pygame.K_F4,
            pygame.K_F5,
            pygame.K_F6,
            pygame.K_F7,
            pygame.K_F8,
            pygame.K_F9,
            pygame.K_F10,
            pygame.K_F11,
        ]

        hotkeys: list[DebugHotkey] = []
        for i, (label, callback) in enumerate(options):
            if i >= len(f_keys):
                break
            hotkeys.append(DebugHotkey(key=f_keys[i], label=label, callback=callback))

        return hotkeys

    def _go_back(self) -> None:
        """Return to title scene."""
        from fall_in.core.game_manager import GameManager, GameState
        from fall_in.scenes.title_scene import TitleScene

        game = GameManager()
        game.state = GameState.TITLE
        game.change_scene(TitleScene())

    def handle_event(self, event: pygame.event.Event) -> None:
        """Handle events."""
        if self.handle_debug_event(event):
            # If ESC/F12 closed the overlay, go back to title
            if not self.is_debug_active:
                self._go_back()
            return

    def update(self, dt: float) -> None:
        """Update scene."""
        self.update_debug_overlay(dt)

    def render(self, screen: pygame.Surface) -> None:
        """Render debug menu."""
        # Dark background
        screen.fill((20, 20, 40))
        self.draw_debug_overlay(screen)
