"""
Collection Cutscene Scene - Interview story introduction.

Displays 4 comic panels (interview_1~4.png) in a 2x2 grid with slide-in
animations, reusing the same mechanics as IntroCutsceneScene.

Shown once per game session before the collection/recruitment screen.
"""

import os

import pygame

from fall_in.scenes.base_scene import Scene
from fall_in.utils.asset_loader import get_font
from fall_in.config import (
    SCREEN_WIDTH,
    SCREEN_HEIGHT,
    CUTSCENE_IMAGES_DIR,
    CUTSCENE_SLIDE_DURATION,
    CUTSCENE_SKIP_SPEED,
    CUTSCENE_BG_COLOR,
    CUTSCENE_SKIP_BTN_X,
    CUTSCENE_SKIP_BTN_Y,
    CUTSCENE_SKIP_BTN_WIDTH,
    CUTSCENE_SKIP_BTN_HEIGHT,
    AIR_FORCE_BLUE,
    WHITE,
)

_PADDING = 10
_CELL_W = (SCREEN_WIDTH - _PADDING * 3) // 2
_CELL_H = (SCREEN_HEIGHT - _PADDING * 3) // 2

_PAGE_RECTS = [
    pygame.Rect(_PADDING, _PADDING, _CELL_W, _CELL_H),
    pygame.Rect(_PADDING * 2 + _CELL_W, _PADDING, _CELL_W, _CELL_H),
    pygame.Rect(_PADDING, _PADDING * 2 + _CELL_H, _CELL_W, _CELL_H),
    pygame.Rect(_PADDING * 2 + _CELL_W, _PADDING * 2 + _CELL_H, _CELL_W, _CELL_H),
]


class _Phase:
    SLIDING_IN = 0
    WAITING_INPUT = 1
    DONE = 2


def _ease_out_cubic(t: float) -> float:
    return 1.0 - (1.0 - t) ** 3


