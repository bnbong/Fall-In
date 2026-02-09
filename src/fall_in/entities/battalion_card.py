"""
BattalionCard - Renders soldier card with portrait, danger info, and aura effects.

Handles both normal-resolution and high-resolution (hover) rendering,
portrait loading (mob fallback or individual soldier), circular masking,
and animated fire-like aura effects for high-danger cards.

TODO: Add card aura effect assets or improve the current aura effect.
"""

import math
import time
from typing import Optional

import pygame

from fall_in.core.card import Card
from fall_in.utils.asset_loader import AssetLoader, get_font
from fall_in.utils.danger_utils import get_danger_circle_color
from fall_in.config import (
    WHITE,
    BATTALION_CARD_WIDTH,
    BATTALION_CARD_HEIGHT,
    BATTALION_PORTRAIT_CENTER_X,
    BATTALION_PORTRAIT_CENTER_Y,
    BATTALION_PORTRAIT_RADIUS_RATIO,
    BATTALION_NUMBER_CIRCLE_X,
    BATTALION_NUMBER_CIRCLE_Y,
    NUMBER_CIRCLE_RADIUS,
    NUMBER_CIRCLE_FONT_SIZE,
    BATTALION_NAME_Y,
    BATTALION_RANK_Y,
    BATTALION_UNIT_Y,
    BATTALION_DANGER_Y,
    BATTALION_TEXT_FONT_SIZE,
    BATTALION_DANGER_LABELS,
    BATTALION_DETAIL_TEXT_X,
    CARD_AURA_COLORS,
    CARD_AURA_MARGIN,
    CARD_AURA_NUM_FLAMES,
    CARD_AURA_BASE_FLAME_SIZE,
    CARD_HR_SCALE,
    CARD_SELECTED_BORDER_COLOR,
    CARD_HOVER_BORDER_COLOR,
    CARD_TEXT_COLOR,
    CARD_SELECTED_BORDER_WIDTH,
    CARD_HOVER_BORDER_WIDTH,
    CARD_BORDER_RADIUS,
)


