"""
DustParticle - Simple particle effect for soldier landing impact.
"""

import random

import pygame

from fall_in.config import (
    DUST_GRAVITY,
    DUST_SPEED_MIN,
    DUST_SPEED_MAX,
    DUST_UPWARD_MIN,
    DUST_UPWARD_MAX,
    DUST_LIFETIME_MIN,
    DUST_LIFETIME_MAX,
    DUST_SIZE_MIN,
    DUST_SIZE_MAX,
    DUST_SPAWN_SPREAD_X,
    DUST_SPAWN_SPREAD_Y,
)


class DustParticle:
    """Single dust particle with position, velocity, and lifetime."""

    # Sand/dust color palette
    COLORS = [
        (194, 178, 128),  # Sand
        (210, 190, 140),  # Light sand
        (180, 165, 115),  # Dark sand
        (200, 180, 130),  # Medium sand
    ]

    def __init__(self, x: float, y: float):
        self.x = x
        self.y = y

        # Random velocity (outward and upward)
        angle = random.uniform(-1.0, 1.0)
        speed = random.uniform(DUST_SPEED_MIN, DUST_SPEED_MAX)
        self.vx = angle * speed
        self.vy = random.uniform(DUST_UPWARD_MIN, DUST_UPWARD_MAX)

        self.gravity = DUST_GRAVITY
        self.lifetime = random.uniform(DUST_LIFETIME_MIN, DUST_LIFETIME_MAX)
        self.age = 0.0
        self.size = random.uniform(DUST_SIZE_MIN, DUST_SIZE_MAX)
        self.color = random.choice(self.COLORS)

    @property
    def is_alive(self) -> bool:
        return self.age < self.lifetime

    @property
    def alpha(self) -> int:
        """Fade out over lifetime."""
        progress = self.age / self.lifetime
        return int(255 * (1 - progress))

    def update(self, dt: float) -> None:
        """Update particle position and age."""
        self.age += dt
        self.x += self.vx * dt
        self.y += self.vy * dt
        self.vy += self.gravity * dt

        # Shrink over time
        shrink_rate = self.size / self.lifetime
        self.size = max(0, self.size - shrink_rate * dt)

    def render(self, screen: pygame.Surface) -> None:
        """Render particle as a small fading circle."""
        if not self.is_alive or self.size < 1:
            return

        alpha = self.alpha
        color_with_alpha = (*self.color, alpha)

        size = int(self.size)
        if size >= 1:
            surf = pygame.Surface((size * 2, size * 2), pygame.SRCALPHA)
            pygame.draw.circle(surf, color_with_alpha, (size, size), size)
            screen.blit(surf, (int(self.x) - size, int(self.y) - size))


class DustEffect:
    """Manager for multiple dust particles."""

    def __init__(self):
        self.particles: list[DustParticle] = []

    def spawn(self, x: float, y: float, count: int) -> None:
        """Spawn multiple dust particles at position."""
        for _ in range(count):
            px = x + random.uniform(-DUST_SPAWN_SPREAD_X, DUST_SPAWN_SPREAD_X)
            py = y + random.uniform(-DUST_SPAWN_SPREAD_Y, DUST_SPAWN_SPREAD_Y)
            self.particles.append(DustParticle(px, py))

    def update(self, dt: float) -> None:
        """Update all particles and remove dead ones."""
        for particle in self.particles:
            particle.update(dt)
        self.particles = [p for p in self.particles if p.is_alive]

    def render(self, screen: pygame.Surface, offset: tuple[int, int] = (0, 0)) -> None:
        """Render all particles with optional offset (for screen shake)."""
        for particle in self.particles:
            original_x, original_y = particle.x, particle.y
            particle.x += offset[0]
            particle.y += offset[1]
            particle.render(screen)
            particle.x, particle.y = original_x, original_y

    @property
    def is_active(self) -> bool:
        """Check if any particles are still alive."""
        return len(self.particles) > 0
