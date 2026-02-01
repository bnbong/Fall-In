"""
Soldier Figure - Visual representation of soldier on the board
"""
import pygame
from typing import Optional

from fall_in.core.card import Card
from fall_in.utils.asset_loader import get_font
from fall_in.config import (
    AIR_FORCE_BLUE, WHITE,
    DANGER_SAFE, DANGER_WARNING, DANGER_DANGER
)


class SoldierFigure:
    """
    Visual representation of a soldier card on the isometric board.
    Currently uses placeholder graphics (capsule shape).
    """
    
    # Figure dimensions
    BODY_WIDTH = 28
    BODY_HEIGHT = 40
    HEAD_RADIUS = 12
    SHADOW_RADIUS = 14
    
    def __init__(self, card: Card):
        self.card = card
        self.animation_frame = 0
        self.animation_timer = 0.0
    
    def get_danger_color(self) -> tuple[int, int, int]:
        """Get color based on card danger level"""
        danger = self.card.danger
        if danger <= 2:
            return DANGER_SAFE
        elif danger <= 4:
            return DANGER_WARNING
        else:
            return DANGER_DANGER
    
    def update(self, dt: float) -> None:
        """Update animation state"""
        self.animation_timer += dt
        # Simple idle animation: bob up and down
        self.animation_frame = int(self.animation_timer * 2) % 4
    
    def render(
        self, 
        screen: pygame.Surface, 
        iso_x: int, 
        iso_y: int,
        tile_height: int = 30
    ) -> None:
        """
        Render soldier figure at isometric position.
        
        Args:
            screen: Surface to draw on
            iso_x: Center X position in screen coordinates
            iso_y: Center Y position of the tile
            tile_height: Height of the isometric tile for positioning
        """
        # Calculate figure position (figure stands on the tile)
        # Add small bob animation
        bob_offset = [0, -2, 0, 2][self.animation_frame]
        
        base_y = iso_y - tile_height // 4  # Adjust to sit on tile
        figure_center_y = base_y - self.BODY_HEIGHT // 2 + bob_offset
        
        # 1. Draw shadow (ellipse on ground)
        shadow_rect = pygame.Rect(
            iso_x - self.SHADOW_RADIUS,
            iso_y - self.SHADOW_RADIUS // 3,
            self.SHADOW_RADIUS * 2,
            self.SHADOW_RADIUS * 2 // 3
        )
        pygame.draw.ellipse(screen, (50, 50, 50, 100), shadow_rect)
        
        # 2. Draw body (rounded rectangle / capsule)
        body_color = self.get_danger_color()
        body_rect = pygame.Rect(
            iso_x - self.BODY_WIDTH // 2,
            figure_center_y,
            self.BODY_WIDTH,
            self.BODY_HEIGHT
        )
        pygame.draw.rect(screen, body_color, body_rect, border_radius=8)
        pygame.draw.rect(screen, AIR_FORCE_BLUE, body_rect, width=2, border_radius=8)
        
        # 3. Draw head (circle)
        head_y = figure_center_y - self.HEAD_RADIUS + 5
        pygame.draw.circle(screen, (255, 220, 180), (iso_x, head_y), self.HEAD_RADIUS)
        pygame.draw.circle(screen, AIR_FORCE_BLUE, (iso_x, head_y), self.HEAD_RADIUS, width=2)
        
        # 4. Draw helmet (arc on top of head)
        helmet_rect = pygame.Rect(
            iso_x - self.HEAD_RADIUS,
            head_y - self.HEAD_RADIUS,
            self.HEAD_RADIUS * 2,
            self.HEAD_RADIUS * 2
        )
        pygame.draw.arc(screen, AIR_FORCE_BLUE, helmet_rect, 0.5, 2.6, width=4)
        
        # 5. Draw number above head
        font = get_font(14, "bold")
        number_text = font.render(str(self.card.number), True, WHITE)
        
        # Number background
        text_rect = number_text.get_rect(center=(iso_x, head_y - self.HEAD_RADIUS - 12))
        bg_rect = text_rect.inflate(8, 4)
        pygame.draw.rect(screen, AIR_FORCE_BLUE, bg_rect, border_radius=4)
        
        screen.blit(number_text, text_rect)


def render_soldier_placeholder(
    screen: pygame.Surface,
    card: Card,
    iso_x: int,
    iso_y: int
) -> None:
    """Convenience function to render a soldier figure"""
    figure = SoldierFigure(card)
    figure.render(screen, iso_x, iso_y)
