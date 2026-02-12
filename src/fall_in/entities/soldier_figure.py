"""
Soldier Figure - Visual representation of a soldier on the isometric board.

Supports sprite sheets with body-type-aware sizing, drop animation
with easing, and triggers dust/shake effects on landing.

Body Type System:
- NORMAL: Standard soldier physique (default, 960×252 sprite sheets)
- SMALL:  Petite soldiers (smaller display, TBD sprite sheets)
- LARGE:  Bulky soldiers (wider display, e.g. 1020×252 sheets)

Each figure instance determines its body type from the card data
(explicit body_type field) or falls back to a danger-level mapping.
"""

from typing import Optional

import pygame

from fall_in.core.card import Card
from fall_in.utils.asset_loader import AssetLoader, get_font
from fall_in.config import (
    AIR_FORCE_BLUE,
    WHITE,
    BodyType,
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
    FIGURE_BODY_TYPE_DIMENSIONS,
    FIGURE_BODY_TYPE_OFFSET_Y,
    FIGURE_BODY_TYPE_SHADOW_RADIUS,
    FIGURE_DANGER_BODY_TYPE,
    DUST_PARTICLE_COUNT,
    SCREEN_SHAKE_INTENSITY,
)


def _determine_body_type(card: Card) -> str:
    """
    Determine body type for a card.

    Priority:
    1. Explicit body_type on the card (from soldier data)
    2. Danger-level based default mapping
    3. NORMAL fallback
    """
    if card.body_type:
        return card.body_type
    return FIGURE_DANGER_BODY_TYPE.get(card.danger, BodyType.NORMAL)


def _get_display_dimensions(body_type: str) -> tuple[int, int]:
    """Get (width, height) display dimensions for a body type."""
    return FIGURE_BODY_TYPE_DIMENSIONS.get(
        body_type, (FIGURE_DISPLAY_WIDTH, FIGURE_DISPLAY_HEIGHT)
    )


def _get_shadow_radius(body_type: str) -> int:
    """Get shadow ellipse radius for a body type."""
    return FIGURE_BODY_TYPE_SHADOW_RADIUS.get(body_type, FIGURE_SHADOW_RADIUS)


def _get_offset_y(body_type: str) -> int:
    """Get vertical tile-anchoring offset for a body type."""
    return FIGURE_BODY_TYPE_OFFSET_Y.get(body_type, FIGURE_OFFSET_Y)


