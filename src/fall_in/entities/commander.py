"""
Commander - Wing Commander sprite with expressions
"""

import math

import pygame

from fall_in.ui.speech_bubble import SpeechBubble
from fall_in.utils.asset_loader import AssetLoader


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
    - Sprite sheet rendering (4 quadrants for expressions)
    """

    # Position (left side of screen, partially off-screen to show thighs and above)
    DEFAULT_X = 100  # Centered horizontally at left
    DEFAULT_Y = 520  # Pushed down so lower body is cut off

    # Sprite sheet layout (2x2 grid)
    # Q1 (top-right) = ANGRY
    # Q2 (top-left) = CONCERNED
    # Q3 (bottom-left) = NEUTRAL/PLEASED (default)
    # Q4 (bottom-right) = FURIOUS
    SPRITE_SHEET_COLS = 2
    SPRITE_SHEET_ROWS = 2

    # Mapping expressions to sprite quadrants (col, row) - 0-indexed
    EXPRESSION_SPRITES = {
        CommanderExpression.NEUTRAL: (0, 1),  # Q3 - bottom-left
        CommanderExpression.PLEASED: (0, 1),  # Q3 - same as neutral
        CommanderExpression.CONCERNED: (0, 0),  # Q2 - top-left
        CommanderExpression.ANGRY: (1, 0),  # Q1 - top-right
        CommanderExpression.FURIOUS: (1, 1),  # Q4 - bottom-right
    }

    # Display size (larger, maintaining aspect ratio)
    # Original frame: 640x1648, ratio ~1:2.575
    DISPLAY_WIDTH = 250
    DISPLAY_HEIGHT = 680

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

        # Load sprite sheet
        loader = AssetLoader()
        self.sprite_sheet = loader.load_image("characters/commander/commander.png")

        # Calculate frame dimensions from sprite sheet
        sheet_width = self.sprite_sheet.get_width()
        sheet_height = self.sprite_sheet.get_height()
        self.frame_width = sheet_width // self.SPRITE_SHEET_COLS
        self.frame_height = sheet_height // self.SPRITE_SHEET_ROWS

        # Pre-extract and scale expression sprites
        self.expression_surfaces = {}
        for expr, (col, row) in self.EXPRESSION_SPRITES.items():
            frame_rect = pygame.Rect(
                col * self.frame_width,
                row * self.frame_height,
                self.frame_width,
                self.frame_height,
            )
            frame_surface = self.sprite_sheet.subsurface(frame_rect).copy()
            # Scale to display size
            scaled = pygame.transform.scale(
                frame_surface, (self.DISPLAY_WIDTH, self.DISPLAY_HEIGHT)
            )
            self.expression_surfaces[expr] = scaled

        # Speech bubble (positioned to upper right of commander's head)
        self.speech_bubble = SpeechBubble(
            x=x + self.DISPLAY_WIDTH // 2,
            y=365,  # Fixed near top of screen
            max_width=200,
            tail_direction="left",
        )

        # Idle animation
        self.idle_timer = 0.0
        self.idle_offset = 0

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
        # Subtle bobbing animation
        self.idle_offset = int(math.sin(self.idle_timer * 2) * 3)

        self.speech_bubble.update(dt)

    def render(self, screen: pygame.Surface) -> None:
        """Render commander sprite and speech bubble"""
        # Get current expression sprite
        sprite = self.expression_surfaces.get(
            self.expression, self.expression_surfaces[CommanderExpression.NEUTRAL]
        )

        # Calculate position (centered on x, y with idle offset)
        draw_x = self.x - self.DISPLAY_WIDTH // 2
        draw_y = self.y - self.DISPLAY_HEIGHT // 2 + self.idle_offset

        # Draw sprite
        screen.blit(sprite, (draw_x, draw_y))

        # Draw speech bubble
        self.speech_bubble.render(screen)