class CollectionCutsceneScene(Scene):
    """Comic cutscene for the interview/collection story. Shown once per session."""

    def __init__(self) -> None:
        super().__init__()
        self._raw_images = self._load_raw_images()
        self._panels: list[pygame.Surface] = []
        self._rects: list[pygame.Rect] = []
        self._build_panels()
        self._panel_reveal_count: int = 0
        self._phase: int = _Phase.SLIDING_IN
        self._timer: float = 0.0
        self._skipping: bool = False
        self._skip_timer: float = 0.0
        self._skip_btn_rect = pygame.Rect(
            CUTSCENE_SKIP_BTN_X,
            CUTSCENE_SKIP_BTN_Y,
            CUTSCENE_SKIP_BTN_WIDTH,
            CUTSCENE_SKIP_BTN_HEIGHT,
        )
        from fall_in.core.audio_manager import AudioManager

        AudioManager().stop_bgm()
        from fall_in.config import SOUNDS_DIR

        self._panel_sfx: pygame.mixer.Sound | None = None
        try:
            sfx_path = SOUNDS_DIR / "sfx" / "cutscene.wav"
            if sfx_path.exists():
                self._panel_sfx = pygame.mixer.Sound(str(sfx_path))
                from fall_in.core.audio_manager import AudioManager

                self._panel_sfx.set_volume(AudioManager().sfx_volume)
        except Exception:
            pass

    @staticmethod
    def _load_raw_images() -> list[pygame.Surface]:
        images: list[pygame.Surface] = []
        if not CUTSCENE_IMAGES_DIR.exists():
            return images
        files = sorted(
            f
            for f in os.listdir(CUTSCENE_IMAGES_DIR)
            if f.startswith("interview_") and f.endswith(".png")
        )
        for fname in files:
            path = CUTSCENE_IMAGES_DIR / fname
            try:
                raw = pygame.image.load(str(path)).convert_alpha()
                images.append(raw)
            except Exception as e:
                print(f"[CollectionCutscene] Failed to load {fname}: {e}")
        return images

    def _build_panels(self) -> None:
        for i, raw in enumerate(self._raw_images):
            if i >= len(_PAGE_RECTS):
                break
            rect = _PAGE_RECTS[i]
            scaled = self._fit_to_rect(raw, rect)
            self._panels.append(scaled)
            self._rects.append(rect)

    @staticmethod
    def _fit_to_rect(surface: pygame.Surface, rect: pygame.Rect) -> pygame.Surface:
        img_w, img_h = surface.get_size()
        scale = min(rect.width / img_w, rect.height / img_h)
        new_w = int(img_w * scale)
        new_h = int(img_h * scale)
        scaled = pygame.transform.smoothscale(surface, (new_w, new_h))
        canvas = pygame.Surface(rect.size)
        canvas.fill(CUTSCENE_BG_COLOR)
        x = (rect.width - new_w) // 2
        y = (rect.height - new_h) // 2
        canvas.blit(scaled, (x, y))
        return canvas

    def _panel_count(self) -> int:
        return len(self._panels)

    def _all_panels_revealed(self) -> bool:
        return self._panel_reveal_count >= self._panel_count()

    def handle_event(self, event: pygame.event.Event) -> None:
        if self._phase == _Phase.DONE:
            return
        if event.type == pygame.MOUSEBUTTONDOWN:
            if self._skip_btn_rect.collidepoint(event.pos):
                self._phase = _Phase.DONE
                return
            if self._phase == _Phase.WAITING_INPUT:
                self._phase = _Phase.DONE
            elif self._phase == _Phase.SLIDING_IN:
                self._panel_reveal_count += 1
                self._play_panel_sfx()
                self._timer = 0.0
                if self._all_panels_revealed():
                    self._phase = _Phase.WAITING_INPUT
        elif event.type == pygame.KEYDOWN:
            if event.key in (pygame.K_SPACE, pygame.K_RETURN):
                if self._phase == _Phase.WAITING_INPUT:
                    self._phase = _Phase.DONE
                elif self._phase == _Phase.SLIDING_IN:
                    self._panel_reveal_count += 1
                    self._play_panel_sfx()
                    self._timer = 0.0
                    if self._all_panels_revealed():
                        self._phase = _Phase.WAITING_INPUT

    def update(self, dt: float) -> None:
        if self._phase == _Phase.DONE:
            self._transition_to_collection()
            return
        if not self._panels:
            self._phase = _Phase.DONE
            return
        if self._skipping:
            self._skip_timer += dt
            if self._skip_timer >= CUTSCENE_SKIP_SPEED:
                self._skip_timer -= CUTSCENE_SKIP_SPEED
                if self._phase == _Phase.SLIDING_IN:
                    self._panel_reveal_count += 1
                    self._play_panel_sfx()
                    self._timer = 0.0
                    if self._all_panels_revealed():
                        self._phase = _Phase.WAITING_INPUT
                if self._phase == _Phase.WAITING_INPUT:
                    self._phase = _Phase.DONE
            return
        if self._phase == _Phase.SLIDING_IN:
            self._timer += dt
            if self._timer >= CUTSCENE_SLIDE_DURATION:
                self._timer = CUTSCENE_SLIDE_DURATION
                self._panel_reveal_count += 1
                self._play_panel_sfx()
                if self._all_panels_revealed():
                    self._phase = _Phase.WAITING_INPUT
                else:
                    self._timer = 0.0

    def render(self, screen: pygame.Surface) -> None:
        screen.fill(CUTSCENE_BG_COLOR)
        for i, (panel, rect) in enumerate(zip(self._panels, self._rects)):
            if i < self._panel_reveal_count:
                screen.blit(panel, rect.topleft)
            elif i == self._panel_reveal_count and self._phase == _Phase.SLIDING_IN:
                t = min(self._timer / CUTSCENE_SLIDE_DURATION, 1.0)
                eased = _ease_out_cubic(t)
                offset_x = int((1.0 - eased) * SCREEN_WIDTH)
                screen.blit(panel, (rect.x + offset_x, rect.y))
        self._draw_skip_button(screen)
        self._draw_progress(screen)

    def _play_panel_sfx(self) -> None:
        if self._panel_sfx is not None:
            self._panel_sfx.play()

    def _transition_to_collection(self) -> None:
        from fall_in.core.game_manager import GameManager
        from fall_in.scenes.collection_loading_scene import CollectionLoadingScene

        GameManager().change_scene(CollectionLoadingScene())

    def _draw_skip_button(self, screen: pygame.Surface) -> None:
        btn = self._skip_btn_rect
        surf = pygame.Surface((btn.width, btn.height), pygame.SRCALPHA)
        pygame.draw.rect(
            surf, (0, 0, 0, 140), (0, 0, btn.width, btn.height), border_radius=8
        )
        pygame.draw.rect(
            surf,
            (*AIR_FORCE_BLUE, 200),
            (0, 0, btn.width, btn.height),
            width=2,
            border_radius=8,
        )
        screen.blit(surf, btn.topleft)
        font = get_font(16)
        text = font.render("건너뛰기 ▶▶", True, WHITE)
        screen.blit(text, text.get_rect(center=btn.center))

    def _draw_progress(self, screen: pygame.Surface) -> None:
        total = self._panel_count()
        if total <= 0:
            return
        dot_radius = 5
        spacing = 18
        start_x = SCREEN_WIDTH // 2 - (total - 1) * spacing // 2
        y = SCREEN_HEIGHT - 20
        for i in range(total):
            x = start_x + i * spacing
            if i < self._panel_reveal_count:
                pygame.draw.circle(screen, WHITE, (x, y), dot_radius)
            else:
                pygame.draw.circle(screen, (80, 80, 80), (x, y), dot_radius)
                pygame.draw.circle(screen, WHITE, (x, y), dot_radius, 1)
