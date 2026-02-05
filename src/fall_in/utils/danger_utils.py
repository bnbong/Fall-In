"""
Danger utility functions - Common danger level related functions
"""

from enum import Enum

from fall_in.config import (
    DANGER_SAFE,
    DANGER_CAUTION,
    DANGER_WARNING,
    DANGER_DANGER,
    DANGER_CRITICAL,
)


class TileType(Enum):
    """Tile types for board rendering"""

    EMPTY = "empty"
    SAFE = "safe"
    WARNING = "warning"
    DANGER = "danger"


class DangerLevel(Enum):
    """Danger level names"""

    SAFE = "안전"
    CAUTION = "주의"
    WARNING = "경고"
    DANGER = "위험"
    CRITICAL = "극한"


def get_danger_color(score: int) -> tuple[int, int, int]:
    """
    Get color based on cumulative danger score.

    Args:
        score: Cumulative danger score (0-66+)

    Returns:
        RGB color tuple
    """
    if score < 20:
        return DANGER_SAFE
    elif score < 35:
        return DANGER_CAUTION
    elif score < 50:
        return DANGER_WARNING
    elif score < 60:
        return DANGER_DANGER
    else:
        return DANGER_CRITICAL


def get_danger_level(score: int) -> DangerLevel:
    """
    Get danger level enum based on cumulative score.

    Args:
        score: Cumulative danger score

    Returns:
        DangerLevel enum value
    """
    if score < 20:
        return DangerLevel.SAFE
    elif score < 35:
        return DangerLevel.CAUTION
    elif score < 50:
        return DangerLevel.WARNING
    elif score < 60:
        return DangerLevel.DANGER
    else:
        return DangerLevel.CRITICAL


def get_tile_type_by_danger(danger: int) -> TileType:
    """
    Get tile type based on card danger level.

    Args:
        danger: Card danger level (1-7)

    Returns:
        TileType enum value
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

    Args:
        danger: Card danger level (1-7)

    Returns:
        RGB color tuple
    """
    if danger >= 7:
        return (100, 50, 150)  # Purple
    elif danger >= 5:
        return (200, 50, 50)  # Red
    elif danger >= 3:
        return (230, 150, 50)  # Orange
    elif danger >= 2:
        return (200, 180, 50)  # Yellow
    else:
        return (100, 150, 100)  # Green
