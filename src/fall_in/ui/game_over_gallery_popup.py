"""
GameOverGalleryPopup - Modal overlay showing game over scenes the player has
unlocked (seen at least once during gameplay).

Displayed as a grid of thumbnails. Each card shows the scenario background
image (if available) plus the scenario name. Clicking outside or pressing
ESC closes the popup.

seen_endings in player_data.json stores bg stems, e.g. "victory_bg",
"defeat_coup".  Images are loaded directly from GAMEOVER_IMAGES_DIR.
"""

from __future__ import annotations

import json

import pygame

from fall_in.utils.asset_loader import get_font
from fall_in.config import (
    SCREEN_WIDTH,
    SCREEN_HEIGHT,
    WHITE,
    DATA_DIR,
    GAMEOVER_IMAGES_DIR,
)

_THUMB_W = 200
_THUMB_H = 130
_THUMB_GAP = 20
_COLS = 3

_POPUP_W = _COLS * _THUMB_W + (_COLS + 1) * _THUMB_GAP
_POPUP_H = 420
_POPUP_X = (SCREEN_WIDTH - _POPUP_W) // 2
_POPUP_Y = (SCREEN_HEIGHT - _POPUP_H) // 2


class GameOverGalleryPopup:
    """
    Modal gallery popup for seen game over ending backgrounds.
    Create one instance per parent popup and call render() every frame.
    """

    def __init__(self) -> None:
        self.visible = False

        self._rect = pygame.Rect(_POPUP_X, _POPUP_Y, _POPUP_W, _POPUP_H)
        self._close_btn = pygame.Rect(self._rect.right - 36, self._rect.top + 8, 28, 28)

        # Preview state: index of card being previewed (-1 = none)
        self._preview_idx: int = -1
        self._preview_surface: pygame.Surface | None = None

        # Cached data (loaded on show)
        self._seen_stems: list[str] = []
        self._thumbnails: list[pygame.Surface | None] = []
        self._img_paths: list[str | None] = []  # original file paths for preview
        self._card_rects: list[pygame.Rect] = []
        self._display_names: list[str] = []

    def show(self) -> None:
        self.visible = True
        self._preview_idx = -1
        self._preview_surface = None
        self._reload()

    def hide(self) -> None:
        self.visible = False
        self._preview_idx = -1
        self._preview_surface = None

    # ------------------------------------------------------------------
    # Data loading
    # ------------------------------------------------------------------

    def _reload(self) -> None:
        """Load seen endings and build thumbnail surfaces."""
        from fall_in.core.ending_manager import EndingManager

        seen_stems = self._load_seen_stems()

        self._seen_stems = seen_stems
        self._thumbnails = []
        self._img_paths = []
        self._card_rects = []
        self._display_names = []

        for i, stem in enumerate(self._seen_stems):
            # Load image from filesystem: gameover/{result}/{stem}.png
            thumb: pygame.Surface | None = None
            result_part = stem.split("_")[0]  # "victory" or "defeat"
            img_path = GAMEOVER_IMAGES_DIR / result_part / f"{stem}.png"
            if img_path.exists():
                try:
                    raw = pygame.image.load(str(img_path)).convert()
                    thumb = pygame.transform.smoothscale(raw, (_THUMB_W, _THUMB_H))
                    self._img_paths.append(str(img_path))
                except Exception:
                    self._img_paths.append(None)
            else:
                self._img_paths.append(None)
            self._thumbnails.append(thumb)

            # Display name: look up via EndingManager, fallback to stem
            scenario = EndingManager.get_scenario_by_bg_stem(stem)
            self._display_names.append(scenario.display_name if scenario else stem)

            # Calculate grid position
            col = i % _COLS
            row = i // _COLS
            x = _POPUP_X + _THUMB_GAP + col * (_THUMB_W + _THUMB_GAP)
            y = _POPUP_Y + 60 + row * (_THUMB_H + _THUMB_GAP + 20)
            self._card_rects.append(pygame.Rect(x, y, _THUMB_W, _THUMB_H))

    @staticmethod
    def _load_seen_stems() -> list[str]:
        try:
            path = DATA_DIR / "player_data.json"
            if path.exists():
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    return data.get("seen_endings", [])
        except Exception:
            pass
        return []

    # ------------------------------------------------------------------
    # Event handling
    # ------------------------------------------------------------------

    def handle_event(self, event: pygame.event.Event) -> bool:
        """Returns True if event was consumed."""
        if not self.visible:
            return False

        if event.type == pygame.MOUSEBUTTONDOWN:
            pos = event.pos

            # Close button
            if self._close_btn.collidepoint(pos):
                self.hide()
                return True

            # Preview close (click on preview)
            if self._preview_idx >= 0:
                self._preview_idx = -1
                self._preview_surface = None
                return True

            # Card click → open preview
            for i, rect in enumerate(self._card_rects):
                if rect.collidepoint(pos):
                    self._open_preview(i)
                    return True

            # Click outside popup → close
            if not self._rect.collidepoint(pos):
                self.hide()
                return True

            return True  # inside popup, consume

        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                if self._preview_idx >= 0:
                    self._preview_idx = -1
                    self._preview_surface = None
                else:
                    self.hide()
                return True

        return self.visible

    def _open_preview(self, idx: int) -> None:
        if idx < 0 or idx >= len(self._img_paths):
            return
        path = self._img_paths[idx]
        if path is None:
            return
        try:
            raw = pygame.image.load(path).convert()
        except Exception:
            return
        # Scale to screen only if the source is not already 1280×720
        if raw.get_size() == (SCREEN_WIDTH, SCREEN_HEIGHT):
            self._preview_surface = raw
        else:
            self._preview_surface = pygame.transform.smoothscale(
                raw, (SCREEN_WIDTH, SCREEN_HEIGHT)
            )
        self._preview_idx = idx

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------

    def render(self, screen: pygame.Surface) -> None:
        if not self.visible:
            return

        # Full-screen preview mode
        if self._preview_idx >= 0 and self._preview_surface is not None:
            screen.blit(self._preview_surface, (0, 0))
            hint_font = get_font(14)
            hint = hint_font.render("클릭하여 닫기", True, WHITE)
            screen.blit(
                hint,
                hint.get_rect(center=(SCREEN_WIDTH // 2, SCREEN_HEIGHT - 30)),
            )
            return

        # Dim overlay
        overlay = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 160))
        screen.blit(overlay, (0, 0))

        # Popup background
        popup_surf = pygame.Surface(
            (self._rect.width, self._rect.height), pygame.SRCALPHA
        )
        pygame.draw.rect(
            popup_surf, (20, 30, 55, 245), popup_surf.get_rect(), border_radius=14
        )
        pygame.draw.rect(
            popup_surf, (80, 120, 170), popup_surf.get_rect(), width=3, border_radius=14
        )
        screen.blit(popup_surf, self._rect.topleft)

        # Title
        title_font = get_font(20, "bold")
        title = title_font.render("게임 오버 보관함", True, WHITE)
        screen.blit(
            title,
            title.get_rect(centerx=self._rect.centerx, top=self._rect.top + 14),
        )

        # Close button — use btn_close image with hover state
        from fall_in.utils.asset_manifest import AssetManifest

        btn_imgs = AssetManifest.get_loaded("buttons")
        is_hovered = self._close_btn.collidepoint(pygame.mouse.get_pos())
        close_key = "btn_close_hover" if is_hovered else "btn_close_normal"
        if close_key in btn_imgs:
            close_img = pygame.transform.smoothscale(
                btn_imgs[close_key],
                (self._close_btn.width, self._close_btn.height),
            )
            screen.blit(close_img, self._close_btn.topleft)
        else:
            pygame.draw.rect(screen, (180, 60, 60), self._close_btn, border_radius=6)
            close_font = get_font(16, "bold")
            x_text = close_font.render("✕", True, WHITE)
            screen.blit(x_text, x_text.get_rect(center=self._close_btn.center))

        if not self._seen_stems:
            # Empty state
            empty_font = get_font(15)
            empty = empty_font.render(
                "아직 해금된 게임 오버 씬이 없습니다.", True, (160, 170, 185)
            )
            screen.blit(empty, empty.get_rect(center=self._rect.center))
            return

        # Thumbnail grid
        name_font = get_font(13, "bold")

        for thumb, rect, label in zip(
            self._thumbnails, self._card_rects, self._display_names
        ):
            # Card background
            pygame.draw.rect(screen, (35, 50, 80), rect, border_radius=8)
            pygame.draw.rect(screen, (70, 100, 150), rect, width=1, border_radius=8)

            if thumb is not None:
                screen.blit(thumb, rect.topleft)
                pygame.draw.rect(screen, (70, 100, 150), rect, width=1, border_radius=8)
            else:
                # Placeholder
                placeholder_font = get_font(12)
                ph = placeholder_font.render("이미지 없음", True, (100, 110, 130))
                screen.blit(ph, ph.get_rect(center=rect.center))

            # Label below card
            name_surf = name_font.render(label, True, WHITE)
            screen.blit(
                name_surf,
                name_surf.get_rect(centerx=rect.centerx, top=rect.bottom + 4),
            )
