"""
Intro Cutscene Scene — Comic-panel story introduction.

Displays comic panels across multiple pages with slide-in animations.
Page 1: intro_1 ~ intro_4 in a 2×2 grid (panels fly in one at a time).
Page 2: intro_5 ~ intro_6 (panels fly in one at a time).

The player advances panels by clicking or pressing Space/Enter.
A "건너뛰기" (skip) button in the top-right fast-forwards through
remaining panels.
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

# ---------------------------------------------------------------------------
# Layout — define which images belong to which page and their target rects
# ---------------------------------------------------------------------------

_PADDING = 10  # gap between panels and edges

# Page 1: 2×2 grid  (indices 0-3 of the loaded images)
_CELL_W = (SCREEN_WIDTH - _PADDING * 3) // 2
_CELL_H = (SCREEN_HEIGHT - _PADDING * 3) // 2

_PAGE_1_RECTS = [
    pygame.Rect(_PADDING, _PADDING, _CELL_W, _CELL_H),  # top-left
    pygame.Rect(_PADDING * 2 + _CELL_W, _PADDING, _CELL_W, _CELL_H),  # top-right
    pygame.Rect(_PADDING, _PADDING * 2 + _CELL_H, _CELL_W, _CELL_H),  # bottom-left
    pygame.Rect(
        _PADDING * 2 + _CELL_W, _PADDING * 2 + _CELL_H, _CELL_W, _CELL_H
    ),  # bottom-right
]

# Page 2: left + right layout (indices 4-5)
_P2_LEFT_W = (SCREEN_WIDTH - _PADDING * 3) * 3 // 5
_P2_RIGHT_W = (SCREEN_WIDTH - _PADDING * 3) - _P2_LEFT_W
_P2_H = SCREEN_HEIGHT - _PADDING * 2

_PAGE_2_RECTS = [
    pygame.Rect(_PADDING, _PADDING, _P2_LEFT_W, _P2_H),  # left (16:9 landscape)
    pygame.Rect(
        _PADDING * 2 + _P2_LEFT_W, _PADDING, _P2_RIGHT_W, _P2_H
    ),  # right (1:1 square)
]

# Per-panel transforms: keyed by global image index
# scale_override: extra zoom factor applied after fit-to-rect (>1 = enlarge)
# rotate_deg: rotation in degrees (positive = counter-clockwise)
_PANEL_TRANSFORMS: dict[int, dict] = {
    3: {"scale_override": 1.07},  # intro_4: enlarge to match siblings
    5: {"scale_override": 1.07, "rotate_deg": -5},  # intro_6: rotate CW + enlarge
}

# Collected page definitions: list of (image_indices, target_rects)
_PAGES: list[tuple[list[int], list[pygame.Rect]]] = [
    ([0, 1, 2, 3], _PAGE_1_RECTS),
    ([4, 5], _PAGE_2_RECTS),
]


# ---------------------------------------------------------------------------
# Phase enum
# ---------------------------------------------------------------------------


class _Phase:
    SLIDING_IN = 0  # current panel is animating in
    WAITING_INPUT = 1  # all current-page panels shown, waiting for advance
    DONE = 2


# ---------------------------------------------------------------------------
# Easing
# ---------------------------------------------------------------------------


def _ease_out_cubic(t: float) -> float:
    """Ease-out cubic — fast start, smooth deceleration."""
    return 1.0 - (1.0 - t) ** 3


# ---------------------------------------------------------------------------
# Scene
# ---------------------------------------------------------------------------


class IntroCutsceneScene(Scene):
    """Multi-page comic cutscene shown before the title screen."""

    def __init__(self) -> None:
        super().__init__()

        # Load raw images (not yet scaled to cells)
        self._raw_images: list[pygame.Surface] = self._load_raw_images()

        # Pre-scale images for every cell they appear in
        self._page_panels: list[list[pygame.Surface]] = []  # per-page scaled panels
        self._page_rects: list[list[pygame.Rect]] = []  # per-page target rects
        self._build_pages()

        # Navigation state
        self._page_index: int = 0  # which page we are on
        self._panel_reveal_count: int = (
            0  # how many panels revealed so far on current page
        )
        self._phase: int = _Phase.SLIDING_IN
        self._timer: float = 0.0

        # Skip state
        self._skipping: bool = False
        self._skip_timer: float = 0.0

        # Skip button rect
        self._skip_btn_rect = pygame.Rect(
            CUTSCENE_SKIP_BTN_X,
            CUTSCENE_SKIP_BTN_Y,
            CUTSCENE_SKIP_BTN_WIDTH,
            CUTSCENE_SKIP_BTN_HEIGHT,
        )

        # Load cutscene panel SFX
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

    # ------------------------------------------------------------------
    # Asset loading
    # ------------------------------------------------------------------

    @staticmethod
    def _load_raw_images() -> list[pygame.Surface]:
        """Load all intro_*.png files in sorted order."""
        images: list[pygame.Surface] = []
        if not CUTSCENE_IMAGES_DIR.exists():
            return images

        files = sorted(
            f
            for f in os.listdir(CUTSCENE_IMAGES_DIR)
            if f.startswith("intro_") and f.endswith(".png")
        )

        for fname in files:
            path = CUTSCENE_IMAGES_DIR / fname
            try:
                raw = pygame.image.load(str(path)).convert_alpha()
                images.append(raw)
            except Exception as e:
                print(f"[IntroCutscene] Failed to load {fname}: {e}")

        return images

    def _build_pages(self) -> None:
        """Pre-scale each raw image to its target cell rect."""
        for img_indices, rects in _PAGES:
            page_panels: list[pygame.Surface] = []
            page_rects: list[pygame.Rect] = []

            for i, idx in enumerate(img_indices):
                if idx >= len(self._raw_images) or i >= len(rects):
                    continue
                raw = self._raw_images[idx]
                rect = rects[i]
                transforms = _PANEL_TRANSFORMS.get(idx, {})
                scaled = self._fit_to_rect(raw, rect, transforms)
                page_panels.append(scaled)
                page_rects.append(rect)

            if page_panels:
                self._page_panels.append(page_panels)
                self._page_rects.append(page_rects)

    @staticmethod
    def _fit_to_rect(
        surface: pygame.Surface,
        rect: pygame.Rect,
        transforms: dict | None = None,
    ) -> pygame.Surface:
        """Scale image to fit inside rect while keeping aspect ratio.
        Applies optional transforms (scale_override, rotate_deg).
        Returns a surface of *exactly* rect.size with the image centred
        and the remaining area filled with CUTSCENE_BG_COLOR."""
        if transforms is None:
            transforms = {}

        src_w, src_h = surface.get_size()
        aspect = src_w / src_h
        target_aspect = rect.width / rect.height

        if aspect >= target_aspect:
            new_w = rect.width
            new_h = int(rect.width / aspect)
        else:
            new_h = rect.height
            new_w = int(rect.height * aspect)

        # Apply scale override (zoom into the content)
        scale_override = transforms.get("scale_override", 1.0)
        if scale_override != 1.0:
            new_w = int(new_w * scale_override)
            new_h = int(new_h * scale_override)

        scaled = pygame.transform.smoothscale(surface, (new_w, new_h))

        # Apply rotation (rotozoom applies anti-aliased smooth rotation)
        rotate_deg = transforms.get("rotate_deg", 0)
        if rotate_deg != 0:
            scaled = pygame.transform.rotozoom(scaled, rotate_deg, 1.0)

        # Centre on a cell-sized surface, clipping any overflow
        result = pygame.Surface((rect.width, rect.height))
        result.fill(CUTSCENE_BG_COLOR)
        x = (rect.width - scaled.get_width()) // 2
        y = (rect.height - scaled.get_height()) // 2
        result.blit(scaled, (x, y))
        return result

    # ------------------------------------------------------------------
    # Current page helpers
    # ------------------------------------------------------------------

    def _current_page_panel_count(self) -> int:
        if self._page_index >= len(self._page_panels):
            return 0
        return len(self._page_panels[self._page_index])

    def _all_panels_revealed(self) -> bool:
        return self._panel_reveal_count >= self._current_page_panel_count()

    def _total_panels(self) -> int:
        return sum(len(p) for p in self._page_panels)

    def _revealed_so_far(self) -> int:
        """Total panels revealed across all previous pages + current page."""
        count = 0
        for i in range(self._page_index):
            count += len(self._page_panels[i])
        count += self._panel_reveal_count
        return count

    # ------------------------------------------------------------------
    # Scene interface
    # ------------------------------------------------------------------

    def handle_event(self, event: pygame.event.Event) -> None:
        if self._phase == _Phase.DONE:
            return

        if event.type == pygame.MOUSEBUTTONDOWN:
            if self._skip_btn_rect.collidepoint(event.pos):
                from fall_in.core.audio_manager import AudioManager

                AudioManager().play_sfx("sfx/back.wav")
                self._phase = _Phase.DONE
                return

            if self._phase == _Phase.WAITING_INPUT and not self._skipping:
                self._advance()

        elif event.type == pygame.KEYDOWN:
            if event.key in (pygame.K_SPACE, pygame.K_RETURN):
                if self._phase == _Phase.WAITING_INPUT and not self._skipping:
                    self._advance()

    def update(self, dt: float) -> None:
        if self._phase == _Phase.DONE:
            self._transition_to_title()
            return

        if not self._page_panels:
            self._phase = _Phase.DONE
            return

        # Skipping — auto-advance quickly
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
                    self._advance()
            return

        # Normal slide-in
        if self._phase == _Phase.SLIDING_IN:
            self._timer += dt
            if self._timer >= CUTSCENE_SLIDE_DURATION:
                self._timer = CUTSCENE_SLIDE_DURATION
                self._panel_reveal_count += 1
                self._play_panel_sfx()

                if self._all_panels_revealed():
                    self._phase = _Phase.WAITING_INPUT
                else:
                    # Start sliding next panel on same page
                    self._timer = 0.0

    def render(self, screen: pygame.Surface) -> None:
        screen.fill(CUTSCENE_BG_COLOR)

        if not self._page_panels or self._page_index >= len(self._page_panels):
            return

        panels = self._page_panels[self._page_index]
        rects = self._page_rects[self._page_index]

        for i in range(len(panels)):
            if i < self._panel_reveal_count:
                # Fully revealed
                screen.blit(panels[i], rects[i].topleft)
            elif i == self._panel_reveal_count and self._phase == _Phase.SLIDING_IN:
                # Currently animating
                t = min(self._timer / CUTSCENE_SLIDE_DURATION, 1.0)
                eased = _ease_out_cubic(t)
                # Slide from right edge towards target position
                start_x = SCREEN_WIDTH
                target_x = rects[i].x
                current_x = int(start_x + (target_x - start_x) * eased)
                screen.blit(panels[i], (current_x, rects[i].y))
            # Panels beyond reveal_count are not drawn yet

        # Skip button
        self._draw_skip_button(screen)

        # Progress dots
        self._draw_progress(screen)

    # ------------------------------------------------------------------
    # Navigation
    # ------------------------------------------------------------------

    def _advance(self) -> None:
        """Move to the next page, or finish if on the last page."""
        self._page_index += 1
        if self._page_index >= len(self._page_panels):
            self._phase = _Phase.DONE
        else:
            self._panel_reveal_count = 0
            self._phase = _Phase.SLIDING_IN
            self._timer = 0.0

    def _play_panel_sfx(self) -> None:
        """Play SFX when a new panel is revealed."""
        if self._panel_sfx is not None:
            self._panel_sfx.play()

    def _transition_to_title(self) -> None:
        from fall_in.core.game_manager import GameManager, GameState
        from fall_in.scenes.title_scene import TitleScene

        gm = GameManager()
        gm.state = GameState.TITLE
        gm.change_scene(TitleScene())

    # ------------------------------------------------------------------
    # Rendering helpers
    # ------------------------------------------------------------------

    def _draw_skip_button(self, screen: pygame.Surface) -> None:
        btn = self._skip_btn_rect
        btn_surface = pygame.Surface((btn.width, btn.height), pygame.SRCALPHA)
        btn_surface.fill((0, 0, 0, 120))
        screen.blit(btn_surface, btn.topleft)
        pygame.draw.rect(screen, WHITE, btn, 2, border_radius=6)

        font = get_font(16)
        label = font.render("건너뛰기 >>", True, WHITE)
        label_rect = label.get_rect(center=btn.center)
        screen.blit(label, label_rect)

    def _draw_progress(self, screen: pygame.Surface) -> None:
        """Draw page-level progress dots at the bottom."""
        total_pages = len(self._page_panels)
        if total_pages == 0:
            return

        dot_radius = 6
        dot_gap = 22
        total_width = total_pages * dot_gap
        start_x = (SCREEN_WIDTH - total_width) // 2 + dot_gap // 2
        y = SCREEN_HEIGHT - 25

        for i in range(total_pages):
            x = start_x + i * dot_gap
            color = AIR_FORCE_BLUE if i <= self._page_index else (200, 200, 200)
            pygame.draw.circle(screen, color, (x, y), dot_radius)
