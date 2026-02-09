"""
Danger utility functions - Shared danger level logic for colors, tiles, and labels.

Provides a single source of truth for danger-related color mappings and
score-to-level conversions used across the entire game.
"""

from enum import Enum

from fall_in.config import (
    DANGER_SAFE,
    DANGER_CAUTION,
    DANGER_WARNING,
    DANGER_DANGER,
    DANGER_CRITICAL,
    DANGER_LEVEL_COLORS,
    DANGER_SCORE_THRESHOLDS,
)


class TileType(Enum):
    """Tile visual types for board rendering."""

    EMPTY = "empty"
    SAFE = "safe"
    WARNING = "warning"
    DANGER = "danger"


class DangerLevel(Enum):
    """Named danger levels for cumulative score display."""

    SAFE = "안전"
    CAUTION = "주의"
    WARNING = "경고"
    DANGER = "위험"
    CRITICAL = "극한"


def get_danger_color(score: int) -> tuple[int, int, int]:
    """
    Get color based on cumulative danger score.

    Args:
        score: Cumulative danger score (0-66+).

    Returns:
        RGB color tuple.
    """
    if score < DANGER_SCORE_THRESHOLDS["caution"]:
        return DANGER_SAFE
    elif score < DANGER_SCORE_THRESHOLDS["warning"]:
        return DANGER_CAUTION
    elif score < DANGER_SCORE_THRESHOLDS["danger"]:
        return DANGER_WARNING
    elif score < DANGER_SCORE_THRESHOLDS["critical"]:
        return DANGER_DANGER
    else:
        return DANGER_CRITICAL


def get_danger_level(score: int) -> DangerLevel:
    """
    Get danger level enum based on cumulative score.

    Args:
        score: Cumulative danger score.

    Returns:
        DangerLevel enum value.
    """
    if score < DANGER_SCORE_THRESHOLDS["caution"]:
        return DangerLevel.SAFE
    elif score < DANGER_SCORE_THRESHOLDS["warning"]:
        return DangerLevel.CAUTION
    elif score < DANGER_SCORE_THRESHOLDS["danger"]:
        return DangerLevel.WARNING
    elif score < DANGER_SCORE_THRESHOLDS["critical"]:
        return DangerLevel.DANGER
    else:
        return DangerLevel.CRITICAL


def get_danger_level_name(score: int) -> str:
    """
    Get Korean danger level name for a cumulative score.

    Args:
        score: Cumulative danger score.

    Returns:
        Korean danger level string.
    """
    if score < DANGER_SCORE_THRESHOLDS["caution"]:
        return "안전"
    elif score < DANGER_SCORE_THRESHOLDS["warning"]:
        return "주의"
    elif score < DANGER_SCORE_THRESHOLDS["danger"]:
        return "경고"
    elif score < DANGER_SCORE_THRESHOLDS["critical"]:
        return "위험"
    elif score < DANGER_SCORE_THRESHOLDS["eliminated"]:
        return "극한"
    else:
        return "탈락"


def get_tile_type_by_danger(danger: int) -> TileType:
    """
    Get tile type based on individual card danger level.

    Args:
        danger: Card danger level (1-7).

    Returns:
        TileType enum value.
    """
    if danger <= 2:
        return TileType.SAFE
    elif danger <= 4:
        return TileType.WARNING
    else:
        return TileType.DANGER


def get_danger_circle_color(danger: int) -> tuple[int, int, int]:
    """
    Get circle background color for card number display based on danger level.

    Uses the centralized DANGER_LEVEL_COLORS from config. Falls back to the
    closest available key for intermediate danger levels (e.g. 4 -> 3, 6 -> 5).

    Args:
        danger: Card danger level (1-7).

    Returns:
        RGB color tuple.
    """
    if danger in DANGER_LEVEL_COLORS:
        return DANGER_LEVEL_COLORS[danger]

    # Fall back to closest available key
    if danger <= 1:
        return DANGER_LEVEL_COLORS[1]
    elif danger <= 2:
        return DANGER_LEVEL_COLORS[2]
    elif danger <= 3:
        return DANGER_LEVEL_COLORS[3]
    elif danger <= 5:
        return DANGER_LEVEL_COLORS[5]
    else:
        return DANGER_LEVEL_COLORS[7]
