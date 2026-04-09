"""
Game Mode Select Scene (PR-09).

Shown when the player taps "게임 시작" on the title screen.
Presents two choices:

  싱글플레이  — proceeds through GameLoadingScene → GameScene (existing path)
  멀티플레이  — proceeds to MultiplayerMenuScene (WS auth + lobby)

A "← 뒤로" button returns to TitleScene.
"""

from __future__ import annotations

import pygame

from fall_in.config import (
    AIR_FORCE_BLUE,
    LIGHT_BLUE,
    WHITE,
    SAND_BEIGE,
    SCREEN_WIDTH,
    SCREEN_HEIGHT,
)
from fall_in.scenes.base_scene import Scene
from fall_in.ui.button import Button
from fall_in.utils.asset_loader import get_font
from fall_in.utils.text_utils import draw_outlined_text


class GameModeSelectScene(Scene):
    """Single choice: 싱글플레이 vs 멀티플레이."""

    def __init__(self) -> None:
        super().__init__()
        cx = SCREEN_WIDTH // 2
        btn_w, btn_h = 260, 60
        gap = 24

        self._btn_single = Button(
            x=cx - btn_w // 2,
            y=SCREEN_HEIGHT // 2 - btn_h - gap // 2,
            width=btn_w,
            height=btn_h,
            text="싱글플레이",
            callback=self._on_single,
        )
        self._btn_multi = Button(
            x=cx - btn_w // 2,
            y=SCREEN_HEIGHT // 2 + gap // 2,
            width=btn_w,
            height=btn_h,
            text="멀티플레이",
            callback=self._on_multi,
        )
        self._btn_back = Button(20, 20, 100, 40, "← 뒤로", self._on_back)

        # Reuse the title background if available
        from fall_in.config import IMAGES_DIR

        self._bg_image: pygame.Surface | None = None
        try:
            path = IMAGES_DIR / "ui" / "backgrounds" / "title.png"
            if path.exists():
                img = pygame.image.load(str(path)).convert()
                self._bg_image = pygame.transform.smoothscale(
                    img, (SCREEN_WIDTH, SCREEN_HEIGHT)
                )
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def _on_single(self) -> None:
        from fall_in.core.game_manager import GameManager
        from fall_in.scenes.game_loading_scene import GameLoadingScene

        game = GameManager()
        prev_screen = game.screen.copy() if game.screen else None
        game.change_scene(GameLoadingScene(prev_screen=prev_screen))

    def _on_multi(self) -> None:
        from fall_in.core.game_manager import GameManager
        from fall_in.scenes.multiplayer_menu_scene import MultiplayerMenuScene

        GameManager().change_scene(MultiplayerMenuScene())

    def _on_back(self) -> None:
        from fall_in.core.game_manager import GameManager
        from fall_in.scenes.title_scene import TitleScene

        GameManager().change_scene(TitleScene())

    # ------------------------------------------------------------------
    # Scene interface
    # ------------------------------------------------------------------

    def handle_event(self, event: pygame.event.Event) -> None:
        self._btn_single.handle_event(event)
        self._btn_multi.handle_event(event)
        self._btn_back.handle_event(event)

    def update(self, dt: float) -> None:
        self._btn_single.update(dt)
        self._btn_multi.update(dt)
        self._btn_back.update(dt)

    def render(self, screen: pygame.Surface) -> None:
        if self._bg_image:
            screen.blit(self._bg_image, (0, 0))
        else:
            screen.fill(SAND_BEIGE)

        # Semi-transparent overlay so buttons stand out over any background
        overlay = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
        overlay.fill((245, 235, 220, 180))
        screen.blit(overlay, (0, 0))

        # Heading
        font = get_font(36, "bold")
        draw_outlined_text(
            screen,
            "게임 방식 선택",
            font,
            font.render("게임 방식 선택", True, AIR_FORCE_BLUE).get_rect(
                center=(SCREEN_WIDTH // 2, SCREEN_HEIGHT // 2 - 120)
            ).topleft,
            AIR_FORCE_BLUE,
            WHITE,
            outline_offset=2,
        )

        self._btn_single.render(screen)
        self._btn_multi.render(screen)
        self._btn_back.render(screen)
