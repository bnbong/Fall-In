"""
Speech Bubble - Reusable animated speech bubble component
"""
import pygame
from typing import Optional

from fall_in.utils.asset_loader import get_font
from fall_in.config import AIR_FORCE_BLUE, WHITE


class SpeechBubble:
    """
    Animated speech bubble that can appear and disappear.
    Reusable across different scenes.
    """
    
    # Animation states
    STATE_HIDDEN = 0
    STATE_APPEARING = 1
    STATE_VISIBLE = 2
    STATE_DISAPPEARING = 3
    
    # Animation durations (seconds)
    APPEAR_DURATION = 0.3
    VISIBLE_DURATION = 2.5
    DISAPPEAR_DURATION = 0.3
    
    def __init__(
        self,
        x: int,
        y: int,
        max_width: int = 200,
        tail_direction: str = "left"  # "left", "right", "bottom"
    ):
        self.x = x
        self.y = y
        self.max_width = max_width
        self.tail_direction = tail_direction
        
        self.text = ""
        self.state = self.STATE_HIDDEN
        self.timer = 0.0
        self.alpha = 0  # 0-255
        
        # Cached surfaces
        self._bubble_surface: Optional[pygame.Surface] = None
        self._needs_rebuild = True
    
    def show(self, text: str, duration: Optional[float] = None) -> None:
        """Show speech bubble with text"""
        self.text = text
        self.state = self.STATE_APPEARING
        self.timer = 0.0
        self._needs_rebuild = True
        
        if duration is not None:
            self.VISIBLE_DURATION = duration
    
    def hide(self) -> None:
        """Start hiding animation"""
        if self.state == self.STATE_VISIBLE:
            self.state = self.STATE_DISAPPEARING
            self.timer = 0.0
    
    def is_visible(self) -> bool:
        """Check if bubble is currently visible or animating"""
        return self.state != self.STATE_HIDDEN
    
    def update(self, dt: float) -> None:
        """Update animation state"""
        if self.state == self.STATE_HIDDEN:
            return
        
        self.timer += dt
        
        if self.state == self.STATE_APPEARING:
            progress = min(self.timer / self.APPEAR_DURATION, 1.0)
            self.alpha = int(255 * progress)
            
            if progress >= 1.0:
                self.state = self.STATE_VISIBLE
                self.timer = 0.0
                self.alpha = 255
        
        elif self.state == self.STATE_VISIBLE:
            if self.timer >= self.VISIBLE_DURATION:
                self.state = self.STATE_DISAPPEARING
                self.timer = 0.0
        
        elif self.state == self.STATE_DISAPPEARING:
            progress = min(self.timer / self.DISAPPEAR_DURATION, 1.0)
            self.alpha = int(255 * (1.0 - progress))
            
            if progress >= 1.0:
                self.state = self.STATE_HIDDEN
                self.alpha = 0
    
    def _build_bubble(self) -> pygame.Surface:
        """Build the speech bubble surface"""
        font = get_font(14)
        padding = 12
        tail_size = 15
        
        # Word wrap text
        words = self.text.split()
        lines = []
        current_line = ""
        
        for word in words:
            test_line = f"{current_line} {word}".strip()
            if font.size(test_line)[0] <= self.max_width - padding * 2:
                current_line = test_line
            else:
                if current_line:
                    lines.append(current_line)
                current_line = word
        if current_line:
            lines.append(current_line)
        
        # Calculate bubble size
        line_height = font.get_height()
        text_height = len(lines) * line_height
        text_width = max(font.size(line)[0] for line in lines) if lines else 50
        
        bubble_width = text_width + padding * 2
        bubble_height = text_height + padding * 2
        
        # Create surface with extra space for tail
        extra = tail_size if self.tail_direction in ("left", "right") else 0
        surface = pygame.Surface(
            (bubble_width + extra, bubble_height + tail_size),
            pygame.SRCALPHA
        )
        
        # Bubble body offset
        body_x = tail_size if self.tail_direction == "left" else 0
        body_y = 0
        
        # Draw bubble body
        body_rect = pygame.Rect(body_x, body_y, bubble_width, bubble_height)
        pygame.draw.rect(surface, WHITE, body_rect, border_radius=10)
        pygame.draw.rect(surface, AIR_FORCE_BLUE, body_rect, width=2, border_radius=10)
        
        # Draw tail
        if self.tail_direction == "left":
            tail_points = [
                (body_x, bubble_height // 2 - 5),
                (0, bubble_height // 2 + 5),
                (body_x, bubble_height // 2 + 10),
            ]
        elif self.tail_direction == "right":
            tail_points = [
                (bubble_width, bubble_height // 2 - 5),
                (bubble_width + tail_size, bubble_height // 2 + 5),
                (bubble_width, bubble_height // 2 + 10),
            ]
        else:  # bottom
            tail_points = [
                (bubble_width // 2 - 8, bubble_height),
                (bubble_width // 2, bubble_height + tail_size),
                (bubble_width // 2 + 8, bubble_height),
            ]
        
        pygame.draw.polygon(surface, WHITE, tail_points)
        pygame.draw.lines(surface, AIR_FORCE_BLUE, False, tail_points[:2], 2)
        pygame.draw.lines(surface, AIR_FORCE_BLUE, False, tail_points[1:], 2)
        
        # Render text
        for i, line in enumerate(lines):
            text_surface = font.render(line, True, AIR_FORCE_BLUE)
            surface.blit(text_surface, (body_x + padding, body_y + padding + i * line_height))
        
        return surface
    
    def render(self, screen: pygame.Surface) -> None:
        """Render speech bubble"""
        if self.state == self.STATE_HIDDEN or self.alpha <= 0:
            return
        
        if self._needs_rebuild:
            self._bubble_surface = self._build_bubble()
            self._needs_rebuild = False
        
        if self._bubble_surface:
            # Apply alpha
            temp_surface = self._bubble_surface.copy()
            temp_surface.set_alpha(self.alpha)
            
            # Position based on tail direction
            if self.tail_direction == "left":
                pos = (self.x, self.y - temp_surface.get_height() // 2)
            elif self.tail_direction == "right":
                pos = (self.x - temp_surface.get_width(), self.y - temp_surface.get_height() // 2)
            else:
                pos = (self.x - temp_surface.get_width() // 2, self.y - temp_surface.get_height())
            
            screen.blit(temp_surface, pos)
