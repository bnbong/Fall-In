"""
BattalionCard - Renders soldier card with portrait, danger info, and aura effects

# TODO: add card aura effect assets or improve the current aura effect
"""

from typing import Optional

import pygame

from fall_in.core.card import Card
from fall_in.utils.asset_loader import AssetLoader, get_font
from fall_in.utils.danger_utils import get_danger_circle_color
from fall_in.config import (
    WHITE,
    NUMBER_CIRCLE_RADIUS,
    NUMBER_CIRCLE_FONT_SIZE,
    BATTALION_CARD_WIDTH,
    BATTALION_CARD_HEIGHT,
    BATTALION_PORTRAIT_CENTER_X,
    BATTALION_PORTRAIT_CENTER_Y,
    BATTALION_PORTRAIT_RADIUS_RATIO,
    BATTALION_NUMBER_CIRCLE_X,
    BATTALION_NUMBER_CIRCLE_Y,
    BATTALION_NAME_Y,
    BATTALION_RANK_Y,
    BATTALION_UNIT_Y,
    BATTALION_DANGER_Y,
    BATTALION_TEXT_FONT_SIZE,
    BATTALION_DANGER_LABELS,
    BATTALION_DETAIL_TEXT_X,
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

    # Constants for number circle
    NUMBER_CIRCLE_RADIUS = NUMBER_CIRCLE_RADIUS
    NUMBER_CIRCLE_FONT_SIZE = NUMBER_CIRCLE_FONT_SIZE

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

    # Fall back mob character portrait mappings by danger level (not used until got error on loading interviewed soldier's info)
    PORTRAIT_FILES = {
        1: ["portrait_mob_danger_1.png"],
        2: ["portrait_mob_danger_2.png"],
        3: ["portrait_mob_danger_3.png"],
        5: ["portrait_mob_danger_5.png"],
        7: ["portrait_mob_danger_7.png"],
    }

    # High-resolution scale factor for hover (assets are 2x size)
    HR_SCALE = 2.0

    # Cached assets (normal resolution)
    _card_base: Optional[pygame.Surface] = None
    _card_back: Optional[pygame.Surface] = None  # Card back for uncollected
    _portraits: dict[str, pygame.Surface] = {}

    # Cached assets (high resolution for hover)
    _card_base_hr: Optional[pygame.Surface] = None
    _card_back_hr: Optional[pygame.Surface] = None  # Card back HR
    _portraits_hr: dict[str, pygame.Surface] = {}

    # Cached individual soldier portraits
    _soldier_portraits: dict[int, pygame.Surface] = {}
    _soldier_portraits_hr: dict[int, pygame.Surface] = {}

    _initialized: bool = False
    _loader: Optional[AssetLoader] = None  # Keep loader for lazy loading

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
            # Fallback: use base if back not found
            cls._card_back = cls._card_base
            cls._card_back_hr = cls._card_base_hr

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
        cls._loader = loader  # Keep for lazy loading individual portraits

    @classmethod
    def _load_soldier_portrait(cls, soldier_id: int) -> Optional[pygame.Surface]:
        """Lazy load individual soldier portrait if available"""
        if soldier_id in cls._soldier_portraits:
            return cls._soldier_portraits[soldier_id]

        if cls._loader is None:
            cls._loader = AssetLoader()

        path = f"characters/portraits/portrait_{soldier_id}.png"
        try:
            portrait = cls._loader.load_image(path)

            # Normal size
            portrait_size = int(cls.CARD_WIDTH * cls.PORTRAIT_RADIUS_RATIO * 2)
            scaled = pygame.transform.smoothscale(
                portrait, (portrait_size, portrait_size)
            )
            cls._soldier_portraits[soldier_id] = scaled

            # High-res size
            hr_width = int(cls.CARD_WIDTH * cls.HR_SCALE)
            portrait_size_hr = int(hr_width * cls.PORTRAIT_RADIUS_RATIO * 2)
            scaled_hr = pygame.transform.smoothscale(
                portrait, (portrait_size_hr, portrait_size_hr)
            )
            cls._soldier_portraits_hr[soldier_id] = scaled_hr

            return scaled
        except Exception:
            return None  # Portrait not found, will use mob portrait

    @classmethod
    def _get_danger_key(cls, danger: int) -> int:
        """Map danger level to available portrait key"""
        if danger in cls.PORTRAIT_FILES:
            return danger
        # Fall back to closest available
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
        """Get portrait filename for danger level (deterministic by card number)"""
        danger_key = cls._get_danger_key(danger)
        files = cls.PORTRAIT_FILES[danger_key]
        return files[card_number % len(files)]

    @classmethod
    def get_portrait_for_danger(cls, danger: int, card_number: int) -> pygame.Surface:
        """Get appropriate portrait for danger level (deterministic by card number)"""
        filename = cls._get_portrait_filename(danger, card_number)
        return cls._portraits[filename]

    @classmethod
    def _get_portrait_hr_for_danger(
        cls, danger: int, card_number: int
    ) -> pygame.Surface:
        """Get high-resolution portrait for danger level (for hover/zoom rendering)"""
        # Fall back to mob portrait
        filename = cls._get_portrait_filename(danger, card_number)
        return cls._portraits_hr[filename]

    @classmethod
    def get_portrait_for_card(cls, card: Card) -> pygame.Surface:
        """Get appropriate portrait for a card (individual if interviewed)"""
        if card.is_collected:
            # Check for individual portrait
            if card.number in cls._soldier_portraits:
                return cls._soldier_portraits[card.number]
            # Try to load
            portrait = cls._load_soldier_portrait(card.number)
            if portrait:
                return portrait

        # Fall back to mob portrait
        return cls.get_portrait_for_danger(card.danger, card.number)

    @classmethod
    def get_portrait_hr_for_card(cls, card: Card) -> pygame.Surface:
        """Get high-resolution portrait for a card (individual if interviewed)"""
        if card.is_collected:
            # Check for individual HR portrait
            if card.number in cls._soldier_portraits_hr:
                return cls._soldier_portraits_hr[card.number]
            # Try to load individual portrait (loads both normal and HR)
            cls._load_soldier_portrait(card.number)
            if card.number in cls._soldier_portraits_hr:
                return cls._soldier_portraits_hr[card.number]

        # Fall back to mob portrait HR
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

        # Aura margin for combined surface
        aura_margin = 35 if card.danger >= 3 else 0

        # Determine if we should use high-res rendering (for hover/scale > 1)
        use_hr = scale > 1.0

        if use_hr:
            # Use HR assets and scale down to target size (sharper than scaling up)
            target_width = int(cls.CARD_WIDTH * scale)
            target_height = int(cls.CARD_HEIGHT * scale)
            scaled_margin = int(aura_margin * scale)

            # Create combined surface (card + aura margin)
            combined_width = target_width + scaled_margin * 2
            combined_height = target_height + scaled_margin * 2
            combined_surface = pygame.Surface(
                (combined_width, combined_height), pygame.SRCALPHA
            )

            # Draw aura on combined surface (centered)
            if card.danger >= 3:
                cls._draw_aura_on_surface(
                    combined_surface,
                    scaled_margin,
                    scaled_margin,
                    target_width,
                    target_height,
                    card.danger,
                    scale,
                )

            # Use card back for uncollected soldiers, base for collected
            if card.is_collected:
                card_surface = pygame.transform.smoothscale(
                    cls._card_base_hr, (target_width, target_height)
                )

                # Draw portrait from HR version (individual if collected)
                portrait_hr = cls.get_portrait_hr_for_card(card)
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

                # Draw soldier info text (scaled) - only for collected
                cls._draw_soldier_info_scaled(card_surface, card, is_interviewed, scale)
            else:
                # Uncollected: use card back, no portrait, no info text
                card_surface = pygame.transform.smoothscale(
                    cls._card_back_hr, (target_width, target_height)
                )

            # Draw number circle (scaled) - always show
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

            # Blit card onto combined surface
            combined_surface.blit(card_surface, (scaled_margin, scaled_margin))
            final_surface = combined_surface

        else:
            # Normal resolution rendering
            # Create combined surface (card + aura margin)
            combined_width = cls.CARD_WIDTH + aura_margin * 2
            combined_height = cls.CARD_HEIGHT + aura_margin * 2
            combined_surface = pygame.Surface(
                (combined_width, combined_height), pygame.SRCALPHA
            )

            # Draw aura on combined surface
            if card.danger >= 3:
                cls._draw_aura_on_surface(
                    combined_surface,
                    aura_margin,
                    aura_margin,
                    cls.CARD_WIDTH,
                    cls.CARD_HEIGHT,
                    card.danger,
                    1.0,
                )

            # Use card back for uncollected soldiers, base for collected
            if card.is_collected:
                card_surface = cls._card_base.copy()

                # Draw portrait (individual if collected)
                portrait = cls.get_portrait_for_card(card)
                portrait_x = int(
                    cls.CARD_WIDTH * cls.PORTRAIT_CENTER_X - portrait.get_width() // 2
                )
                portrait_y = int(
                    cls.CARD_HEIGHT * cls.PORTRAIT_CENTER_Y - portrait.get_height() // 2
                )

                # Create circular mask for portrait
                masked_portrait = cls._apply_circular_mask(portrait)
                card_surface.blit(masked_portrait, (portrait_x, portrait_y))

                # Draw soldier info text (name, rank, unit, danger) - only for collected
                cls._draw_soldier_info(card_surface, card, is_interviewed)
            else:
                # Uncollected: use card back, no portrait, no info text
                card_surface = cls._card_back.copy()

            # Draw number circle at top (shows card number, colored by danger) - always show
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

            # Blit card onto combined surface
            combined_surface.blit(card_surface, (aura_margin, aura_margin))
            final_surface = combined_surface

        # Apply rotation if needed (rotozoom for anti-aliased rotation)
        if rotation != 0.0:
            final_surface = pygame.transform.rotozoom(final_surface, -rotation, 1.0)

        # Calculate draw position (center the rotated/scaled surface)
        rect = final_surface.get_rect()
        if scale != 1.0:
            # When scaled, center horizontally and align to original bottom
            rect.centerx = x + cls.CARD_WIDTH // 2
            rect.bottom = y + cls.CARD_HEIGHT + int(aura_margin * scale)
        else:
            # Center on original card position
            rect.centerx = x + cls.CARD_WIDTH // 2
            rect.centery = y + cls.CARD_HEIGHT // 2

        # Blit to screen
        screen.blit(final_surface, rect)

        return pygame.Rect(x, y, cls.CARD_WIDTH, cls.CARD_HEIGHT)

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
        """Draw animated fire-like aura on the given surface around card position"""
        import math
        import time

        # Find the highest applicable aura color
        aura_color = None
        for threshold in sorted(cls.AURA_COLORS.keys()):
            if danger >= threshold:
                aura_color = cls.AURA_COLORS[threshold]

        if aura_color is None:
            return

        # Get animation time for wave effect
        t = time.time() * 3  # Speed of animation

        # Center of card on the surface
        center_x = card_x + card_width // 2
        center_y = card_y + card_height // 2

        # Draw multiple flame layers around card perimeter
        num_flames = 12
        base_flame_size = int(15 * scale)

        for i in range(num_flames):
            # Distribute flames around the card perimeter
            angle = (i / num_flames) * 2 * math.pi + t * 0.3

            # Calculate flame position on card edge (ellipse path)
            ellipse_x = math.cos(angle) * (card_width // 2 + int(5 * scale))
            ellipse_y = math.sin(angle) * (card_height // 2 + int(5 * scale))

            flame_x = center_x + int(ellipse_x)
            flame_y = center_y + int(ellipse_y)

            # Flame size varies with time
            wave = math.sin(t * 2 + i * 0.5)
            current_size = base_flame_size + int(wave * 5 * scale)

            # Draw flame (multiple circles for soft glow)
            for j in range(4):
                size = int(current_size * (1 - j * 0.2))
                alpha = int(aura_color[3] * (1 - j * 0.25))
                color = (*aura_color[:3], max(10, alpha))

                # Offset for flickering effect
                flicker_x = int(math.sin(t * 5 + i + j) * 2 * scale)
                flicker_y = int(math.cos(t * 4 + i + j) * 2 * scale)

                pygame.draw.circle(
                    surface,
                    color,
                    (flame_x + flicker_x, flame_y + flicker_y - int(j * 3 * scale)),
                    max(1, size),
                )

    @classmethod
    def _draw_number_circle(
        cls, surface: pygame.Surface, card_number: int, danger: int
    ) -> None:
        """Draw card number circle at top of card (colored by danger level)"""
        circle_x = int(cls.CARD_WIDTH * cls.NUMBER_CIRCLE_X)
        circle_y = int(cls.CARD_HEIGHT * cls.NUMBER_CIRCLE_Y)
        radius = cls.NUMBER_CIRCLE_RADIUS

        bg_color = get_danger_circle_color(danger)

        pygame.draw.circle(surface, bg_color, (circle_x, circle_y), radius)
        pygame.draw.circle(surface, WHITE, (circle_x, circle_y), radius, width=2)

        # Draw card number (not danger)
        font = get_font(cls.NUMBER_CIRCLE_FONT_SIZE, "bold")
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
        radius = int(cls.NUMBER_CIRCLE_RADIUS * scale)

        bg_color = get_danger_circle_color(danger)

        pygame.draw.circle(surface, bg_color, (circle_x, circle_y), radius)
        pygame.draw.circle(
            surface, WHITE, (circle_x, circle_y), radius, width=max(1, int(2 * scale))
        )

        # Draw card number with scaled font
        font_size = int(cls.NUMBER_CIRCLE_FONT_SIZE * scale)
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

    @classmethod
    def _draw_soldier_info(
        cls, surface: pygame.Surface, card: Card, is_interviewed: bool
    ) -> None:
        """Draw soldier info text on card (name, rank, unit, danger on 4 lines)"""
        font = get_font(BATTALION_TEXT_FONT_SIZE)
        danger_font = get_font(BATTALION_TEXT_FONT_SIZE, "bold")
        center_x = cls.CARD_WIDTH // 2  # Name stays centered
        detail_x = int(
            cls.CARD_WIDTH * BATTALION_DETAIL_TEXT_X
        )  # X for rank/unit/danger

        # Text color
        text_color = (50, 50, 50)

        # Get card info (this function is only called for collected soldiers)
        name = card.name if card.name else "미확인"
        rank = card.rank if card.rank else "미확인"
        unit = card.unit if card.unit else "미확인"

        # Draw name (centered)
        name_y = int(cls.CARD_HEIGHT * BATTALION_NAME_Y)
        name_text = font.render(name, True, text_color)
        name_rect = name_text.get_rect(center=(center_x, name_y))
        surface.blit(name_text, name_rect)

        # Draw rank (uses detail_x)
        rank_y = int(cls.CARD_HEIGHT * BATTALION_RANK_Y)
        rank_text = font.render(rank, True, text_color)
        rank_rect = rank_text.get_rect(center=(detail_x, rank_y))
        surface.blit(rank_text, rank_rect)

        # Draw unit (uses detail_x)
        unit_y = int(cls.CARD_HEIGHT * BATTALION_UNIT_Y)
        unit_text = font.render(unit, True, text_color)
        unit_rect = unit_text.get_rect(center=(detail_x, unit_y))
        surface.blit(unit_text, unit_rect)

        # Draw danger level with text label and color (uses detail_x)
        danger_y = int(cls.CARD_HEIGHT * BATTALION_DANGER_Y)
        danger_color = get_danger_circle_color(card.danger)
        danger_label = BATTALION_DANGER_LABELS.get(card.danger, "주의")
        danger_text = danger_font.render(danger_label, True, danger_color)
        danger_rect = danger_text.get_rect(center=(detail_x, danger_y))
        surface.blit(danger_text, danger_rect)

    @classmethod
    def _draw_soldier_info_scaled(
        cls, surface: pygame.Surface, card: Card, is_interviewed: bool, scale: float
    ) -> None:
        """Draw soldier info text on card (scaled version for HR rendering)"""
        scaled_font_size = int(BATTALION_TEXT_FONT_SIZE * scale)
        font = get_font(scaled_font_size)
        danger_font = get_font(scaled_font_size, "bold")

        scaled_width = int(cls.CARD_WIDTH * scale)
        scaled_height = int(cls.CARD_HEIGHT * scale)
        center_x = scaled_width // 2
        detail_x = int(scaled_width * BATTALION_DETAIL_TEXT_X)

        # Text color
        text_color = (50, 50, 50)

        # Get card info (this function is only called for collected soldiers)
        name = card.name if card.name else "미확인"
        rank = card.rank if card.rank else "미확인"
        unit = card.unit if card.unit else "미확인"

        # Draw name (centered)
        name_y = int(scaled_height * BATTALION_NAME_Y)
        name_text = font.render(name, True, text_color)
        name_rect = name_text.get_rect(center=(center_x, name_y))
        surface.blit(name_text, name_rect)

        # Draw rank (uses detail_x)
        rank_y = int(scaled_height * BATTALION_RANK_Y)
        rank_text = font.render(rank, True, text_color)
        rank_rect = rank_text.get_rect(center=(detail_x, rank_y))
        surface.blit(rank_text, rank_rect)

        # Draw unit (uses detail_x)
        unit_y = int(scaled_height * BATTALION_UNIT_Y)
        unit_text = font.render(unit, True, text_color)
        unit_rect = unit_text.get_rect(center=(detail_x, unit_y))
        surface.blit(unit_text, unit_rect)

        # Draw danger level with text label and color (uses detail_x)
        danger_y = int(scaled_height * BATTALION_DANGER_Y)
        danger_color = get_danger_circle_color(card.danger)
        danger_label = BATTALION_DANGER_LABELS.get(card.danger, "주의")
        danger_text = danger_font.render(danger_label, True, danger_color)
        danger_rect = danger_text.get_rect(center=(detail_x, danger_y))
        surface.blit(danger_text, danger_rect)
