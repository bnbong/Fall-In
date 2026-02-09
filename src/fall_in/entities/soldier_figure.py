"""
Soldier Figure - Visual representation of a soldier on the isometric board.

Supports sprite sheets, drop animation with easing, and
triggers dust/shake effects on landing.
"""

from typing import Optional

import pygame

from fall_in.core.card import Card
from fall_in.utils.asset_loader import AssetLoader, get_font
from fall_in.config import (
    AIR_FORCE_BLUE,
    WHITE,
    FIGURE_SPRITE_FRAMES,
    FIGURE_DISPLAY_WIDTH,
    FIGURE_DISPLAY_HEIGHT,
    FIGURE_DROP_DURATION,
    FIGURE_DROP_HEIGHT,
    FIGURE_OFFSET_X,
    FIGURE_OFFSET_Y,
    FIGURE_SHADOW_RADIUS,
    FIGURE_SHADOW_VISIBILITY_THRESHOLD,
    FIGURE_NUMBER_FONT_SIZE,
    DUST_PARTICLE_COUNT,
    SCREEN_SHAKE_INTENSITY,
)


class SoldierFigure:
    """
    Visual representation of a soldier card on the isometric board.
    Supports sprite sheets with drop animation and dust effects.
    """

    # Cached sprite sheets: {danger_level: [frames]}
    _mob_sprites: dict[int, list[pygame.Surface]] = {}
    # Cached individual soldier sprites: {soldier_id: [frames]}
    _soldier_sprites: dict[int, list[pygame.Surface]] = {}
    _initialized: bool = False
    _loader: Optional[AssetLoader] = None

    @classmethod
    def initialize(cls) -> None:
        """Load and cache sprite sheets."""
        if cls._initialized:
            return

        cls._loader = AssetLoader()

        for danger in [1, 2, 3, 5, 7]:
            try:
                sprite_path = f"sprites/figure_mob_danger_{danger}.png"
                sheet = cls._loader.load_image(sprite_path)
                frames = cls._extract_frames(sheet)
                cls._mob_sprites[danger] = frames
            except Exception:
                pass

        cls._initialized = True

    @classmethod
    def _load_soldier_sprite(cls, soldier_id: int) -> Optional[list[pygame.Surface]]:
        """Lazy load individual soldier sprite if available."""
        if soldier_id in cls._soldier_sprites:
            return cls._soldier_sprites[soldier_id]

        if cls._loader is None:
            cls._loader = AssetLoader()

        try:
            sprite_path = f"sprites/figure_soldier_{soldier_id}.png"
            sheet = cls._loader.load_image(sprite_path)
            frames = cls._extract_frames(sheet)
            cls._soldier_sprites[soldier_id] = frames
            return frames
        except Exception:
            return None

    @classmethod
    def _extract_frames(cls, sheet: pygame.Surface) -> list[pygame.Surface]:
        """Extract animation frames from a horizontal sprite sheet."""
        sheet_width = sheet.get_width()
        sheet_height = sheet.get_height()
        frame_width = sheet_width // FIGURE_SPRITE_FRAMES

        frames = []
        for i in range(FIGURE_SPRITE_FRAMES):
            frame_rect = pygame.Rect(i * frame_width, 0, frame_width, sheet_height)
            frame = sheet.subsurface(frame_rect).copy()
            scaled = pygame.transform.smoothscale(
                frame, (FIGURE_DISPLAY_WIDTH, FIGURE_DISPLAY_HEIGHT)
            )
            frames.append(scaled)

        return frames

    @classmethod
    def get_sprite_for_danger(cls, danger: int, frame: int) -> Optional[pygame.Surface]:
        """Get sprite frame for a given danger level."""
        cls.initialize()

        danger_key = danger
        if danger not in cls._mob_sprites:
            if danger <= 1:
                danger_key = 1
            elif danger <= 2:
                danger_key = 2 if 2 in cls._mob_sprites else 1
            elif danger <= 3:
                danger_key = 3 if 3 in cls._mob_sprites else 1
            elif danger <= 5:
                danger_key = 5 if 5 in cls._mob_sprites else 3
            else:
                danger_key = 7 if 7 in cls._mob_sprites else 5

        if danger_key in cls._mob_sprites:
            frames = cls._mob_sprites[danger_key]
            return frames[frame % len(frames)]
        return None

    @classmethod
    def get_sprite_for_card(cls, card: Card, frame: int) -> Optional[pygame.Surface]:
        """Get sprite frame for a card (individual if collected, mob otherwise)."""
        cls.initialize()

        if card.is_collected:
            frames = cls._load_soldier_sprite(card.number)
            if frames:
                return frames[frame % len(frames)]

        return cls.get_sprite_for_danger(card.danger, frame)

    def __init__(self, card: Card):
        self.card = card
        self.animation_frame = 0
        self.animation_timer = 0.0

        # Drop animation state
        self.is_dropping = False
        self.drop_progress = 0.0
        self.drop_start_y = 0
        self.target_y = 0

        # Landing effects
        self.has_landed = False
        self.pending_dust_spawn = False
        self.pending_shake = False

    def start_drop(self, target_y: int) -> None:
        """Start drop animation to target Y position."""
        self.is_dropping = True
        self.drop_progress = 0.0
        self.drop_start_y = target_y - FIGURE_DROP_HEIGHT
        self.target_y = target_y
        self.has_landed = False
        self.pending_dust_spawn = False
        self.pending_shake = False

    def get_dust_count(self) -> int:
        """Get number of dust particles based on danger."""
        danger = min(7, max(1, self.card.danger))
        return DUST_PARTICLE_COUNT.get(danger, 5)

    def get_shake_intensity(self) -> int:
        """Get screen shake intensity based on danger."""
        danger = min(7, max(1, self.card.danger))
        return SCREEN_SHAKE_INTENSITY.get(danger, 0)

    def update(self, dt: float) -> tuple[bool, bool]:
        """
        Update animation state.

        Returns:
            (spawn_dust, trigger_shake) flags.
        """
        self.animation_timer += dt
        self.animation_frame = int(self.animation_timer * 4) % FIGURE_SPRITE_FRAMES

        spawn_dust = False
        trigger_shake = False

        if self.is_dropping:
            self.drop_progress += dt / FIGURE_DROP_DURATION

            if self.drop_progress >= 1.0:
                self.drop_progress = 1.0
                self.is_dropping = False

                if not self.has_landed:
                    self.has_landed = True
                    spawn_dust = True
                    trigger_shake = self.get_shake_intensity() > 0

        return spawn_dust, trigger_shake

    def get_current_y_offset(self) -> int:
        """Get current Y offset for drop animation."""
        if not self.is_dropping and self.has_landed:
            return 0

        if self.is_dropping:
            t = self.drop_progress
            eased = 1 - (1 - t) ** 3  # Ease-out cubic
            return int(FIGURE_DROP_HEIGHT * (1 - eased))

        return FIGURE_DROP_HEIGHT  # Before drop starts

    def render(
        self, screen: pygame.Surface, iso_x: int, iso_y: int, tile_height: int = 30
    ) -> None:
        """Render soldier figure at isometric position."""
        base_y = iso_y - tile_height // 4
        figure_y = base_y - FIGURE_DISPLAY_HEIGHT + FIGURE_OFFSET_Y

        drop_offset = self.get_current_y_offset()
        figure_y -= drop_offset

        sprite = self.get_sprite_for_card(self.card, self.animation_frame)
        adjusted_iso_x = iso_x + FIGURE_OFFSET_X

        if sprite:
            if drop_offset < FIGURE_SHADOW_VISIBILITY_THRESHOLD:
                shadow_alpha = int(
                    255 * (1 - drop_offset / FIGURE_SHADOW_VISIBILITY_THRESHOLD)
                )
                self._draw_shadow(screen, adjusted_iso_x, iso_y, shadow_alpha)

            sprite_x = adjusted_iso_x - FIGURE_DISPLAY_WIDTH // 2
            screen.blit(sprite, (sprite_x, figure_y))
        else:
            self._render_placeholder(screen, adjusted_iso_x, figure_y, tile_height)

        self._draw_number(screen, adjusted_iso_x, figure_y)

    def _draw_shadow(
        self, screen: pygame.Surface, iso_x: int, iso_y: int, alpha: int = 255
    ) -> None:
        """Draw elliptical shadow on ground."""
        shadow_surface = pygame.Surface(
            (FIGURE_SHADOW_RADIUS * 2, FIGURE_SHADOW_RADIUS), pygame.SRCALPHA
        )
        pygame.draw.ellipse(
            shadow_surface,
            (30, 30, 30, min(alpha, 100)),
            (0, 0, FIGURE_SHADOW_RADIUS * 2, FIGURE_SHADOW_RADIUS),
        )
        screen.blit(
            shadow_surface,
            (iso_x - FIGURE_SHADOW_RADIUS, iso_y - FIGURE_SHADOW_RADIUS // 2),
        )

    def _draw_number(self, screen: pygame.Surface, iso_x: int, figure_y: int) -> None:
        """Draw card number above figure."""
        font = get_font(FIGURE_NUMBER_FONT_SIZE, "bold")
        number_text = font.render(str(self.card.number), True, WHITE)

        text_rect = number_text.get_rect(center=(iso_x, figure_y - 5))
        bg_rect = text_rect.inflate(6, 2)
        pygame.draw.rect(screen, AIR_FORCE_BLUE, bg_rect, border_radius=3)
        screen.blit(number_text, text_rect)

    def _render_placeholder(
        self, screen: pygame.Surface, iso_x: int, figure_y: int, tile_height: int
    ) -> None:
        """Fallback placeholder rendering when sprite not available."""
        body_rect = pygame.Rect(iso_x - 14, figure_y + 10, 28, 40)
        pygame.draw.rect(screen, (100, 150, 100), body_rect, border_radius=5)
        pygame.draw.rect(screen, AIR_FORCE_BLUE, body_rect, width=2, border_radius=5)


def render_soldier_placeholder(
    screen: pygame.Surface, card: Card, iso_x: int, iso_y: int
) -> None:
    """Convenience function to render a soldier figure."""
    figure = SoldierFigure(card)
    figure.render(screen, iso_x, iso_y)
