"""
Tween - Smooth value interpolation for animations
"""

import math
from typing import Callable, Optional, Union


# Easing functions
def ease_linear(t: float) -> float:
    return t


def ease_in_quad(t: float) -> float:
    return t * t


def ease_out_quad(t: float) -> float:
    return 1 - (1 - t) * (1 - t)


def ease_in_out_quad(t: float) -> float:
    return 2 * t * t if t < 0.5 else 1 - pow(-2 * t + 2, 2) / 2


def ease_out_back(t: float) -> float:
    c1 = 1.70158
    c3 = c1 + 1
    return 1 + c3 * pow(t - 1, 3) + c1 * pow(t - 1, 2)


def ease_out_elastic(t: float) -> float:
    if t == 0 or t == 1:
        return t
    c4 = (2 * math.pi) / 3
    return pow(2, -10 * t) * math.sin((t * 10 - 0.75) * c4) + 1


EASING_FUNCTIONS = {
    "linear": ease_linear,
    "ease_in": ease_in_quad,
    "ease_out": ease_out_quad,
    "ease_in_out": ease_in_out_quad,
    "ease_out_back": ease_out_back,
    "ease_out_elastic": ease_out_elastic,
}


class Tween:
    """
    Animate a value from start to end over a duration.
    Supports various easing functions and optional delay.
    """

    def __init__(
        self,
        start: Union[float, tuple[float, float]],
        end: Union[float, tuple[float, float]],
        duration: float,
        easing: str = "ease_out",
        on_complete: Optional[Callable] = None,
        delay: float = 0.0,
    ):
        self.start = start
        self.end = end
        self.duration = duration
        self.easing_func = EASING_FUNCTIONS.get(easing, ease_out_quad)
        self.on_complete = on_complete
        self.delay = delay

        self.elapsed = 0.0
        self.delay_elapsed = 0.0
        self.is_complete = False
        self.is_started = delay <= 0
        self._is_tuple = isinstance(start, tuple)

    def update(self, dt: float) -> bool:
        """
        Update tween. Returns True if tween just completed this frame.
        """
        if self.is_complete:
            return False

        # Handle delay first
        if not self.is_started:
            self.delay_elapsed += dt
            if self.delay_elapsed >= self.delay:
                self.is_started = True
            else:
                return False

        self.elapsed += dt

        if self.elapsed >= self.duration:
            self.elapsed = self.duration
            self.is_complete = True
            if self.on_complete:
                self.on_complete()
            return True

        return False

    def get_progress(self) -> float:
        """Get raw progress (0-1)"""
        return min(self.elapsed / self.duration, 1.0)

    def get_eased_progress(self) -> float:
        """Get eased progress (0-1)"""
        return self.easing_func(self.get_progress())

    def get_current(self) -> Union[float, tuple[float, float]]:
        """Get current interpolated value"""
        t = self.get_eased_progress()

        if self._is_tuple:
            return (
                self.start[0] + (self.end[0] - self.start[0]) * t,
                self.start[1] + (self.end[1] - self.start[1]) * t,
            )
        else:
            return self.start + (self.end - self.start) * t

    def get_current_int(self) -> Union[int, tuple[int, int]]:
        """Get current value as integer(s)"""
        current = self.get_current()
        if self._is_tuple:
            return (int(current[0]), int(current[1]))
        return int(current)


class TweenSequence:
    """Run multiple tweens in sequence"""

    def __init__(self, tweens: list[Tween]):
        self.tweens = tweens
        self.current_index = 0

    @property
    def is_complete(self) -> bool:
        return self.current_index >= len(self.tweens)

    @property
    def current_tween(self) -> Optional[Tween]:
        if self.is_complete:
            return None
        return self.tweens[self.current_index]

    def update(self, dt: float) -> bool:
        """Update current tween. Returns True when all complete."""
        if self.is_complete:
            return True

        if self.tweens[self.current_index].update(dt):
            self.current_index += 1

        return self.is_complete


class TweenGroup:
    """Run multiple tweens in parallel"""

    def __init__(self):
        self.tweens: list[Tween] = []

    def add(self, tween: Tween) -> Tween:
        self.tweens.append(tween)
        return tween

    @property
    def is_complete(self) -> bool:
        return all(t.is_complete for t in self.tweens)

    def update(self, dt: float) -> bool:
        """Update all tweens. Returns True when all complete."""
        for tween in self.tweens:
            tween.update(dt)
        return self.is_complete

    def clear(self):
        self.tweens.clear()
