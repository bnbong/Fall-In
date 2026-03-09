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

    # Draw outline by blitting at every offset in a grid for a smooth, connected look
    outline_surface = font.render(text, True, outline_color)
    for dx in range(-outline_offset, outline_offset + 1):
        for dy in range(-outline_offset, outline_offset + 1):
            if dx == 0 and dy == 0:
                continue
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


def wrap_text(text: str, font: pygame.font.Font, max_width: int) -> list[str]:
    """
    Wrap text to fit within a given pixel width, splitting on existing
    newlines first, then wrapping long lines character-by-character.

    Character-level wrapping is used because Korean text does not rely
    on spaces for word boundaries the way English does.

    Args:
        text: The text to wrap (may contain ``\\n`` for explicit line breaks).
        font: A pygame Font used to measure rendered width.
        max_width: Maximum pixel width per line.

    Returns:
        A list of strings, each fitting within *max_width* when rendered
        with *font*.
    """
    if max_width <= 0:
        return [text]

    wrapped_lines: list[str] = []

    for paragraph in text.split("\n"):
        paragraph = paragraph.strip()
        if not paragraph:
            wrapped_lines.append("")
            continue

        current_line = ""
        for char in paragraph:
            test_line = current_line + char
            if font.size(test_line)[0] <= max_width:
                current_line = test_line
            else:
                if current_line:
                    wrapped_lines.append(current_line)
                current_line = char

        if current_line:
            wrapped_lines.append(current_line)

    return wrapped_lines if wrapped_lines else [""]
