"""
Commander - Wing Commander sprite with expressions
"""
import pygame
from typing import Optional

from fall_in.utils.asset_loader import get_font
from fall_in.ui.speech_bubble import SpeechBubble
from fall_in.config import AIR_FORCE_BLUE, WHITE, LIGHT_BLUE


class CommanderExpression:
    """Expression types for commander"""
    NEUTRAL = "neutral"
    PLEASED = "pleased"
    CONCERNED = "concerned"
    ANGRY = "angry"
    FURIOUS = "furious"


class Commander:
    """
    Wing Commander (비행단장) character with:
    - Danger-based expression changes
    - Speech bubble integration
    - Placeholder sprite rendering
    """
    
    # Position (left side of screen)
    DEFAULT_X = 80
    DEFAULT_Y = 400
    
    # Placeholder dimensions
    WIDTH = 120
    HEIGHT = 180
    
    # Expression colors (face tint for placeholder)
    EXPRESSION_COLORS = {
        CommanderExpression.NEUTRAL: (255, 220, 180),    # Normal skin
        CommanderExpression.PLEASED: (255, 230, 200),    # Slight glow
        CommanderExpression.CONCERNED: (255, 210, 170),  # Slightly worried
        CommanderExpression.ANGRY: (255, 190, 160),      # Flushed
        CommanderExpression.FURIOUS: (255, 150, 140),    # Very red
    }
    
    # Danger thresholds for expression changes
    DANGER_THRESHOLDS = {
        0: CommanderExpression.PLEASED,
        15: CommanderExpression.NEUTRAL,
        30: CommanderExpression.CONCERNED,
        45: CommanderExpression.ANGRY,
        55: CommanderExpression.FURIOUS,
    }
    
    def __init__(self, x: int = DEFAULT_X, y: int = DEFAULT_Y):
        self.x = x
        self.y = y
        self.expression = CommanderExpression.NEUTRAL
        
        # Speech bubble (positioned to the right of commander)
        self.speech_bubble = SpeechBubble(
            x=x + self.WIDTH // 2 + 10,
            y=y - self.HEIGHT // 2 + 30,
            max_width=180,
            tail_direction="left"
        )
        
        # Idle animation
        self.idle_timer = 0.0
        self.idle_frame = 0
    
    def set_expression_from_danger(self, danger_score: int) -> None:
        """Set expression based on player's danger score"""
        expression = CommanderExpression.PLEASED
        
        for threshold, expr in self.DANGER_THRESHOLDS.items():
            if danger_score >= threshold:
                expression = expr
        
        self.expression = expression
    
    def say(self, text: str, duration: float = 2.5) -> None:
        """Make commander say something in speech bubble"""
        self.speech_bubble.show(text, duration)
    
    def say_penalty_taken(self) -> None:
        """Default message when penalties are taken"""
        self.say("준비된 인원들 각자 위치로.", duration=2.0)
    
    def update(self, dt: float) -> None:
        """Update commander state"""
        self.idle_timer += dt
        self.idle_frame = int(self.idle_timer * 2) % 4
        
        self.speech_bubble.update(dt)
    
    def _draw_placeholder(self, screen: pygame.Surface) -> None:
        """Draw placeholder commander sprite"""
        # Body (uniform)
        body_rect = pygame.Rect(
            self.x - self.WIDTH // 2,
            self.y - self.HEIGHT // 2 + 40,
            self.WIDTH,
            self.HEIGHT - 40
        )
        pygame.draw.rect(screen, AIR_FORCE_BLUE, body_rect, border_radius=10)
        
        # Shoulders
        pygame.draw.ellipse(
            screen, AIR_FORCE_BLUE,
            (self.x - self.WIDTH // 2 - 15, self.y - self.HEIGHT // 2 + 35, 30, 20)
        )
        pygame.draw.ellipse(
            screen, AIR_FORCE_BLUE,
            (self.x + self.WIDTH // 2 - 15, self.y - self.HEIGHT // 2 + 35, 30, 20)
        )
        
        # Head
        face_color = self.EXPRESSION_COLORS.get(
            self.expression, self.EXPRESSION_COLORS[CommanderExpression.NEUTRAL]
        )
        head_y = self.y - self.HEIGHT // 2 + 20
        pygame.draw.circle(screen, face_color, (self.x, head_y), 35)
        pygame.draw.circle(screen, AIR_FORCE_BLUE, (self.x, head_y), 35, width=2)
        
        # Hat
        hat_rect = pygame.Rect(self.x - 40, head_y - 45, 80, 25)
        pygame.draw.rect(screen, AIR_FORCE_BLUE, hat_rect, border_radius=5)
        pygame.draw.rect(screen, (50, 80, 120), (self.x - 30, head_y - 50, 60, 10), border_radius=3)
        
        # Hat badge
        pygame.draw.circle(screen, (255, 215, 0), (self.x, head_y - 35), 8)
        
        # Eyes based on expression
        eye_y = head_y - 5
        if self.expression == CommanderExpression.PLEASED:
            # Happy closed eyes (arcs)
            pygame.draw.arc(screen, AIR_FORCE_BLUE, (self.x - 18, eye_y - 5, 12, 10), 3.14, 6.28, 2)
            pygame.draw.arc(screen, AIR_FORCE_BLUE, (self.x + 6, eye_y - 5, 12, 10), 3.14, 6.28, 2)
        elif self.expression == CommanderExpression.FURIOUS:
            # Angry eyes (angled)
            pygame.draw.line(screen, AIR_FORCE_BLUE, (self.x - 20, eye_y - 8), (self.x - 8, eye_y - 3), 3)
            pygame.draw.line(screen, AIR_FORCE_BLUE, (self.x + 8, eye_y - 3), (self.x + 20, eye_y - 8), 3)
            pygame.draw.circle(screen, AIR_FORCE_BLUE, (self.x - 12, eye_y), 4)
            pygame.draw.circle(screen, AIR_FORCE_BLUE, (self.x + 12, eye_y), 4)
        elif self.expression == CommanderExpression.ANGRY:
            # Annoyed eyes
            pygame.draw.line(screen, AIR_FORCE_BLUE, (self.x - 18, eye_y - 5), (self.x - 8, eye_y - 2), 2)
            pygame.draw.line(screen, AIR_FORCE_BLUE, (self.x + 8, eye_y - 2), (self.x + 18, eye_y - 5), 2)
            pygame.draw.circle(screen, AIR_FORCE_BLUE, (self.x - 12, eye_y), 4)
            pygame.draw.circle(screen, AIR_FORCE_BLUE, (self.x + 12, eye_y), 4)
        else:
            # Normal eyes
            pygame.draw.circle(screen, AIR_FORCE_BLUE, (self.x - 12, eye_y), 4)
            pygame.draw.circle(screen, AIR_FORCE_BLUE, (self.x + 12, eye_y), 4)
        
        # Mouth based on expression
        mouth_y = head_y + 12
        if self.expression == CommanderExpression.PLEASED:
            pygame.draw.arc(screen, AIR_FORCE_BLUE, (self.x - 12, mouth_y - 8, 24, 16), 3.14, 6.28, 2)
        elif self.expression in (CommanderExpression.ANGRY, CommanderExpression.FURIOUS):
            pygame.draw.arc(screen, AIR_FORCE_BLUE, (self.x - 12, mouth_y, 24, 12), 0, 3.14, 2)
        elif self.expression == CommanderExpression.CONCERNED:
            pygame.draw.line(screen, AIR_FORCE_BLUE, (self.x - 10, mouth_y + 2), (self.x + 10, mouth_y - 2), 2)
        else:
            pygame.draw.line(screen, AIR_FORCE_BLUE, (self.x - 10, mouth_y), (self.x + 10, mouth_y), 2)
        
        # Rank insignia on shoulders
        for dx in [-self.WIDTH // 2 + 15, self.WIDTH // 2 - 15]:
            pygame.draw.rect(screen, (255, 215, 0), (self.x + dx - 8, body_rect.y + 10, 16, 4))
            pygame.draw.rect(screen, (255, 215, 0), (self.x + dx - 8, body_rect.y + 18, 16, 4))
        
        # Arms crossed (simple)
        pygame.draw.ellipse(
            screen, AIR_FORCE_BLUE,
            (self.x - 40, self.y - 20, 80, 40)
        )
    
    def render(self, screen: pygame.Surface) -> None:
        """Render commander and speech bubble"""
        self._draw_placeholder(screen)
        self.speech_bubble.render(screen)
