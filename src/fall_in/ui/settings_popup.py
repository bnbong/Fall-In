"""
SettingsPopup - Overlay popup for volume controls and bug reporting.

Can be used from any scene by composing it into the scene class.
"""

import webbrowser

import pygame

from fall_in.utils.asset_loader import get_font
from fall_in.config import (
    SCREEN_WIDTH,
    SCREEN_HEIGHT,
    AIR_FORCE_BLUE,
    WHITE,
    GITHUB_ISSUES_URL,
)


class SettingsPopup:
    """Modal settings popup with volume sliders and bug report button."""

    POPUP_WIDTH = 400
    POPUP_HEIGHT = 340
    SLIDER_WIDTH = 250
    SLIDER_HEIGHT = 8
    HANDLE_RADIUS = 10

    def __init__(self) -> None:
        self.visible = False

        # Popup rect (centered on screen)
        self.rect = pygame.Rect(
            (SCREEN_WIDTH - self.POPUP_WIDTH) // 2,
            (SCREEN_HEIGHT - self.POPUP_HEIGHT) // 2,
            self.POPUP_WIDTH,
            self.POPUP_HEIGHT,
        )

        # Slider positions (relative to popup)
        self._bgm_slider_y = 110
        self._sfx_slider_y = 180
        self._slider_x = (self.POPUP_WIDTH - self.SLIDER_WIDTH) // 2

        # Close button rect (top-right of popup)
        self._close_btn = pygame.Rect(self.rect.right - 36, self.rect.top + 8, 28, 28)

        # Bug report button rect (bottom center)
        self._bug_btn = pygame.Rect(
            self.rect.centerx - 80, self.rect.bottom - 65, 160, 36
        )

        # Dragging state
        self._dragging_bgm = False
        self._dragging_sfx = False

    def toggle(self) -> None:
        """Toggle popup visibility."""
        from fall_in.core.audio_manager import AudioManager

        if self.visible:
            AudioManager().save_settings()
        self.visible = not self.visible

    def show(self) -> None:
        self.visible = True

    def hide(self) -> None:
        from fall_in.core.audio_manager import AudioManager

        AudioManager().save_settings()
        self.visible = False

    # ------------------------------------------------------------------
    # Event handling
    # ------------------------------------------------------------------

    def handle_event(self, event: pygame.event.Event) -> bool:
        """Handle event. Returns True if the event was consumed."""
        if not self.visible:
            return False

        if event.type == pygame.MOUSEBUTTONDOWN:
            pos = event.pos

            # Close button
            if self._close_btn.collidepoint(pos):
                self.hide()
                return True

            # Bug report button
            if self._bug_btn.collidepoint(pos):
                webbrowser.open(GITHUB_ISSUES_URL)
                return True

            # BGM slider
            bgm_handle = self._get_bgm_handle_rect()
            bgm_track = self._get_bgm_track_rect()
            if bgm_handle.collidepoint(pos) or bgm_track.collidepoint(pos):
                self._dragging_bgm = True
                self._update_bgm_from_mouse(pos[0])
                return True

            # SFX slider
            sfx_handle = self._get_sfx_handle_rect()
            sfx_track = self._get_sfx_track_rect()
            if sfx_handle.collidepoint(pos) or sfx_track.collidepoint(pos):
                self._dragging_sfx = True
                self._update_sfx_from_mouse(pos[0])
                return True

            # Click inside popup = consume but do nothing
            if self.rect.collidepoint(pos):
                return True

            # Click outside popup = close
            self.hide()
            return True

        elif event.type == pygame.MOUSEMOTION:
            if self._dragging_bgm:
                self._update_bgm_from_mouse(event.pos[0])
                return True
            if self._dragging_sfx:
                self._update_sfx_from_mouse(event.pos[0])
                return True

        elif event.type == pygame.MOUSEBUTTONUP:
            if self._dragging_bgm or self._dragging_sfx:
                self._dragging_bgm = False
                self._dragging_sfx = False
                return True

        elif event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                self.hide()
                return True

        return self.visible  # consume all events while visible

    # ------------------------------------------------------------------
    # Slider helpers
    # ------------------------------------------------------------------

    def _get_bgm_track_rect(self) -> pygame.Rect:
        return pygame.Rect(
            self.rect.x + self._slider_x,
            self.rect.y + self._bgm_slider_y - self.SLIDER_HEIGHT // 2,
            self.SLIDER_WIDTH,
            self.SLIDER_HEIGHT,
        )

    def _get_sfx_track_rect(self) -> pygame.Rect:
        return pygame.Rect(
            self.rect.x + self._slider_x,
            self.rect.y + self._sfx_slider_y - self.SLIDER_HEIGHT // 2,
            self.SLIDER_WIDTH,
            self.SLIDER_HEIGHT,
        )

    def _get_bgm_handle_rect(self) -> pygame.Rect:
        from fall_in.core.audio_manager import AudioManager

        vol = AudioManager().bgm_volume
        x = self.rect.x + self._slider_x + int(vol * self.SLIDER_WIDTH)
        y = self.rect.y + self._bgm_slider_y
        return pygame.Rect(
            x - self.HANDLE_RADIUS,
            y - self.HANDLE_RADIUS,
            self.HANDLE_RADIUS * 2,
            self.HANDLE_RADIUS * 2,
        )

    def _get_sfx_handle_rect(self) -> pygame.Rect:
        from fall_in.core.audio_manager import AudioManager

        vol = AudioManager().sfx_volume
        x = self.rect.x + self._slider_x + int(vol * self.SLIDER_WIDTH)
        y = self.rect.y + self._sfx_slider_y
        return pygame.Rect(
            x - self.HANDLE_RADIUS,
            y - self.HANDLE_RADIUS,
            self.HANDLE_RADIUS * 2,
            self.HANDLE_RADIUS * 2,
        )

    def _update_bgm_from_mouse(self, mouse_x: int) -> None:
        from fall_in.core.audio_manager import AudioManager

        track_left = self.rect.x + self._slider_x
        ratio = (mouse_x - track_left) / self.SLIDER_WIDTH
        AudioManager().bgm_volume = max(0.0, min(1.0, ratio))

    def _update_sfx_from_mouse(self, mouse_x: int) -> None:
        from fall_in.core.audio_manager import AudioManager

        track_left = self.rect.x + self._slider_x
        ratio = (mouse_x - track_left) / self.SLIDER_WIDTH
        AudioManager().sfx_volume = max(0.0, min(1.0, ratio))

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------

    def render(self, screen: pygame.Surface) -> None:
        """Render the settings popup overlay."""
        if not self.visible:
            return

        from fall_in.core.audio_manager import AudioManager

        audio = AudioManager()

        # Dim overlay
        overlay = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 140))
        screen.blit(overlay, (0, 0))

        # Popup background
        popup_surf = pygame.Surface(
            (self.POPUP_WIDTH, self.POPUP_HEIGHT), pygame.SRCALPHA
        )
        pygame.draw.rect(
            popup_surf,
            (30, 40, 60, 240),
            (0, 0, self.POPUP_WIDTH, self.POPUP_HEIGHT),
            border_radius=16,
        )
        pygame.draw.rect(
            popup_surf,
            AIR_FORCE_BLUE,
            (0, 0, self.POPUP_WIDTH, self.POPUP_HEIGHT),
            width=2,
            border_radius=16,
        )
        screen.blit(popup_surf, self.rect.topleft)

        # Title
        title_font = get_font(24, "bold")
        title = title_font.render("설정", True, WHITE)
        screen.blit(
            title,
            title.get_rect(centerx=self.rect.centerx, top=self.rect.top + 18),
        )

        # Close button (X)
        pygame.draw.rect(screen, (180, 60, 60), self._close_btn, border_radius=6)
        close_font = get_font(16, "bold")
        x_text = close_font.render("✕", True, WHITE)
        screen.blit(x_text, x_text.get_rect(center=self._close_btn.center))

        # BGM slider
        self._draw_slider(
            screen,
            "BGM 볼륨",
            self._bgm_slider_y,
            audio.bgm_volume,
        )

        # SFX slider
        self._draw_slider(
            screen,
            "SFX 볼륨",
            self._sfx_slider_y,
            audio.sfx_volume,
        )

        # Bug report button
        pygame.draw.rect(screen, (60, 80, 120), self._bug_btn, border_radius=8)
        pygame.draw.rect(
            screen, AIR_FORCE_BLUE, self._bug_btn, width=2, border_radius=8
        )
        bug_font = get_font(14)
        bug_text = bug_font.render("🐛 버그 제보", True, WHITE)
        screen.blit(bug_text, bug_text.get_rect(center=self._bug_btn.center))

    def _draw_slider(
        self,
        screen: pygame.Surface,
        label: str,
        slider_y: int,
        value: float,
    ) -> None:
        """Draw a labeled volume slider."""
        label_font = get_font(16)
        value_font = get_font(14)

        # Label
        label_surf = label_font.render(label, True, WHITE)
        screen.blit(
            label_surf,
            (self.rect.x + self._slider_x, self.rect.y + slider_y - 30),
        )

        # Value percentage
        pct = value_font.render(f"{int(value * 100)}%", True, (180, 200, 220))
        screen.blit(
            pct,
            (
                self.rect.x + self._slider_x + self.SLIDER_WIDTH + 10,
                self.rect.y + slider_y - 8,
            ),
        )

        # Track background
        track_rect = pygame.Rect(
            self.rect.x + self._slider_x,
            self.rect.y + slider_y - self.SLIDER_HEIGHT // 2,
            self.SLIDER_WIDTH,
            self.SLIDER_HEIGHT,
        )
        pygame.draw.rect(screen, (80, 90, 110), track_rect, border_radius=4)

        # Track fill
        fill_w = int(value * self.SLIDER_WIDTH)
        if fill_w > 0:
            fill_rect = pygame.Rect(
                track_rect.x, track_rect.y, fill_w, self.SLIDER_HEIGHT
            )
            pygame.draw.rect(screen, AIR_FORCE_BLUE, fill_rect, border_radius=4)

        # Handle
        handle_x = self.rect.x + self._slider_x + int(value * self.SLIDER_WIDTH)
        handle_y = self.rect.y + slider_y
        pygame.draw.circle(screen, WHITE, (handle_x, handle_y), self.HANDLE_RADIUS)
        pygame.draw.circle(
            screen, AIR_FORCE_BLUE, (handle_x, handle_y), self.HANDLE_RADIUS, 2
        )