class SoldierFigure:
    """
    Visual representation of a soldier card on the isometric board.

    Sprite frames are cached in two layers:
    - Raw frames: original resolution extracted from sprite sheets.
    - Scaled frames: resized to body-type-specific display dimensions.
    """

    # --- Class-level sprite caches ---
    # Raw (unscaled) mob sprite frames: {danger_level: [raw_frames]}
    _raw_mob_sprites: dict[int, list[pygame.Surface]] = {}
    # Scaled mob sprites: {(danger_level, body_type): [scaled_frames]}
    _scaled_mob_cache: dict[tuple[int, str], list[pygame.Surface]] = {}

    # Raw individual soldier sprites: {soldier_id: [raw_frames]}
    _raw_soldier_sprites: dict[int, list[pygame.Surface]] = {}
    # Scaled individual sprites: {(soldier_id, body_type): [scaled_frames]}
    _scaled_soldier_cache: dict[tuple[int, str], list[pygame.Surface]] = {}

    _initialized: bool = False
    _loader: Optional[AssetLoader] = None

    # ------------------------------------------------------------------
    # Class methods: sprite loading and caching
    # ------------------------------------------------------------------

    @classmethod
    def initialize(cls) -> None:
        """Load and cache raw mob sprite sheets for each danger level."""
        if cls._initialized:
            return

        cls._loader = AssetLoader()

        for danger in [1, 2, 3, 5, 7]:
            try:
                sprite_path = f"sprites/figure_mob_danger_{danger}.png"
                sheet = cls._loader.load_image(sprite_path)
                raw_frames = cls._extract_raw_frames(sheet)
                cls._raw_mob_sprites[danger] = raw_frames
            except Exception:
                pass

        cls._initialized = True

    @classmethod
    def _extract_raw_frames(cls, sheet: pygame.Surface) -> list[pygame.Surface]:
        """Extract animation frames from a horizontal sprite sheet (no scaling)."""
        sheet_width = sheet.get_width()
        sheet_height = sheet.get_height()
        frame_width = sheet_width // FIGURE_SPRITE_FRAMES

        frames = []
        for i in range(FIGURE_SPRITE_FRAMES):
            frame_rect = pygame.Rect(i * frame_width, 0, frame_width, sheet_height)
            frame = sheet.subsurface(frame_rect).copy()
            frames.append(frame)

        return frames

    @classmethod
    def _scale_frames(
        cls, raw_frames: list[pygame.Surface], width: int, height: int
    ) -> list[pygame.Surface]:
        """Scale a list of raw frames to the given dimensions."""
        return [
            pygame.transform.smoothscale(frame, (width, height)) for frame in raw_frames
        ]

    @classmethod
    def _get_mob_frames(
        cls, danger: int, body_type: str
    ) -> Optional[list[pygame.Surface]]:
        """
        Get scaled mob sprite frames for a danger level and body type.
        Uses two-layer caching: raw -> scaled.
        """
        cls.initialize()

        cache_key = (danger, body_type)
        if cache_key in cls._scaled_mob_cache:
            return cls._scaled_mob_cache[cache_key]

        # Find the best matching raw frames
        danger_key = cls._resolve_danger_key(danger)
        if danger_key is None:
            return None

        raw_frames = cls._raw_mob_sprites[danger_key]
        width, height = _get_display_dimensions(body_type)
        scaled = cls._scale_frames(raw_frames, width, height)
        cls._scaled_mob_cache[cache_key] = scaled
        return scaled

    @classmethod
    def _resolve_danger_key(cls, danger: int) -> Optional[int]:
        """Find the closest available danger level for mob sprites."""
        if danger in cls._raw_mob_sprites:
            return danger

        # Fallback chain
        if danger <= 1:
            return 1 if 1 in cls._raw_mob_sprites else None
        elif danger <= 2:
            for key in [2, 1]:
                if key in cls._raw_mob_sprites:
                    return key
        elif danger <= 3:
            for key in [3, 1]:
                if key in cls._raw_mob_sprites:
                    return key
        elif danger <= 5:
            for key in [5, 3]:
                if key in cls._raw_mob_sprites:
                    return key
        else:
            for key in [7, 5]:
                if key in cls._raw_mob_sprites:
                    return key

        # Last resort: any available
        return next(iter(cls._raw_mob_sprites), None)

    @classmethod
    def _load_soldier_sprite(
        cls, soldier_id: int, body_type: str
    ) -> Optional[list[pygame.Surface]]:
        """Lazy load and scale individual soldier sprite."""
        cache_key = (soldier_id, body_type)
        if cache_key in cls._scaled_soldier_cache:
            return cls._scaled_soldier_cache[cache_key]

        # Check raw cache first
        if soldier_id not in cls._raw_soldier_sprites:
            if cls._loader is None:
                cls._loader = AssetLoader()

            try:
                sprite_path = f"sprites/figure_soldier_{soldier_id}.png"
                sheet = cls._loader.load_image(sprite_path)
                raw_frames = cls._extract_raw_frames(sheet)
                cls._raw_soldier_sprites[soldier_id] = raw_frames
            except Exception:
                return None

        raw_frames = cls._raw_soldier_sprites[soldier_id]
        width, height = _get_display_dimensions(body_type)
        scaled = cls._scale_frames(raw_frames, width, height)
        cls._scaled_soldier_cache[cache_key] = scaled
        return scaled

    @classmethod
    def get_sprite_for_danger(
        cls, danger: int, frame: int, body_type: str = BodyType.NORMAL
    ) -> Optional[pygame.Surface]:
        """Get a single sprite frame for a danger level and body type."""
        frames = cls._get_mob_frames(danger, body_type)
        if frames:
            return frames[frame % len(frames)]
        return None

    @classmethod
    def get_sprite_for_card(
        cls, card: Card, frame: int, body_type: Optional[str] = None
    ) -> Optional[pygame.Surface]:
        """
        Get a single sprite frame for a card.
        Uses individual soldier sprite if collected, mob sprite otherwise.
        """
        cls.initialize()
        bt = body_type or _determine_body_type(card)

        if card.is_collected:
            frames = cls._load_soldier_sprite(card.number, bt)
            if frames:
                return frames[frame % len(frames)]

        return cls.get_sprite_for_danger(card.danger, frame, bt)

    # ------------------------------------------------------------------
    # Instance: per-figure animation and rendering
    # ------------------------------------------------------------------

    def __init__(self, card: Card):
        self.card = card
        self.body_type = _determine_body_type(card)

        # Resolved display dimensions for this figure
        self.display_width, self.display_height = _get_display_dimensions(
            self.body_type
        )
        self.shadow_radius = _get_shadow_radius(self.body_type)
        self.offset_y = _get_offset_y(self.body_type)

        # Animation state
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
        """Render soldier figure at isometric position, sized by body type."""
        base_y = iso_y - tile_height // 4
        figure_y = base_y - self.display_height + self.offset_y

        drop_offset = self.get_current_y_offset()
        figure_y -= drop_offset

        sprite = self.get_sprite_for_card(
            self.card, self.animation_frame, self.body_type
        )
        adjusted_iso_x = iso_x + FIGURE_OFFSET_X

        if sprite:
            if drop_offset < FIGURE_SHADOW_VISIBILITY_THRESHOLD:
                shadow_alpha = int(
                    255 * (1 - drop_offset / FIGURE_SHADOW_VISIBILITY_THRESHOLD)
                )
                self._draw_shadow(screen, adjusted_iso_x, iso_y, shadow_alpha)

            sprite_x = adjusted_iso_x - self.display_width // 2
            screen.blit(sprite, (sprite_x, figure_y))
        else:
            self._render_placeholder(screen, adjusted_iso_x, figure_y, tile_height)

        self._draw_number(screen, adjusted_iso_x, figure_y)

    def _draw_shadow(
        self, screen: pygame.Surface, iso_x: int, iso_y: int, alpha: int = 255
    ) -> None:
        """Draw elliptical shadow on ground, sized by body type."""
        r = self.shadow_radius
        shadow_surface = pygame.Surface((r * 2, r), pygame.SRCALPHA)
        pygame.draw.ellipse(
            shadow_surface,
            (30, 30, 30, min(alpha, 100)),
            (0, 0, r * 2, r),
        )
        screen.blit(shadow_surface, (iso_x - r, iso_y - r // 2))

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
        pw = max(20, self.display_width // 3)
        ph = max(30, self.display_height // 2)
        body_rect = pygame.Rect(iso_x - pw // 2, figure_y + 10, pw, ph)
        pygame.draw.rect(screen, (100, 150, 100), body_rect, border_radius=5)
        pygame.draw.rect(screen, AIR_FORCE_BLUE, body_rect, width=2, border_radius=5)


def render_soldier_placeholder(
    screen: pygame.Surface, card: Card, iso_x: int, iso_y: int
) -> None:
    """Convenience function to render a soldier figure."""
    figure = SoldierFigure(card)
    figure.render(screen, iso_x, iso_y)
