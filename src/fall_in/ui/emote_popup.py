"""
EmotePopup — in-game emote palette (PR-07).

Opens when the local player clicks their profile icon in the top bar.
Displays a 4×2 grid of emoji buttons.  Selecting one calls the registered
callback with the emote_id slug and closes the palette immediately.

The popup is cosmetic-only: no free text, no targeted pings.
All emote slugs match the server-side VALID_EMOTE_IDS catalog.

Usage (from GameScene or a multiplayer wrapper)::

    popup = EmotePopup()
    popup.set_callback(lambda eid: ws_client.send_emote(eid))

    # In handle_event:
    if popup.handle_event(event):
        return  # event consumed

    # In render:
    popup.render(screen)

Asset fallback
--------------
Each emote button uses an emoji character as its label.  If a future
``emotes/<slug>.png`` asset is added to the manifest, it is used instead.
The popup is fully functional without any image assets.
"""

from __future__ import annotations

from typing import Callable, Optional

import pygame

from fall_in.config import (
    SCREEN_HEIGHT,
    SCREEN_WIDTH,
    WHITE,
)
from fall_in.utils.asset_loader import get_font

# ---------------------------------------------------------------------------
# Emote catalog — must match server-side VALID_EMOTE_IDS
# ---------------------------------------------------------------------------

# (emote_id, emoji_label, korean_label)
EMOTE_CATALOG: list[tuple[str, str, str]] = [
    ("thumbsup", "👍", "좋아요"),
    ("thumbsdown", "👎", "별로"),
    ("smile", "😄", "웃음"),
    ("sweat", "😅", "땀"),
    ("thinking", "🤔", "생각"),
    ("fire", "🔥", "열정"),
    ("cry", "😭", "눈물"),
    ("clap", "👏", "박수"),
]

# Grid layout
_COLS = 4
_ROWS = 2
_BTN_W = 72
_BTN_H = 72
_GAP = 8
_PADDING = 14

_POPUP_W = _COLS * _BTN_W + (_COLS - 1) * _GAP + _PADDING * 2
_POPUP_H = _ROWS * _BTN_H + (_ROWS - 1) * _GAP + _PADDING * 2 + 28  # +28 title bar


