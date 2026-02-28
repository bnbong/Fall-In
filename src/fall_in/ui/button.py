"""
Button UI Component — supports image-based and fallback rendering.

Loads button assets from assets/images/ui/buttons/ with normal/hover/pressed states.
Falls back to pygame.draw rendering if images are not found.
"""

from typing import Callable, Optional

import pygame

from fall_in.config import AIR_FORCE_BLUE, WHITE, LIGHT_BLUE
from fall_in.utils.asset_loader import get_font


class Button:
    """
    Clickable button UI component.
    Supports image-based rendering with normal/hover/pressed states.
    """

    # Shared cached button images {(size_key, state): Surface}
    _image_cache: dict[tuple[str, str], pygame.Surface] = {}
    _cache_initialized: bool = False

    @classmethod
    def _init_image_cache(cls) -> None:
        """Load button images into cache (lazy, one-time)."""
        if cls._cache_initialized:
            return

        from fall_in.utils.asset_manifest import AssetManifest

        loaded = AssetManifest.get_loaded("buttons")
        size_keys = ["large", "small", "circle"]
        states = ["normal", "hover", "pressed"]

        for size_key in size_keys:
            for state in states:
                manifest_key = f"btn_{size_key}_{state}"
                if manifest_key in loaded:
                    cls._image_cache[(size_key, state)] = loaded[manifest_key]

        cls._cache_initialized = True

    def __init__(
        self,
        x: int,
        y: int,
        width: int,
        height: int,
        text: str,
        callback: Optional[Callable] = None,
        font_size: int = 24,
        bg_color: tuple = AIR_FORCE_BLUE,
        hover_color: tuple = LIGHT_BLUE,
        text_color: tuple = WHITE,
        size_key: str = "auto",
    ):
        self.rect = pygame.Rect(x, y, width, height)
        self.text = text
        self.callback = callback
        self.font_size = font_size
        self.bg_color = bg_color
        self.hover_color = hover_color
        self.text_color = text_color

        self.is_hovered = False
        self.is_pressed = False
        self._was_hovered = False

        # Determine which image set to use
        if size_key == "auto":
            if width == height:
                self.size_key = "circle"
            elif width >= 160:
                self.size_key = "large"
            else:
                self.size_key = "small"
        else:
            self.size_key = size_key

        # Lazy-load images
        self._init_image_cache()

        # Pre-scale images for this button's size
        self._scaled_images: dict[str, pygame.Surface] = {}
        self._prepare_scaled_images()

    def _prepare_scaled_images(self) -> None:
        """Scale cached button images to this button's rect size."""
        for state in ["normal", "hover", "pressed"]:
            cache_key = (self.size_key, state)
            if cache_key in self._image_cache:
                src = self._image_cache[cache_key]
                scaled = pygame.transform.smoothscale(
                    src, (self.rect.width, self.rect.height)
                )
                self._scaled_images[state] = scaled

    @property
    def _use_images(self) -> bool:
        """Whether we have at least a normal image to render."""
        return "normal" in self._scaled_images

    def handle_event(self, event: pygame.event.Event) -> None:
        """Handle mouse events"""
        if event.type == pygame.MOUSEMOTION:
            self.is_hovered = self.rect.collidepoint(event.pos)
            if self.is_hovered and not self._was_hovered:
                from fall_in.core.audio_manager import AudioManager

                AudioManager().play_sfx("sfx/cursor.wav")
            self._was_hovered = self.is_hovered

        elif event.type == pygame.MOUSEBUTTONDOWN:
            if event.button == 1 and self.is_hovered:
                self.is_pressed = True

        elif event.type == pygame.MOUSEBUTTONUP:
            if event.button == 1 and self.is_pressed and self.is_hovered:
                if self.callback:
                    from fall_in.core.audio_manager import AudioManager

                    AudioManager().play_sfx("sfx/confirm.wav")
                    self.callback()
            self.is_pressed = False

    def update(self, dt: float) -> None:
        """Update button state"""
        pass

    def render(self, screen: pygame.Surface) -> None:
        """Render button — image-based or fallback."""
        if self._use_images:
            self._render_image(screen)
        else:
            self._render_fallback(screen)

        # Draw text on top (always)
        font = get_font(self.font_size)
        text_surface = font.render(self.text, True, self.text_color)
        text_rect = text_surface.get_rect(center=self.rect.center)
        screen.blit(text_surface, text_rect)

    def _render_image(self, screen: pygame.Surface) -> None:
        """Render with loaded image assets."""
        if self.is_pressed and "pressed" in self._scaled_images:
            img = self._scaled_images["pressed"]
        elif self.is_hovered and "hover" in self._scaled_images:
            img = self._scaled_images["hover"]
        else:
            img = self._scaled_images["normal"]

        screen.blit(img, self.rect.topleft)

    def _render_fallback(self, screen: pygame.Surface) -> None:
        """Render with pygame.draw primitives (original behavior)."""
        color = self.hover_color if self.is_hovered else self.bg_color
        pygame.draw.rect(screen, color, self.rect, border_radius=8)
        pygame.draw.rect(screen, WHITE, self.rect, width=2, border_radius=8)
