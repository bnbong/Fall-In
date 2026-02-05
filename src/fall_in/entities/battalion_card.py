"""
BattalionCard - Renders soldier card with portrait, danger info, and aura effects

# TODO: add card aura effect assets or improve the current aura effect
"""

from typing import Optional

import pygame

from fall_in.core.card import Card
from fall_in.utils.asset_loader import AssetLoader, get_font
from fall_in.config import (
    WHITE,
    BATTALION_CARD_WIDTH,
    BATTALION_CARD_HEIGHT,
    BATTALION_PORTRAIT_CENTER_X,
    BATTALION_PORTRAIT_CENTER_Y,
    BATTALION_PORTRAIT_RADIUS_RATIO,
    BATTALION_NUMBER_CIRCLE_X,
    BATTALION_NUMBER_CIRCLE_Y,
)


class BattalionCard:
    """
    Renders a battalion member card with:
    - Card base image
    - Portrait (mob or interviewed soldier)
    - Card number circle at top (colored by danger)
    - Aura effects based on danger level
    - Text info (name, rank, unit)
    """

    # Card display size (from config)
    CARD_WIDTH = BATTALION_CARD_WIDTH
    CARD_HEIGHT = BATTALION_CARD_HEIGHT

    # Portrait positioning (from config)
    PORTRAIT_CENTER_X = BATTALION_PORTRAIT_CENTER_X
    PORTRAIT_CENTER_Y = BATTALION_PORTRAIT_CENTER_Y
    PORTRAIT_RADIUS_RATIO = BATTALION_PORTRAIT_RADIUS_RATIO

    # Number circle position (from config)
    NUMBER_CIRCLE_X = BATTALION_NUMBER_CIRCLE_X
    NUMBER_CIRCLE_Y = BATTALION_NUMBER_CIRCLE_Y

    # Aura colors by danger threshold
    AURA_COLORS = {
        3: (255, 165, 0, 100),  # Orange glow
        5: (255, 50, 50, 120),  # Red glow
        7: (100, 50, 150, 140),  # Dark purple glow
    }

    # Portrait mappings by danger level
    PORTRAIT_FILES = {
        1: ["portrait_mob_danger_1_1.png", "portrait_mob_danger_1_2.png"],
        2: ["portrait_mob_danger_2_1.png", "portrait_mob_danger_2_2.png"],
        3: [
            "portrait_mob_danger_3_1.png",
            "portrait_mob_danger_3_2.png",
            "portrait_mob_danger_3_3.png",
        ],
        5: ["portrait_mob_danger_5_1.png", "portrait_mob_danger_5_2.png"],
        7: ["portrait_mob_danger_7.png"],
    }

    # High-resolution scale factor for hover (assets are 2x size)
    HR_SCALE = 2.0

    # Cached assets (normal resolution)
    _card_base: Optional[pygame.Surface] = None
    _portraits: dict[str, pygame.Surface] = {}

    # Cached assets (high resolution for hover)
    _card_base_hr: Optional[pygame.Surface] = None
    _portraits_hr: dict[str, pygame.Surface] = {}

    _initialized: bool = False

    @classmethod
    def initialize(cls) -> None:
        """Load and cache card assets at both normal and high resolution"""
        if cls._initialized:
            return

        loader = AssetLoader()

        # Load card base - store HR version and normal version
        base_img = loader.load_image("cards/battalion_card_base_single.png")

        # High-res version (scaled from original to 2x display size)
        hr_width = int(cls.CARD_WIDTH * cls.HR_SCALE)
        hr_height = int(cls.CARD_HEIGHT * cls.HR_SCALE)
        cls._card_base_hr = pygame.transform.smoothscale(
            base_img, (hr_width, hr_height)
        )

        # Normal version
        cls._card_base = pygame.transform.smoothscale(
            base_img, (cls.CARD_WIDTH, cls.CARD_HEIGHT)
        )

        # Load all portrait images at both resolutions
        for danger_level, files in cls.PORTRAIT_FILES.items():
            for filename in files:
                path = f"characters/mobs/{filename}"
                portrait = loader.load_image(path)

                # Normal size
                portrait_size = int(cls.CARD_WIDTH * cls.PORTRAIT_RADIUS_RATIO * 2)
                scaled = pygame.transform.smoothscale(
                    portrait, (portrait_size, portrait_size)
                )
                cls._portraits[filename] = scaled

                # High-res size
                portrait_size_hr = int(hr_width * cls.PORTRAIT_RADIUS_RATIO * 2)
                scaled_hr = pygame.transform.smoothscale(
                    portrait, (portrait_size_hr, portrait_size_hr)
                )
                cls._portraits_hr[filename] = scaled_hr

        cls._initialized = True

    @classmethod
    def get_portrait_for_danger(cls, danger: int, card_number: int) -> pygame.Surface:
        """Get appropriate portrait for danger level (deterministic by card number)"""
        # Map danger to available portraits
        danger_key = danger
        if danger not in cls.PORTRAIT_FILES:
            # Fall back to closest available
            if danger <= 1:
                danger_key = 1
            elif danger <= 2:
                danger_key = 2
            elif danger <= 3:
                danger_key = 3
            elif danger <= 5:
                danger_key = 5
            else:
                danger_key = 7

        files = cls.PORTRAIT_FILES[danger_key]
        # Use card number to deterministically select portrait variant
        selected = files[card_number % len(files)]
        return cls._portraits[selected]

    @classmethod
    def _get_portrait_hr_for_danger(
        cls, danger: int, card_number: int
    ) -> pygame.Surface:
        """Get high-resolution portrait for danger level (for hover/zoom rendering)"""
        # Map danger to available portraits (same logic as get_portrait_for_danger)
        danger_key = danger
        if danger not in cls.PORTRAIT_FILES:
            # Fall back to closest available
            if danger <= 1:
                danger_key = 1
            elif danger <= 2:
                danger_key = 2
            elif danger <= 3:
                danger_key = 3
            elif danger <= 5:
                danger_key = 5
            else:
                danger_key = 7

        files = cls.PORTRAIT_FILES[danger_key]
        # Use card number to deterministically select portrait variant
        selected = files[card_number % len(files)]
        return cls._portraits_hr[selected]

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
        rotation: float = 0.0,  # Rotation angle in degrees
        scale: float = 1.0,  # Scale factor (1.0 = normal)
    ) -> pygame.Rect:
        """
        Render a battalion card at the given position.

        Args:
            rotation: Rotation angle in degrees (positive = clockwise)
            scale: Scale factor for hover/zoom effect

        Returns the card's bounding rect for hit detection.
        """
        cls.initialize()

        # Determine if we should use high-res rendering (for hover/scale > 1)
        use_hr = scale > 1.0

        if use_hr:
            # Use HR assets and scale down to target size (sharper than scaling up)
            target_width = int(cls.CARD_WIDTH * scale)
            target_height = int(cls.CARD_HEIGHT * scale)

            # Start from HR card base
            card_surface = pygame.transform.smoothscale(
                cls._card_base_hr, (target_width, target_height)
            )

            # Draw aura effect for high danger cards
            if card.danger >= 3:
                cls._draw_aura(screen, x, y, card.danger)

            # Draw portrait from HR version
            portrait_hr = cls._get_portrait_hr_for_danger(card.danger, card.number)
            portrait_size = int(target_width * cls.PORTRAIT_RADIUS_RATIO * 2)
            portrait = pygame.transform.smoothscale(
                portrait_hr, (portrait_size, portrait_size)
            )
            portrait_x = int(
                target_width * cls.PORTRAIT_CENTER_X - portrait.get_width() // 2
            )
            portrait_y = int(
                target_height * cls.PORTRAIT_CENTER_Y - portrait.get_height() // 2
            )

            masked_portrait = cls._apply_circular_mask(portrait)
            card_surface.blit(masked_portrait, (portrait_x, portrait_y))

            # Draw number circle (scaled)
            cls._draw_number_circle_scaled(
                card_surface, card.number, card.danger, scale
            )

            # Draw selection/hover border (scaled)
            if is_selected:
                pygame.draw.rect(
                    card_surface,
                    (100, 200, 100),
                    (0, 0, target_width, target_height),
                    width=int(4 * scale),
                    border_radius=int(8 * scale),
                )
            elif is_hovered:
                pygame.draw.rect(
                    card_surface,
                    (255, 255, 150),
                    (0, 0, target_width, target_height),
                    width=int(3 * scale),
                    border_radius=int(8 * scale),
                )
        else:
            # Normal resolution rendering
            card_surface = cls._card_base.copy()

            # Draw aura effect for high danger cards
            if card.danger >= 3 and scale > 1.0:
                cls._draw_aura(screen, x, y, card.danger)

            # Draw portrait
            portrait = cls.get_portrait_for_danger(card.danger, card.number)
            portrait_x = int(
                cls.CARD_WIDTH * cls.PORTRAIT_CENTER_X - portrait.get_width() // 2
            )
            portrait_y = int(
                cls.CARD_HEIGHT * cls.PORTRAIT_CENTER_Y - portrait.get_height() // 2
            )

            # Create circular mask for portrait
            masked_portrait = cls._apply_circular_mask(portrait)
            card_surface.blit(masked_portrait, (portrait_x, portrait_y))

            # Draw number circle at top (shows card number, colored by danger)
            cls._draw_number_circle(card_surface, card.number, card.danger)

            # Draw selection/hover effects
            if is_selected:
                pygame.draw.rect(
                    card_surface,
                    (100, 200, 100),
                    (0, 0, cls.CARD_WIDTH, cls.CARD_HEIGHT),
                    width=4,
                    border_radius=8,
                )
            elif is_hovered:
                pygame.draw.rect(
                    card_surface,
                    (255, 255, 150),
                    (0, 0, cls.CARD_WIDTH, cls.CARD_HEIGHT),
                    width=3,
                    border_radius=8,
                )

        # Apply rotation if needed (rotozoom for anti-aliased rotation)
        if rotation != 0.0:
            card_surface = pygame.transform.rotozoom(card_surface, -rotation, 1.0)

        # Calculate draw position (center the rotated/scaled surface)
        rect = card_surface.get_rect()
        if scale != 1.0:
            # When scaled, center horizontally and align to original bottom
            rect.centerx = x + cls.CARD_WIDTH // 2
            rect.bottom = y + cls.CARD_HEIGHT
        else:
            rect.topleft = (x, y)

        # Blit to screen
        screen.blit(card_surface, rect)

        return pygame.Rect(x, y, cls.CARD_WIDTH, cls.CARD_HEIGHT)

    @classmethod
    def _draw_aura(cls, screen: pygame.Surface, x: int, y: int, danger: int) -> None:
        """Draw glowing aura behind the card"""
        # Find the highest applicable aura
        aura_color = None
        for threshold in sorted(cls.AURA_COLORS.keys()):
            if danger >= threshold:
                aura_color = cls.AURA_COLORS[threshold]

        if aura_color is None:
            return

        # Create aura surface with alpha
        aura_size = int(cls.CARD_WIDTH * 1.3)
        aura_surface = pygame.Surface((aura_size, aura_size + 20), pygame.SRCALPHA)

        # Draw multiple ellipses for glow effect
        center = (aura_size // 2, (aura_size + 20) // 2)
        for i in range(3):
            size_factor = 1.0 - i * 0.15
            alpha = aura_color[3] // (i + 1)
            color = (*aura_color[:3], alpha)
            pygame.draw.ellipse(
                aura_surface,
                color,
                (
                    center[0] - int(aura_size * size_factor // 2),
                    center[1] - int((aura_size + 20) * size_factor // 2),
                    int(aura_size * size_factor),
                    int((aura_size + 20) * size_factor),
                ),
            )

        # Position aura behind card
        aura_x = x - (aura_size - cls.CARD_WIDTH) // 2
        aura_y = y - (aura_size + 20 - cls.CARD_HEIGHT) // 2
        screen.blit(aura_surface, (aura_x, aura_y))

    @classmethod
    def _draw_number_circle(
        cls, surface: pygame.Surface, card_number: int, danger: int
    ) -> None:
        """Draw card number circle at top of card (colored by danger level)"""
        circle_x = int(cls.CARD_WIDTH * cls.NUMBER_CIRCLE_X)
        circle_y = int(cls.CARD_HEIGHT * cls.NUMBER_CIRCLE_Y)
        radius = 14  # Larger for bigger card

        # Circle background color based on danger
        if danger >= 7:
            bg_color = (100, 50, 150)  # Purple
        elif danger >= 5:
            bg_color = (200, 50, 50)  # Red
        elif danger >= 3:
            bg_color = (230, 150, 50)  # Orange
        elif danger >= 2:
            bg_color = (200, 180, 50)  # Yellow
        else:
            bg_color = (100, 150, 100)  # Green

        pygame.draw.circle(surface, bg_color, (circle_x, circle_y), radius)
        pygame.draw.circle(surface, WHITE, (circle_x, circle_y), radius, width=2)

        # Draw card number (not danger)
        font = get_font(12, "bold")
        text = font.render(str(card_number), True, WHITE)
        text_rect = text.get_rect(center=(circle_x, circle_y))
        surface.blit(text, text_rect)

    @classmethod
    def _draw_number_circle_scaled(
        cls, surface: pygame.Surface, card_number: int, danger: int, scale: float
    ) -> None:
        """Draw card number circle at top of card (scaled version for hover/zoom)"""
        # Calculate scaled dimensions
        scaled_width = int(cls.CARD_WIDTH * scale)
        scaled_height = int(cls.CARD_HEIGHT * scale)
        circle_x = int(scaled_width * cls.NUMBER_CIRCLE_X)
        circle_y = int(scaled_height * cls.NUMBER_CIRCLE_Y)
        radius = int(14 * scale)  # Scale the radius

        # Circle background color based on danger
        if danger >= 7:
            bg_color = (100, 50, 150)  # Purple
        elif danger >= 5:
            bg_color = (200, 50, 50)  # Red
        elif danger >= 3:
            bg_color = (230, 150, 50)  # Orange
        elif danger >= 2:
            bg_color = (200, 180, 50)  # Yellow
        else:
            bg_color = (100, 150, 100)  # Green

        pygame.draw.circle(surface, bg_color, (circle_x, circle_y), radius)
        pygame.draw.circle(
            surface, WHITE, (circle_x, circle_y), radius, width=max(1, int(2 * scale))
        )

        # Draw card number with scaled font
        font_size = int(12 * scale)
        font = get_font(font_size, "bold")
        text = font.render(str(card_number), True, WHITE)
        text_rect = text.get_rect(center=(circle_x, circle_y))
        surface.blit(text, text_rect)

    @classmethod
    def _apply_circular_mask(cls, surface: pygame.Surface) -> pygame.Surface:
        """Apply circular mask to portrait"""
        size = surface.get_width()
        masked = pygame.Surface((size, size), pygame.SRCALPHA)

        # Create circular mask
        pygame.draw.circle(
            masked, (255, 255, 255, 255), (size // 2, size // 2), size // 2
        )

        # Apply mask
        masked.blit(surface, (0, 0), special_flags=pygame.BLEND_RGBA_MIN)

        return masked
