"""
Collection Loading Scene - Spinner animation with deferred RecruitmentScene loading.

Flow: black screen + spinner → load RecruitmentScene → fade out → transition.
"""

import math

import pygame

from fall_in.scenes.base_scene import Scene
from fall_in.utils.asset_loader import get_font
from fall_in.data.loading_tips import get_random_tip
from fall_in.config import (
    SCREEN_WIDTH,
    SCREEN_HEIGHT,
    WHITE,
    LOADING_MIN_HOLD,
    LOADING_SPINNER_LOAD_DELAY,
    LOADING_SPINNER_FADE_DURATION,
    LOADING_SPINNER_RADIUS,
    LOADING_SPINNER_THICKNESS,
    LOADING_SPINNER_SPEED,
)


class _Phase:
    LOADING = 0
    FADE_OUT = 1
    DONE = 2


class CollectionLoadingScene(Scene):
    """
    Loading screen with a rotating spinner shown while the
    RecruitmentScene is being constructed.
    """

    def __init__(self):
        super().__init__()
        self.phase = _Phase.LOADING
        self.timer = 0.0
        self.tip = get_random_tip()
        self._angle = 0.0

        # Target scene, built during LOADING phase
        self._target_scene: Scene | None = None

        # Stop BGM once on entry (not every frame)
        from fall_in.core.audio_manager import AudioManager

        AudioManager().stop_bgm()

    def handle_event(self, event: pygame.event.Event) -> None:
        pass

    def update(self, dt: float) -> None:
        self.timer += dt
        self._angle += LOADING_SPINNER_SPEED * dt

        if self.phase == _Phase.LOADING:
            if self._target_scene is None and self.timer >= LOADING_SPINNER_LOAD_DELAY:
                self._target_scene = self._build_scene()

            if self._target_scene is not None and self.timer >= LOADING_MIN_HOLD:
                self.phase = _Phase.FADE_OUT
                self.timer = 0.0

        elif self.phase == _Phase.FADE_OUT:
            if self.timer >= LOADING_SPINNER_FADE_DURATION:
                self.phase = _Phase.DONE

        elif self.phase == _Phase.DONE:
            if self._target_scene is not None:
                from fall_in.core.game_manager import GameManager
                from fall_in.core.audio_manager import AudioManager
                from fall_in.config import COLLECTION_BGM_PATH

                AudioManager().play_bgm(COLLECTION_BGM_PATH)
                GameManager().change_scene(self._target_scene)

    def render(self, screen: pygame.Surface) -> None:
        if self.phase == _Phase.FADE_OUT and self._target_scene is not None:
            # Render target underneath with a fading overlay
            self._target_scene.render(screen)
            alpha = max(
                0, int(255 * (1.0 - self.timer / LOADING_SPINNER_FADE_DURATION))
            )
            overlay = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT))
            overlay.fill((0, 0, 0))
            overlay.set_alpha(alpha)
            screen.blit(overlay, (0, 0))
        else:
            screen.fill((0, 0, 0))

        # Spinner (only during LOADING phase)
        if self.phase == _Phase.LOADING:
            self._draw_spinner(screen)

        # Tip text
        if self.phase != _Phase.DONE:
            self._draw_tip(screen)

        # "로딩 중..." text
        if self.phase == _Phase.LOADING:
            self._draw_loading_text(screen)

    # ------------------------------------------------------------------
    # Drawing helpers
    # ------------------------------------------------------------------

    def _draw_spinner(self, screen: pygame.Surface) -> None:
        """Draw a rotating arc spinner."""
        cx = SCREEN_WIDTH // 2
        cy = SCREEN_HEIGHT // 2 - 30
        rect = pygame.Rect(
            cx - LOADING_SPINNER_RADIUS,
            cy - LOADING_SPINNER_RADIUS,
            LOADING_SPINNER_RADIUS * 2,
            LOADING_SPINNER_RADIUS * 2,
        )
        start_rad = math.radians(self._angle)
        end_rad = start_rad + math.radians(90)
        pygame.draw.arc(
            screen, WHITE, rect, start_rad, end_rad, LOADING_SPINNER_THICKNESS
        )

    def _draw_tip(self, screen: pygame.Surface) -> None:
        """Draw gameplay tip near bottom."""
        tip_font = get_font(14)
        tip_surface = tip_font.render(f"💡 TIP: {self.tip}", True, (200, 200, 210))
        screen.blit(
            tip_surface,
            tip_surface.get_rect(center=(SCREEN_WIDTH // 2, SCREEN_HEIGHT - 50)),
        )

    def _draw_loading_text(self, screen: pygame.Surface) -> None:
        """Draw loading label above spinner."""
        font = get_font(18)
        dots = "." * (int(self.timer * 3) % 4)
        text = font.render(f"로딩 중{dots}", True, WHITE)
        screen.blit(
            text,
            text.get_rect(center=(SCREEN_WIDTH // 2, SCREEN_HEIGHT // 2 + 20)),
        )

    # ------------------------------------------------------------------
    # Scene construction
    # ------------------------------------------------------------------

    def _build_scene(self) -> Scene:
        """Construct and return the RecruitmentScene."""
        from fall_in.core.game_manager import GameManager, GameState
        from fall_in.scenes.recruitment_scene import RecruitmentScene

        GameManager().state = GameState.COLLECTION
        return RecruitmentScene()
