"""
Frozen Food Entity - BX frozen food items displayed on interview table
"""

import random
from typing import Optional

import pygame

from fall_in.config import (
    FROZEN_FOOD_SIZE,
    FROZEN_FOOD_GAP,
    FROZEN_FOOD_MIN_COUNT,
    FROZEN_FOOD_MAX_COUNT,
    FROZEN_FOOD_TABLE_X,
    FROZEN_FOOD_TABLE_Y,
)
from fall_in.utils.asset_loader import AssetLoader, get_font


class FrozenFood:
    """
    BX 냉동식품 엔티티 - 면담 테이블 위에 표시되는 음식 아이템.
    게임 스토리: 병사에게 맛있는 것을 사주며 면담을 진행하는 설정.

    에셋 경로: assets/images/ui/frozen_food_{name}.png
    """

    # Available food types with fallback colors (used if asset not found)
    FOOD_TYPES = [
        {
            "name": "ramen",
            "label": "라면",
            "color": (255, 200, 50),
            "accent": (200, 100, 30),
        },
        {
            "name": "dumpling",
            "label": "만두",
            "color": (240, 220, 180),
            "accent": (180, 150, 100),
        },
        {
            "name": "kimbap",
            "label": "김밥",
            "color": (60, 140, 60),
            "accent": (20, 80, 20),
        },
        {
            "name": "burger",
            "label": "햄버거",
            "color": (200, 150, 80),
            "accent": (150, 80, 40),
        },
        {
            "name": "chicken",
            "label": "치킨",
            "color": (220, 180, 100),
            "accent": (180, 120, 60),
        },
        {
            "name": "pizza",
            "label": "피자",
            "color": (255, 180, 80),
            "accent": (200, 80, 50),
        },
        {
            "name": "tteokbokki",
            "label": "떡볶이",
            "color": (200, 60, 40),
            "accent": (150, 30, 20),
        },
    ]

    # Cached assets: {name: pygame.Surface}
    _assets: dict[str, pygame.Surface] = {}
    _assets_loaded: bool = False

    @classmethod
    def _load_assets(cls) -> None:
        """Load frozen food assets (lazy loading)"""
        if cls._assets_loaded:
            return

        loader = AssetLoader()
        for food in cls.FOOD_TYPES:
            try:
                asset_path = f"ui/frozen_food_{food['name']}.png"
                image = loader.load_image(asset_path)
                # Scale to configured size
                scaled = pygame.transform.smoothscale(
                    image, (FROZEN_FOOD_SIZE, FROZEN_FOOD_SIZE)
                )
                cls._assets[food["name"]] = scaled
            except Exception:
                pass  # Asset not found, will use fallback rendering

        cls._assets_loaded = True

    def __init__(self, count: Optional[int] = None):
        """
        Initialize frozen food display.

        Args:
            count: Number of items to display (random if None)
        """
        self._load_assets()

        if count is None:
            count = random.randint(FROZEN_FOOD_MIN_COUNT, FROZEN_FOOD_MAX_COUNT)

        self.count = max(FROZEN_FOOD_MIN_COUNT, min(FROZEN_FOOD_MAX_COUNT, count))
        self.items = self._select_random_items()
        self.hover_offsets = [0.0] * self.count
        self.hover_timers = [random.uniform(0, 2 * 3.14159) for _ in range(self.count)]

    def _select_random_items(self) -> list[dict]:
        """Select random food items"""
        return random.sample(self.FOOD_TYPES, min(self.count, len(self.FOOD_TYPES)))

    def randomize(self) -> None:
        """Randomize food selection"""
        self.count = random.randint(FROZEN_FOOD_MIN_COUNT, FROZEN_FOOD_MAX_COUNT)
        self.items = self._select_random_items()
        self.hover_offsets = [0.0] * len(self.items)
        self.hover_timers = [
            random.uniform(0, 2 * 3.14159) for _ in range(len(self.items))
        ]

    def set_count(self, count: int) -> None:
        """Set specific food count (for soldier-specific data)"""
        self.count = max(FROZEN_FOOD_MIN_COUNT, min(FROZEN_FOOD_MAX_COUNT, count))
        self.items = self._select_random_items()
        self.hover_offsets = [0.0] * len(self.items)
        self.hover_timers = [
            random.uniform(0, 2 * 3.14159) for _ in range(len(self.items))
        ]

    def update(self, dt: float) -> None:
        """Update hover animation"""
        import math

        for i in range(len(self.items)):
            if i < len(self.hover_timers):
                self.hover_timers[i] += dt * 2
                if i < len(self.hover_offsets):
                    self.hover_offsets[i] = math.sin(self.hover_timers[i]) * 3

    def render(
        self,
        screen: pygame.Surface,
        center_x: Optional[int] = None,
        y: Optional[int] = None,
        alpha: int = 255,
    ) -> None:
        """
        Render frozen food items on the table.

        Args:
            screen: Pygame surface to render on
            center_x: Center X position (default: FROZEN_FOOD_TABLE_X from config)
            y: Y position (default: FROZEN_FOOD_TABLE_Y from config)
            alpha: Transparency (0-255)
        """
        if center_x is None:
            center_x = FROZEN_FOOD_TABLE_X
        if y is None:
            y = FROZEN_FOOD_TABLE_Y

        if not self.items:
            return

        # Calculate total width using config values
        total_width = (
            len(self.items) * FROZEN_FOOD_SIZE + (len(self.items) - 1) * FROZEN_FOOD_GAP
        )
        start_x = center_x - total_width // 2

        for i, item in enumerate(self.items):
            item_x = start_x + i * (FROZEN_FOOD_SIZE + FROZEN_FOOD_GAP)
            item_y = (
                y + int(self.hover_offsets[i]) if i < len(self.hover_offsets) else y
            )

            self._render_food_item(screen, item, item_x, item_y, alpha)

    def _render_food_item(
        self,
        screen: pygame.Surface,
        item: dict,
        x: int,
        y: int,
        alpha: int = 255,
    ) -> None:
        """Render a single food item (asset or fallback)"""
        food_name = item["name"]

        # Try to use loaded asset first
        if food_name in self._assets:
            asset = self._assets[food_name].copy()
            if alpha < 255:
                asset.set_alpha(alpha)
            screen.blit(asset, (x, y))
            return

        # Fallback: draw placeholder
        self._render_fallback(screen, item, x, y, alpha)

    def _render_fallback(
        self,
        screen: pygame.Surface,
        item: dict,
        x: int,
        y: int,
        alpha: int = 255,
    ) -> None:
        """Render fallback food icon when asset not found"""
        size = FROZEN_FOOD_SIZE

        # Create surface with alpha
        surface = pygame.Surface((size, size), pygame.SRCALPHA)

        # Draw food container (bowl/box shape)
        main_color = (*item["color"], alpha)
        accent_color = (*item["accent"], alpha)

        # Container body
        container_rect = pygame.Rect(4, size // 3, size - 8, size * 2 // 3 - 4)
        pygame.draw.rect(surface, main_color, container_rect, border_radius=5)
        pygame.draw.rect(
            surface, accent_color, container_rect, width=2, border_radius=5
        )

        # Steam/topping effect (circles on top)
        for j in range(3):
            steam_x = 10 + j * (size - 20) // 2
            steam_y = size // 3 - 5
            pygame.draw.circle(surface, main_color, (steam_x, steam_y), 8)

        # Food label background
        label_rect = pygame.Rect(2, size - 16, size - 4, 14)
        pygame.draw.rect(
            surface, (255, 255, 255, min(alpha, 200)), label_rect, border_radius=3
        )

        # Draw label text
        try:
            font = get_font(8)
            text = font.render(item["label"], True, (50, 50, 50))
            text_rect = text.get_rect(center=(size // 2, size - 9))
            surface.blit(text, text_rect)
        except Exception:
            pass

        screen.blit(surface, (x, y))

    def get_item_names(self) -> list[str]:
        """Get list of food item names"""
        return [item["label"] for item in self.items]

    @classmethod
    def reload_assets(cls) -> None:
        """Force reload of assets (useful after config changes)"""
        cls._assets.clear()
        cls._assets_loaded = False
        cls._load_assets()
