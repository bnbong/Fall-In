"""
Commander - Wing Commander sprite with danger-based expressions and speech.
"""

import math

import pygame

from fall_in.ui.speech_bubble import SpeechBubble
from fall_in.utils.asset_loader import AssetLoader
from fall_in.config import (
    COMMANDER_X,
    COMMANDER_Y,
    COMMANDER_WIDTH,
    COMMANDER_HEIGHT,
    COMMANDER_SPEECH_BUBBLE_Y,
    COMMANDER_DANGER_THRESHOLDS,
)


class CommanderExpression:
    """Expression types for commander."""

    NEUTRAL = "neutral"
    PLEASED = "pleased"
    CONCERNED = "concerned"
    ANGRY = "angry"
    FURIOUS = "furious"


class Commander:
    """
    Wing Commander character with:
    - Danger-based expression changes
    - Speech bubble integration
    - Sprite sheet rendering (2x2 grid for expressions)
    """

    # Sprite sheet layout (2x2 grid)
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

    def __init__(self, x: int = COMMANDER_X, y: int = COMMANDER_Y):
        self.x = x
        self.y = y
        self.expression = CommanderExpression.NEUTRAL

        # Load sprite sheet
        loader = AssetLoader()
        self.sprite_sheet = loader.load_image("characters/commander/commander.png")

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
            scaled = pygame.transform.smoothscale(
                frame_surface, (COMMANDER_WIDTH, COMMANDER_HEIGHT)
            )
            self.expression_surfaces[expr] = scaled

        # Speech bubble (positioned to upper right of commander's head)
        self.speech_bubble = SpeechBubble(
            x=x + COMMANDER_WIDTH // 2,
            y=COMMANDER_SPEECH_BUBBLE_Y,
            max_width=200,
            tail_direction="left",
        )

        # Idle animation
        self.idle_timer = 0.0
        self.idle_offset = 0

    def set_expression_from_danger(self, danger_score: int) -> None:
        """Set expression based on player's cumulative danger score."""
        expression = CommanderExpression.PLEASED

        for threshold_str, expr_str in COMMANDER_DANGER_THRESHOLDS.items():
            threshold = (
                int(threshold_str) if isinstance(threshold_str, str) else threshold_str
            )
            if danger_score >= threshold:
                expression = expr_str

        self.expression = expression

    def say(self, text: str, duration: float = 2.5) -> None:
        """Make commander say something in speech bubble."""
        self.speech_bubble.show(text, duration)

    def say_penalty_taken(self) -> None:
        """Default message when penalties are taken."""
        self.say("준비된 인원들 각자 위치로.", duration=2.0)

    def update(self, dt: float) -> None:
        """Update commander state (idle bobbing + speech bubble)."""
        self.idle_timer += dt
        self.idle_offset = int(math.sin(self.idle_timer * 2) * 3)
        self.speech_bubble.update(dt)

    def render(self, screen: pygame.Surface) -> None:
        """Render commander sprite and speech bubble."""
        sprite = self.expression_surfaces.get(
            self.expression, self.expression_surfaces[CommanderExpression.NEUTRAL]
        )

        draw_x = self.x - COMMANDER_WIDTH // 2
        draw_y = self.y - COMMANDER_HEIGHT // 2 + self.idle_offset

        screen.blit(sprite, (draw_x, draw_y))
        self.speech_bubble.render(screen)
