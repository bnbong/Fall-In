"""
Text utility functions - Common text rendering functions
"""

import pygame

from fall_in.config import WHITE


def draw_outlined_text(
    screen: pygame.Surface,
    text: str,
    font: pygame.font.Font,
    pos: tuple[int, int],
    color: tuple[int, int, int],
    outline_color: tuple[int, int, int] = WHITE,
    outline_offset: int = 1,
) -> None:
    """
    Draw text with outline for better readability.

    Args:
        screen: Surface to draw on
        text: Text string to render
        font: Font to use
        pos: (x, y) position tuple
        color: Main text color (RGB)
        outline_color: Outline color (RGB), defaults to white
        outline_offset: Pixel offset for outline, defaults to 1
    """
    x, y = pos

    # Draw outline (shadow in 4 directions)
    outline_surface = font.render(text, True, outline_color)
    for dx, dy in [
        (-outline_offset, -outline_offset),
        (-outline_offset, outline_offset),
        (outline_offset, -outline_offset),
        (outline_offset, outline_offset),
    ]:
        screen.blit(outline_surface, (x + dx, y + dy))

    # Draw main text on top
    text_surface = font.render(text, True, color)
    screen.blit(text_surface, pos)


def draw_centered_text(
    screen: pygame.Surface,
    text: str,
    font: pygame.font.Font,
    center: tuple[int, int],
    color: tuple[int, int, int],
) -> pygame.Rect:
    """
    Draw text centered at a position.

    Args:
        screen: Surface to draw on
        text: Text string to render
        font: Font to use
        center: (x, y) center position
        color: Text color (RGB)

    Returns:
        Rect of the rendered text
    """
    text_surface = font.render(text, True, color)
    text_rect = text_surface.get_rect(center=center)
    screen.blit(text_surface, text_rect)
    return text_rect