class BattalionCard:
    """
    Renders a battalion member card with:
    - Card base image (front for collected, back for uncollected)
    - Portrait (mob or individual soldier)
    - Card number circle at top (colored by danger)
    - Aura effects based on danger level
    - Text info (name, rank, unit, danger label)

    All rendering uses class methods with cached assets.
    """

    # Mob portrait mappings by danger level (fallback when no individual portrait)
    PORTRAIT_FILES = {
        1: ["portrait_mob_danger_1.png"],
        2: ["portrait_mob_danger_2.png"],
        3: ["portrait_mob_danger_3.png"],
        5: ["portrait_mob_danger_5.png"],
        7: ["portrait_mob_danger_7.png"],
    }

    # Cached assets (normal resolution)
    _card_base: Optional[pygame.Surface] = None
    _card_back: Optional[pygame.Surface] = None
    _portraits: dict[str, pygame.Surface] = {}

    # Cached assets (high resolution for hover)
    _card_base_hr: Optional[pygame.Surface] = None
    _card_back_hr: Optional[pygame.Surface] = None
    _portraits_hr: dict[str, pygame.Surface] = {}

    # Cached individual soldier portraits
    _soldier_portraits: dict[int, pygame.Surface] = {}
    _soldier_portraits_hr: dict[int, pygame.Surface] = {}

    _initialized: bool = False
    _loader: Optional[AssetLoader] = None

    # Expose card dimensions as class attributes (read from config)
    CARD_WIDTH = BATTALION_CARD_WIDTH
    CARD_HEIGHT = BATTALION_CARD_HEIGHT

    @classmethod
    def initialize(cls) -> None:
        """Load and cache card assets at both normal and high resolution."""
        if cls._initialized:
            return

        loader = AssetLoader()

        # High-res dimensions
        hr_width = int(cls.CARD_WIDTH * CARD_HR_SCALE)
        hr_height = int(cls.CARD_HEIGHT * CARD_HR_SCALE)

        # Load card base
        base_img = loader.load_image("cards/battalion_card_base_single.png")
        cls._card_base_hr = pygame.transform.smoothscale(
            base_img, (hr_width, hr_height)
        )
        cls._card_base = pygame.transform.smoothscale(
            base_img, (cls.CARD_WIDTH, cls.CARD_HEIGHT)
        )

        # Load card back for uncollected soldiers
        try:
            back_img = loader.load_image("cards/batallion_card_back.png")
            cls._card_back = pygame.transform.smoothscale(
                back_img, (cls.CARD_WIDTH, cls.CARD_HEIGHT)
            )
            cls._card_back_hr = pygame.transform.smoothscale(
                back_img, (hr_width, hr_height)
            )
        except Exception:
            cls._card_back = cls._card_base
            cls._card_back_hr = cls._card_base_hr

        # Load all mob portrait images at both resolutions
        for files in cls.PORTRAIT_FILES.values():
            for filename in files:
                path = f"characters/mobs/{filename}"
                portrait = loader.load_image(path)

                portrait_size = int(
                    cls.CARD_WIDTH * BATTALION_PORTRAIT_RADIUS_RATIO * 2
                )
                cls._portraits[filename] = pygame.transform.smoothscale(
                    portrait, (portrait_size, portrait_size)
                )

                portrait_size_hr = int(hr_width * BATTALION_PORTRAIT_RADIUS_RATIO * 2)
                cls._portraits_hr[filename] = pygame.transform.smoothscale(
                    portrait, (portrait_size_hr, portrait_size_hr)
                )

        cls._initialized = True
        cls._loader = loader

    @classmethod
    def _load_soldier_portrait(cls, soldier_id: int) -> Optional[pygame.Surface]:
        """Lazy load individual soldier portrait if available."""
        if soldier_id in cls._soldier_portraits:
            return cls._soldier_portraits[soldier_id]

        if cls._loader is None:
            cls._loader = AssetLoader()

        path = f"characters/portraits/portrait_{soldier_id}.png"
        try:
            portrait = cls._loader.load_image(path)

            portrait_size = int(cls.CARD_WIDTH * BATTALION_PORTRAIT_RADIUS_RATIO * 2)
            cls._soldier_portraits[soldier_id] = pygame.transform.smoothscale(
                portrait, (portrait_size, portrait_size)
            )

            hr_width = int(cls.CARD_WIDTH * CARD_HR_SCALE)
            portrait_size_hr = int(hr_width * BATTALION_PORTRAIT_RADIUS_RATIO * 2)
            cls._soldier_portraits_hr[soldier_id] = pygame.transform.smoothscale(
                portrait, (portrait_size_hr, portrait_size_hr)
            )

            return cls._soldier_portraits[soldier_id]
        except Exception:
            return None

    @classmethod
    def _get_danger_key(cls, danger: int) -> int:
        """Map danger level to the nearest available portrait key."""
        if danger in cls.PORTRAIT_FILES:
            return danger
        if danger <= 1:
            return 1
        elif danger <= 2:
            return 2
        elif danger <= 3:
            return 3
        elif danger <= 5:
            return 5
        else:
            return 7

    @classmethod
    def _get_portrait_filename(cls, danger: int, card_number: int) -> str:
        """Get portrait filename for danger level (deterministic by card number)."""
        danger_key = cls._get_danger_key(danger)
        files = cls.PORTRAIT_FILES[danger_key]
        return files[card_number % len(files)]

    @classmethod
    def get_portrait_for_danger(cls, danger: int, card_number: int) -> pygame.Surface:
        """Get appropriate mob portrait for danger level."""
        filename = cls._get_portrait_filename(danger, card_number)
        return cls._portraits[filename]

    @classmethod
    def _get_portrait_hr_for_danger(
        cls, danger: int, card_number: int
    ) -> pygame.Surface:
        """Get high-resolution mob portrait for danger level."""
        filename = cls._get_portrait_filename(danger, card_number)
        return cls._portraits_hr[filename]

    @classmethod
    def get_portrait_for_card(cls, card: Card) -> pygame.Surface:
        """Get appropriate portrait for a card (individual if collected, mob otherwise)."""
        if card.is_collected:
            if card.number in cls._soldier_portraits:
                return cls._soldier_portraits[card.number]
            portrait = cls._load_soldier_portrait(card.number)
            if portrait:
                return portrait
        return cls.get_portrait_for_danger(card.danger, card.number)

    @classmethod
    def get_portrait_hr_for_card(cls, card: Card) -> pygame.Surface:
        """Get high-resolution portrait for a card (individual if collected)."""
        if card.is_collected:
            if card.number in cls._soldier_portraits_hr:
                return cls._soldier_portraits_hr[card.number]
            cls._load_soldier_portrait(card.number)
            if card.number in cls._soldier_portraits_hr:
                return cls._soldier_portraits_hr[card.number]
        return cls._get_portrait_hr_for_danger(card.danger, card.number)

    @classmethod
    def render(
        cls,
        screen: pygame.Surface,
        card: Card,
        x: int,
        y: int,
        is_interviewed: bool = False,
        is_selected: bool = False,
        is_hovered: bool = False,
        rotation: float = 0.0,
        scale: float = 1.0,
    ) -> pygame.Rect:
        """
        Render a battalion card at the given position.

        Args:
            screen: Surface to render on.
            card: Card data to render.
            x: X position.
            y: Y position.
            is_interviewed: Whether the soldier has been interviewed.
            is_selected: Whether the card is selected.
            is_hovered: Whether the card is hovered.
            rotation: Rotation angle in degrees (positive = clockwise).
            scale: Scale factor for hover/zoom effect.

        Returns:
            The card's bounding rect for hit detection.
        """
        cls.initialize()

        aura_margin = CARD_AURA_MARGIN if card.danger >= 3 else 0
        use_hr = scale > 1.0

        # Determine target dimensions
        target_w = int(cls.CARD_WIDTH * scale) if use_hr else cls.CARD_WIDTH
        target_h = int(cls.CARD_HEIGHT * scale) if use_hr else cls.CARD_HEIGHT
        scaled_margin = int(aura_margin * scale) if use_hr else aura_margin

        # Create combined surface (card + aura margin)
        combined_surface = pygame.Surface(
            (target_w + scaled_margin * 2, target_h + scaled_margin * 2),
            pygame.SRCALPHA,
        )

        # Draw aura
        if card.danger >= 3:
            cls._draw_aura_on_surface(
                combined_surface,
                scaled_margin,
                scaled_margin,
                target_w,
                target_h,
                card.danger,
                scale if use_hr else 1.0,
            )

        # Build card surface
        if card.is_collected:
            base_src = cls._card_base_hr if use_hr else cls._card_base
            card_surface = pygame.transform.smoothscale(base_src, (target_w, target_h))
            cls._draw_portrait_on_surface(
                card_surface, card, target_w, target_h, use_hr
            )
            cls._draw_soldier_info_on_surface(
                card_surface, card, target_w, target_h, scale if use_hr else 1.0
            )
        else:
            back_src = cls._card_back_hr if use_hr else cls._card_back
            card_surface = pygame.transform.smoothscale(back_src, (target_w, target_h))

        # Draw number circle (always visible)
        cls._draw_number_circle_on_surface(
            card_surface,
            card.number,
            card.danger,
            target_w,
            target_h,
            scale if use_hr else 1.0,
        )

        # Draw selection/hover border
        cls._draw_card_border(
            card_surface,
            target_w,
            target_h,
            is_selected,
            is_hovered,
            scale if use_hr else 1.0,
        )

        # Compose card onto combined surface
        combined_surface.blit(card_surface, (scaled_margin, scaled_margin))

        # Apply rotation
        final_surface = combined_surface
        if rotation != 0.0:
            final_surface = pygame.transform.rotozoom(final_surface, -rotation, 1.0)

        # Calculate draw position (center the rotated/scaled surface)
        rect = final_surface.get_rect()
        if scale != 1.0:
            rect.centerx = x + cls.CARD_WIDTH // 2
            rect.bottom = y + cls.CARD_HEIGHT + int(aura_margin * scale)
        else:
            rect.centerx = x + cls.CARD_WIDTH // 2
            rect.centery = y + cls.CARD_HEIGHT // 2

        screen.blit(final_surface, rect)
        return pygame.Rect(x, y, cls.CARD_WIDTH, cls.CARD_HEIGHT)

    # ------------------------------------------------------------------
    # Internal drawing helpers (unified for normal and scaled rendering)
    # ------------------------------------------------------------------

    @classmethod
    def _draw_portrait_on_surface(
        cls,
        surface: pygame.Surface,
        card: Card,
        width: int,
        height: int,
        use_hr: bool,
    ) -> None:
        """Draw portrait circle onto the card surface."""
        portrait_src = (
            cls.get_portrait_hr_for_card(card)
            if use_hr
            else cls.get_portrait_for_card(card)
        )
        portrait_size = int(width * BATTALION_PORTRAIT_RADIUS_RATIO * 2)
        portrait = pygame.transform.smoothscale(
            portrait_src, (portrait_size, portrait_size)
        )

        portrait_x = int(
            width * BATTALION_PORTRAIT_CENTER_X - portrait.get_width() // 2
        )
        portrait_y = int(
            height * BATTALION_PORTRAIT_CENTER_Y - portrait.get_height() // 2
        )

        masked_portrait = cls._apply_circular_mask(portrait)
        surface.blit(masked_portrait, (portrait_x, portrait_y))

    @classmethod
    def _draw_number_circle_on_surface(
        cls,
        surface: pygame.Surface,
        card_number: int,
        danger: int,
        width: int,
        height: int,
        scale: float,
    ) -> None:
        """Draw card number circle at top of card (works at any scale)."""
        circle_x = int(width * BATTALION_NUMBER_CIRCLE_X)
        circle_y = int(height * BATTALION_NUMBER_CIRCLE_Y)
        radius = int(NUMBER_CIRCLE_RADIUS * scale)

        bg_color = get_danger_circle_color(danger)

        pygame.draw.circle(surface, bg_color, (circle_x, circle_y), radius)
        pygame.draw.circle(
            surface, WHITE, (circle_x, circle_y), radius, width=max(1, int(2 * scale))
        )

        font_size = int(NUMBER_CIRCLE_FONT_SIZE * scale)
        font = get_font(font_size, "bold")
        text = font.render(str(card_number), True, WHITE)
        text_rect = text.get_rect(center=(circle_x, circle_y))
        surface.blit(text, text_rect)

    @classmethod
    def _draw_soldier_info_on_surface(
        cls,
        surface: pygame.Surface,
        card: Card,
        width: int,
        height: int,
        scale: float,
    ) -> None:
        """Draw soldier info text (name, rank, unit, danger) at any scale."""
        scaled_font_size = int(BATTALION_TEXT_FONT_SIZE * scale)
        font = get_font(scaled_font_size)
        danger_font = get_font(scaled_font_size, "bold")

        center_x = width // 2
        detail_x = int(width * BATTALION_DETAIL_TEXT_X)

        name = card.name if card.name else "미확인"
        rank = card.rank if card.rank else "미확인"
        unit = card.unit if card.unit else "미확인"

        # Name (centered)
        name_y = int(height * BATTALION_NAME_Y)
        name_text = font.render(name, True, CARD_TEXT_COLOR)
        surface.blit(name_text, name_text.get_rect(center=(center_x, name_y)))

        # Rank
        rank_y = int(height * BATTALION_RANK_Y)
        rank_text = font.render(rank, True, CARD_TEXT_COLOR)
        surface.blit(rank_text, rank_text.get_rect(center=(detail_x, rank_y)))

        # Unit
        unit_y = int(height * BATTALION_UNIT_Y)
        unit_text = font.render(unit, True, CARD_TEXT_COLOR)
        surface.blit(unit_text, unit_text.get_rect(center=(detail_x, unit_y)))

        # Danger level label
        danger_y = int(height * BATTALION_DANGER_Y)
        danger_color = get_danger_circle_color(card.danger)
        danger_label = BATTALION_DANGER_LABELS.get(card.danger, "주의")
        danger_text = danger_font.render(danger_label, True, danger_color)
        surface.blit(danger_text, danger_text.get_rect(center=(detail_x, danger_y)))

    @classmethod
    def _draw_card_border(
        cls,
        surface: pygame.Surface,
        width: int,
        height: int,
        is_selected: bool,
        is_hovered: bool,
        scale: float,
    ) -> None:
        """Draw selection or hover border on the card surface."""
        if is_selected:
            pygame.draw.rect(
                surface,
                CARD_SELECTED_BORDER_COLOR,
                (0, 0, width, height),
                width=int(CARD_SELECTED_BORDER_WIDTH * scale),
                border_radius=int(CARD_BORDER_RADIUS * scale),
            )
        elif is_hovered:
            pygame.draw.rect(
                surface,
                CARD_HOVER_BORDER_COLOR,
                (0, 0, width, height),
                width=int(CARD_HOVER_BORDER_WIDTH * scale),
                border_radius=int(CARD_BORDER_RADIUS * scale),
            )

    @classmethod
    def _draw_aura_on_surface(
        cls,
        surface: pygame.Surface,
        card_x: int,
        card_y: int,
        card_width: int,
        card_height: int,
        danger: int,
        scale: float = 1.0,
    ) -> None:
        """Draw animated fire-like aura around the card position."""
        # Find the highest applicable aura color
        aura_color = None
        for threshold in sorted(CARD_AURA_COLORS.keys()):
            if danger >= threshold:
                aura_color = CARD_AURA_COLORS[threshold]

        if aura_color is None:
            return

        t = time.time() * 3  # Animation speed

        center_x = card_x + card_width // 2
        center_y = card_y + card_height // 2

        base_flame_size = int(CARD_AURA_BASE_FLAME_SIZE * scale)

        for i in range(CARD_AURA_NUM_FLAMES):
            angle = (i / CARD_AURA_NUM_FLAMES) * 2 * math.pi + t * 0.3

            ellipse_x = math.cos(angle) * (card_width // 2 + int(5 * scale))
            ellipse_y = math.sin(angle) * (card_height // 2 + int(5 * scale))

            flame_x = center_x + int(ellipse_x)
            flame_y = center_y + int(ellipse_y)

            wave = math.sin(t * 2 + i * 0.5)
            current_size = base_flame_size + int(wave * 5 * scale)

            for j in range(4):
                size = int(current_size * (1 - j * 0.2))
                alpha = int(aura_color[3] * (1 - j * 0.25))
                color = (*aura_color[:3], max(10, alpha))

                flicker_x = int(math.sin(t * 5 + i + j) * 2 * scale)
                flicker_y = int(math.cos(t * 4 + i + j) * 2 * scale)

                pygame.draw.circle(
                    surface,
                    color,
                    (flame_x + flicker_x, flame_y + flicker_y - int(j * 3 * scale)),
                    max(1, size),
                )

    @classmethod
    def _apply_circular_mask(cls, surface: pygame.Surface) -> pygame.Surface:
        """Apply circular mask to a portrait surface."""
        size = surface.get_width()
        masked = pygame.Surface((size, size), pygame.SRCALPHA)
        pygame.draw.circle(
            masked, (255, 255, 255, 255), (size // 2, size // 2), size // 2
        )
        masked.blit(surface, (0, 0), special_flags=pygame.BLEND_RGBA_MIN)
        return masked
