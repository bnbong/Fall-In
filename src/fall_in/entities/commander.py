"""
Commander - Wing Commander sprite with danger-based expressions and speech.
"""

import json
import math
import random

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
    COMMANDER_REACTION_DURATION,
    COMMANDER_RANDOM_DIALOGUE_MIN,
    COMMANDER_RANDOM_DIALOGUE_MAX,
    COMMANDER_RANDOM_DIALOGUE_DURATION,
    DATA_DIR,
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
    - Alt-expression reactions to high-danger soldier placements
    - Random dialogue via speech bubble
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

    # Alt expression keys (from commander_alt.png, 1x2 layout)
    ALT_EXPR_DANGER5 = "alt_danger5"  # right half - stern/angry
    ALT_EXPR_DANGER7 = "alt_danger7"  # left half - scared/sweating

    def __init__(self, x: int = COMMANDER_X, y: int = COMMANDER_Y):
        self.x = x
        self.y = y
        self.expression = CommanderExpression.NEUTRAL

        loader = AssetLoader()

        # Load main sprite sheet (2x2 grid)
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

        # Load alt expression sprites (commander_alt.png, 1x2 layout)
        alt_sheet = loader.load_image("characters/commander/commander_alt.png")
        alt_w = alt_sheet.get_width()
        alt_h = alt_sheet.get_height()
        half_w = alt_w // 2

        # Left half = scared/sweating (danger 7 reaction)
        left_rect = pygame.Rect(0, 0, half_w, alt_h)
        left_surface = alt_sheet.subsurface(left_rect).copy()
        self._alt_surfaces = {
            self.ALT_EXPR_DANGER7: pygame.transform.smoothscale(
                left_surface, (COMMANDER_WIDTH, COMMANDER_HEIGHT)
            ),
        }

        # Right half = stern/angry (danger 5 reaction)
        right_rect = pygame.Rect(half_w, 0, half_w, alt_h)
        right_surface = alt_sheet.subsurface(right_rect).copy()
        self._alt_surfaces[self.ALT_EXPR_DANGER5] = pygame.transform.smoothscale(
            right_surface, (COMMANDER_WIDTH, COMMANDER_HEIGHT)
        )

        # Reaction state (temporary alt expression on soldier placement)
        self._reaction_timer = 0.0
        self._reaction_active = False
        self._reaction_surface: pygame.Surface | None = None
        self._reaction_type: str | None = None  # "danger5" or "danger7"

        # Load surprise VFX image
        self._surprise_vfx = self._load_surprise_vfx(loader)

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

        # Random dialogue system
        self._dialogues = self._load_dialogues()
        self._dialogue_timer = random.uniform(
            COMMANDER_RANDOM_DIALOGUE_MIN, COMMANDER_RANDOM_DIALOGUE_MAX
        )

    # ------------------------------------------------------------------
    # Dialogue loading
    # ------------------------------------------------------------------

    @staticmethod
    def _load_dialogues() -> list[str]:
        """Load commander random dialogues from data/dialogues.json."""
        dialogues_path = DATA_DIR / "dialogues.json"
        try:
            with open(dialogues_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            lines = data.get("commander_random", [])
            if isinstance(lines, list) and lines:
                return lines
        except (FileNotFoundError, json.JSONDecodeError, KeyError):
            pass
        # Fallback if file is missing or malformed
        return ["..."]

    # ------------------------------------------------------------------
    # Expression & reaction
    # ------------------------------------------------------------------

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

    def react_to_soldier(self, danger: int) -> None:
        """Trigger a brief alt-expression when a high-danger soldier is placed.

        - danger 5 → stern/angry alt (right half of commander_alt.png)
        - danger 7 → scared/sweating alt (left half of commander_alt.png)
        """
        if danger == 5:
            self._reaction_surface = self._alt_surfaces.get(self.ALT_EXPR_DANGER5)
            self._reaction_type = "danger5"
        elif danger >= 7:
            self._reaction_surface = self._alt_surfaces.get(self.ALT_EXPR_DANGER7)
            self._reaction_type = "danger7"
        else:
            return

        self._reaction_active = True
        self._reaction_timer = COMMANDER_REACTION_DURATION

    def say(self, text: str, duration: float = 2.5) -> None:
        """Make commander say something in speech bubble."""
        self.speech_bubble.show(text, duration)

    def say_penalty_taken(self) -> None:
        """Default message when penalties are taken."""
        self.say("준비된 인원들 각자 위치로.", duration=2.0)

    # ------------------------------------------------------------------
    # Update
    # ------------------------------------------------------------------

    def update(self, dt: float) -> None:
        """Update commander state (idle bobbing + speech bubble + reactions + dialogue)."""
        # Idle bobbing
        self.idle_timer += dt
        self.idle_offset = int(math.sin(self.idle_timer * 2) * 3)

        # Speech bubble
        self.speech_bubble.update(dt)

        # Reaction timer (alt expression countdown)
        if self._reaction_active:
            self._reaction_timer -= dt
            if self._reaction_timer <= 0:
                self._reaction_active = False
                self._reaction_surface = None
                self._reaction_type = None

        # Random dialogue timer
        self._dialogue_timer -= dt
        if self._dialogue_timer <= 0:
            # Only speak if speech bubble is not already showing
            if not self.speech_bubble.is_visible() and self._dialogues:
                line = random.choice(self._dialogues)
                self.say(line, duration=COMMANDER_RANDOM_DIALOGUE_DURATION)
            # Reset timer for next dialogue
            self._dialogue_timer = random.uniform(
                COMMANDER_RANDOM_DIALOGUE_MIN, COMMANDER_RANDOM_DIALOGUE_MAX
            )

    # ------------------------------------------------------------------
    # Render
    # ------------------------------------------------------------------

    def render(self, screen: pygame.Surface) -> None:
        """Render commander sprite and speech bubble."""
        # Use alt reaction surface if active, otherwise normal expression
        if self._reaction_active and self._reaction_surface is not None:
            sprite = self._reaction_surface
        else:
            sprite = self.expression_surfaces.get(
                self.expression, self.expression_surfaces[CommanderExpression.NEUTRAL]
            )

        draw_x = self.x - COMMANDER_WIDTH // 2
        draw_y = self.y - COMMANDER_HEIGHT // 2 + self.idle_offset

        screen.blit(sprite, (draw_x, draw_y))

        # Draw reaction effect overlay
        if self._reaction_active and self._reaction_type:
            # Effect opacity based on remaining timer (fade out)
            alpha = min(1.0, self._reaction_timer / (COMMANDER_REACTION_DURATION * 0.3))
            effect_x = self.x + COMMANDER_WIDTH // 2 - 30
            effect_y = self.y - COMMANDER_HEIGHT // 2 + self.idle_offset + 60
            if self._reaction_type == "danger5":
                self._draw_surprise_effect(screen, effect_x, effect_y, alpha)
            elif self._reaction_type == "danger7":
                self._draw_exclamation_effect(screen, effect_x, effect_y, alpha)

        self.speech_bubble.render(screen)

    # ------------------------------------------------------------------
    # Reaction effect drawings
    # ------------------------------------------------------------------

    @staticmethod
    def _load_surprise_vfx(loader: AssetLoader) -> pygame.Surface | None:
        """Load the surprise VFX image."""
        try:
            img = loader.load_image("characters/commander/vfx_commander_surprised.png")
            # Scale to a reasonable effect size
            return pygame.transform.smoothscale(img, (80, 83))
        except Exception:
            return None

    def _draw_surprise_effect(
        self, screen: pygame.Surface, cx: int, cy: int, alpha: float
    ) -> None:
        """Draw surprise VFX image above the commander."""
        if self._surprise_vfx is None:
            return
        vfx = self._surprise_vfx.copy()
        vfx.set_alpha(int(255 * alpha))
        screen.blit(vfx, (cx - 40, cy - 40))

    @staticmethod
    def _draw_exclamation_effect(
        screen: pygame.Surface, cx: int, cy: int, alpha: float
    ) -> None:
        """Draw bold exclamation mark effect above the commander."""
        surf = pygame.Surface((50, 70), pygame.SRCALPHA)

        a = int(255 * alpha)
        color_red = (220, 40, 40, a)
        color_outline = (0, 0, 0, a)

        # Exclamation mark body (tapered rectangle)
        body_points = [(18, 5), (32, 5), (29, 42), (21, 42)]
        pygame.draw.polygon(surf, color_outline, body_points)
        inner_body = [(20, 8), (30, 8), (28, 40), (22, 40)]
        pygame.draw.polygon(surf, color_red, inner_body)

        # Exclamation mark dot
        pygame.draw.circle(surf, color_outline, (25, 52), 7)
        pygame.draw.circle(surf, color_red, (25, 52), 5)

        screen.blit(surf, (cx - 25, cy - 35))
