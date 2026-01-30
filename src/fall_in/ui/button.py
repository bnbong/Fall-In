"""
Button UI Component
"""
from typing import Callable, Optional

import pygame

from fall_in.config import AIR_FORCE_BLUE, WHITE, LIGHT_BLUE
from fall_in.utils.asset_loader import get_font


class Button:
    """
    Clickable button UI component.
    """
    
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
        text_color: tuple = WHITE
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
    
    def handle_event(self, event: pygame.event.Event) -> None:
        """Handle mouse events"""
        if event.type == pygame.MOUSEMOTION:
            self.is_hovered = self.rect.collidepoint(event.pos)
        
        elif event.type == pygame.MOUSEBUTTONDOWN:
            if event.button == 1 and self.is_hovered:
                self.is_pressed = True
        
        elif event.type == pygame.MOUSEBUTTONUP:
            if event.button == 1 and self.is_pressed and self.is_hovered:
                if self.callback:
                    self.callback()
            self.is_pressed = False
    
    def update(self, dt: float) -> None:
        """Update button state"""
        pass
    
    def render(self, screen: pygame.Surface) -> None:
        """Render button"""
        # Draw button background
        color = self.hover_color if self.is_hovered else self.bg_color
        pygame.draw.rect(screen, color, self.rect, border_radius=8)
        
        # Draw border
        pygame.draw.rect(screen, WHITE, self.rect, width=2, border_radius=8)
        
        # Draw text using Korean font
        font = get_font(self.font_size)
        text_surface = font.render(self.text, True, self.text_color)
        text_rect = text_surface.get_rect(center=self.rect.center)
        screen.blit(text_surface, text_rect)

