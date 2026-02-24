"""
Game Loading Scene - Hangar door animation with deferred GameScene loading.

Flow: door closes (top→down) → load GameScene → door opens (down→top) → transition.
"""

import pygame

from fall_in.scenes.base_scene import Scene
from fall_in.utils.asset_loader import get_font
from fall_in.data.loading_tips import get_random_tip
from fall_in.config import (
    SCREEN_WIDTH,
    SCREEN_HEIGHT,
    WHITE,
    SAND_BEIGE,
    LOADING_MIN_HOLD,
    LOADING_DOOR_CLOSE_DURATION,
    LOADING_DOOR_OPEN_DURATION,
    LOADING_DOOR_LOAD_DELAY,
    LOADING_DOOR_COLOR,
    LOADING_DOOR_RIDGE_COLOR,
    LOADING_DOOR_BORDER_COLOR,
    LOADING_DOOR_RIDGE_SPACING,
    LOADING_DOOR_RIDGE_HEIGHT,
)


class _Phase:
    CLOSING = 0
    LOADING = 1
    OPENING = 2
    DONE = 3


class GameLoadingScene(Scene):
    """
    Loading screen that plays a hangar-door animation while constructing
    the GameScene in the background.
    """

    def __init__(
        self, difficulty: str = "normal", prev_screen: pygame.Surface | None = None
    ):
        super().__init__()
        self.difficulty = difficulty
        self.phase = _Phase.CLOSING
        self.timer = 0.0
        self.tip = get_random_tip()

        # Snapshot of previous scene (title) to show behind the closing door
        self._prev_screen = prev_screen

        # The target scene, built during LOADING phase
        self._target_scene: Scene | None = None

        # Pre-rendered door surface (full screen width × screen height)
        self._door_surface = self._build_door_surface()

    # ------------------------------------------------------------------
    # Door surface
    # ------------------------------------------------------------------

    @staticmethod
    def _build_door_surface() -> pygame.Surface:
        """Create a metallic shutter door surface."""
        surf = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT))
        surf.fill(LOADING_DOOR_COLOR)

        # Horizontal ridges
        for y in range(0, SCREEN_HEIGHT, LOADING_DOOR_RIDGE_SPACING):
            pygame.draw.rect(
                surf,
                LOADING_DOOR_RIDGE_COLOR,
                (0, y, SCREEN_WIDTH, LOADING_DOOR_RIDGE_HEIGHT),
            )

        # Bottom border (thick bar to look like door edge)
        pygame.draw.rect(
            surf, LOADING_DOOR_BORDER_COLOR, (0, SCREEN_HEIGHT - 8, SCREEN_WIDTH, 8)
        )

        # Handle in center
        handle_w, handle_h = 60, 6
        handle_rect = pygame.Rect(
            SCREEN_WIDTH // 2 - handle_w // 2,
            SCREEN_HEIGHT - 20,
            handle_w,
            handle_h,
        )
        pygame.draw.rect(surf, (120, 125, 135), handle_rect, border_radius=3)

        return surf

    # ------------------------------------------------------------------
    # Door offset helpers
    # ------------------------------------------------------------------

    def _get_door_y(self) -> int:
        """
        Return vertical offset of the door top-left corner.
        - Fully OPEN  → door is at y = -SCREEN_HEIGHT (off screen above)
        - Fully CLOSED → door is at y = 0
        """
        if self.phase == _Phase.CLOSING:
            t = min(self.timer / LOADING_DOOR_CLOSE_DURATION, 1.0)
            t = _ease_in_out(t)
            return int(-SCREEN_HEIGHT * (1.0 - t))  # -H → 0
        elif self.phase == _Phase.LOADING:
            return 0
        elif self.phase == _Phase.OPENING:
            t = min(self.timer / LOADING_DOOR_OPEN_DURATION, 1.0)
            t = _ease_in_out(t)
            return int(-SCREEN_HEIGHT * t)  # 0 → -H
        return -SCREEN_HEIGHT

    # ------------------------------------------------------------------
    # Scene interface
    # ------------------------------------------------------------------

    def handle_event(self, event: pygame.event.Event) -> None:
        """No user input during loading."""
        pass

    def update(self, dt: float) -> None:
        self.timer += dt

        if self.phase == _Phase.CLOSING:
            if self.timer >= LOADING_DOOR_CLOSE_DURATION:
                self.phase = _Phase.LOADING
                self.timer = 0.0

        elif self.phase == _Phase.LOADING:
            if self._target_scene is None and self.timer >= LOADING_DOOR_LOAD_DELAY:
                # Construct the heavy GameScene now (blocks this frame)
                self._target_scene = self._build_game_scene()

            if self._target_scene is not None and self.timer >= LOADING_MIN_HOLD:
                self.phase = _Phase.OPENING
                self.timer = 0.0

        elif self.phase == _Phase.OPENING:
            if self.timer >= LOADING_DOOR_OPEN_DURATION:
                self.phase = _Phase.DONE

        elif self.phase == _Phase.DONE:
            if self._target_scene is not None:
                from fall_in.core.game_manager import GameManager

                GameManager().change_scene(self._target_scene)

    def render(self, screen: pygame.Surface) -> None:
        # Background: show prev screen during closing, target scene during opening
        if self.phase == _Phase.CLOSING and self._prev_screen is not None:
            screen.blit(self._prev_screen, (0, 0))
        elif self._target_scene is not None:
            self._target_scene.render(screen)
        else:
            screen.fill(SAND_BEIGE)

        # Draw door
        door_y = self._get_door_y()
        screen.blit(self._door_surface, (0, door_y))

        # Draw tip text (only when door is mostly visible)
        if door_y > -SCREEN_HEIGHT * 0.3:
            self._draw_tip(screen, door_y)

        # "로딩 중..." text when door is closed
        if self.phase == _Phase.LOADING:
            self._draw_loading_indicator(screen)

    # ------------------------------------------------------------------
    # Rendering helpers
    # ------------------------------------------------------------------

    def _draw_tip(self, screen: pygame.Surface, door_y: int) -> None:
        """Draw gameplay tip near bottom of the closed door."""
        tip_font = get_font(14)
        tip_surface = tip_font.render(f"💡 TIP: {self.tip}", True, (200, 200, 210))
        tip_x = SCREEN_WIDTH // 2 - tip_surface.get_width() // 2
        tip_y = door_y + SCREEN_HEIGHT - 50
        if 0 <= tip_y <= SCREEN_HEIGHT:
            screen.blit(tip_surface, (tip_x, tip_y))

    def _draw_loading_indicator(self, screen: pygame.Surface) -> None:
        """Draw a centered loading label."""
        font = get_font(20)
        dots = "." * (int(self.timer * 3) % 4)
        text = font.render(f"로딩 중{dots}", True, WHITE)
        screen.blit(
            text,
            text.get_rect(center=(SCREEN_WIDTH // 2, SCREEN_HEIGHT // 2)),
        )

    # ------------------------------------------------------------------
    # Scene construction
    # ------------------------------------------------------------------

    def _build_game_scene(self) -> Scene:
        """Construct and return the GameScene."""
        from fall_in.core.game_manager import GameState, GameManager
        from fall_in.scenes.game_scene import GameScene

        GameManager().state = GameState.PLAYING
        return GameScene(difficulty=self.difficulty)


# ------------------------------------------------------------------
# Easing
# ------------------------------------------------------------------


def _ease_in_out(t: float) -> float:
    """Smooth ease-in-out (cubic)."""
    if t < 0.5:
        return 4 * t * t * t
    return 1 - (-2 * t + 2) ** 3 / 2