class EmotePopup:
    """
    Small floating palette for emote selection.

    State machine: hidden ↔ visible.
    """

    def __init__(self) -> None:
        self.visible: bool = False
        self._callback: Optional[Callable[[str], None]] = None

        # Will be set to the screen-space rect when show() is called
        self._rect = pygame.Rect(0, 0, _POPUP_W, _POPUP_H)

        # Hovered button index (0-7), or None
        self._hovered: Optional[int] = None

        # Emote image cache (lazy-loaded from asset manifest)
        self._emote_images: dict[str, pygame.Surface] = {}
        self._images_loaded: bool = False

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_callback(self, callback: Callable[[str], None]) -> None:
        """Register a function to call when the player picks an emote."""
        self._callback = callback

    def show(self, anchor: tuple[int, int]) -> None:
        """
        Open the palette anchored below *anchor* (the profile icon center).

        The popup is kept within screen bounds.
        """
        x = anchor[0] - _POPUP_W // 2
        y = anchor[1] + 10  # below the icon

        # Keep within screen
        x = max(4, min(x, SCREEN_WIDTH - _POPUP_W - 4))
        y = max(4, min(y, SCREEN_HEIGHT - _POPUP_H - 4))

        self._rect.topleft = (x, y)
        self.visible = True
        self._hovered = None

    def hide(self) -> None:
        self.visible = False

    def toggle(self, anchor: tuple[int, int]) -> None:
        if self.visible:
            self.hide()
        else:
            self.show(anchor)

    # ------------------------------------------------------------------
    # Event handling
    # ------------------------------------------------------------------

    def handle_event(self, event: pygame.event.Event) -> bool:
        """
        Handle a pygame event.  Returns True only if the event was consumed
        (i.e. it should NOT propagate to gameplay logic).

        Policy:
          - Clicks ON a button → consumed (send emote + close).
          - Clicks inside the popup frame but not on a button → consumed
            (prevent accidental card clicks through the panel).
          - Clicks OUTSIDE the popup → close, but NOT consumed so that the
            underlying gameplay click still registers.
          - Mouse motion → update hover highlight, never consumed.
          - Escape → close, consumed.
          - All other events → not consumed (gameplay receives them normally).
        """
        if not self.visible:
            return False

        if event.type == pygame.MOUSEMOTION:
            self._hovered = self._hit_test(event.pos)
            # Motion is never consumed — the cursor should still drive card hover
            return False

        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            idx = self._hit_test(event.pos)
            if idx is not None:
                # Clicked an emote button — send and close
                emote_id, _, _ = EMOTE_CATALOG[idx]
                self.hide()
                if self._callback is not None:
                    self._callback(emote_id)
                return True
            if self._rect.collidepoint(event.pos):
                # Clicked inside the popup frame but not on a button — absorb
                return True
            # Clicked outside the popup → close, but pass event through so
            # gameplay (e.g. card selection) still receives the click.
            self.hide()
            return False

        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            self.hide()
            return True

        # All other event types do not affect the popup and must not be eaten
        return False

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------

    def render(self, screen: pygame.Surface) -> None:
        if not self.visible:
            return

        self._ensure_images_loaded()

        # Background panel
        panel = pygame.Surface((_POPUP_W, _POPUP_H), pygame.SRCALPHA)
        pygame.draw.rect(
            panel,
            (20, 35, 60, 230),
            (0, 0, _POPUP_W, _POPUP_H),
            border_radius=10,
        )
        pygame.draw.rect(
            panel,
            (70, 120, 180),
            (0, 0, _POPUP_W, _POPUP_H),
            width=2,
            border_radius=10,
        )
        screen.blit(panel, self._rect.topleft)

        # Title bar
        title_font = get_font(12, "bold")
        title = title_font.render("이모티콘 선택", True, (180, 200, 220))
        screen.blit(
            title,
            title.get_rect(
                centerx=self._rect.centerx,
                top=self._rect.top + 6,
            ),
        )

        # Emote buttons
        emoji_font = get_font(28)
        label_font = get_font(10)

        for idx, (emote_id, emoji, label_ko) in enumerate(EMOTE_CATALOG):
            btn_rect = self._button_rect(idx)
            is_hovered = self._hovered == idx

            # Button background
            bg_color = (60, 90, 140, 220) if is_hovered else (35, 55, 90, 200)
            btn_surf = pygame.Surface(
                (btn_rect.width, btn_rect.height), pygame.SRCALPHA
            )
            pygame.draw.rect(
                btn_surf,
                bg_color,
                (0, 0, btn_rect.width, btn_rect.height),
                border_radius=8,
            )
            border_color = (120, 170, 230) if is_hovered else (60, 90, 130)
            pygame.draw.rect(
                btn_surf,
                border_color,
                (0, 0, btn_rect.width, btn_rect.height),
                width=2,
                border_radius=8,
            )
            screen.blit(btn_surf, btn_rect.topleft)

            # Emote image — use PNG if available, else emoji text
            drawn_image = False
            if emote_id in self._emote_images:
                img = self._emote_images[emote_id]
                img_scaled = pygame.transform.smoothscale(img, (36, 36))
                img_rect = img_scaled.get_rect(
                    centerx=btn_rect.centerx,
                    top=btn_rect.top + 8,
                )
                screen.blit(img_scaled, img_rect)
                drawn_image = True

            if not drawn_image:
                emoji_surf = emoji_font.render(emoji, True, WHITE)
                screen.blit(
                    emoji_surf,
                    emoji_surf.get_rect(
                        centerx=btn_rect.centerx,
                        top=btn_rect.top + 8,
                    ),
                )

            # Korean label below emoji
            label_surf = label_font.render(label_ko, True, (190, 205, 220))
            screen.blit(
                label_surf,
                label_surf.get_rect(
                    centerx=btn_rect.centerx,
                    bottom=btn_rect.bottom - 4,
                ),
            )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _button_rect(self, idx: int) -> pygame.Rect:
        """Return the screen-space Rect for button at index *idx*."""
        row = idx // _COLS
        col = idx % _COLS
        x = self._rect.x + _PADDING + col * (_BTN_W + _GAP)
        y = self._rect.y + _PADDING + 20 + row * (_BTN_H + _GAP)  # 20 = title bar
        return pygame.Rect(x, y, _BTN_W, _BTN_H)

    def _hit_test(self, pos: tuple[int, int]) -> Optional[int]:
        """Return the button index under *pos*, or None."""
        for idx in range(len(EMOTE_CATALOG)):
            if self._button_rect(idx).collidepoint(pos):
                return idx
        return None

    def _ensure_images_loaded(self) -> None:
        """Lazy-load emote PNG assets from the asset manifest (if present)."""
        if self._images_loaded:
            return
        self._images_loaded = True
        try:
            from fall_in.utils.asset_manifest import AssetManifest

            emote_assets = AssetManifest.get_loaded("emotes")
            for emote_id, _, _ in EMOTE_CATALOG:
                if emote_id in emote_assets:
                    self._emote_images[emote_id] = emote_assets[emote_id]
        except Exception:
            # Asset manifest may not have an "emotes" category yet — silent fallback
            pass
