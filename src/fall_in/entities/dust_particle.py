"""
DustParticle - Simple particle effect for soldier landing
"""

import random

import pygame


class DustParticle:
    """Single dust particle with position, velocity, and lifetime"""

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
        angle = random.uniform(-1.0, 1.0)  # Spread angle
        speed = random.uniform(30, 80)
        self.vx = angle * speed
        self.vy = random.uniform(-40, -80)  # Upward

        # Gravity
        self.gravity = 150

        # Lifetime
        self.lifetime = random.uniform(0.3, 0.6)
        self.age = 0.0

        # Size
        self.size = random.uniform(2, 5)

        # Color
        self.color = random.choice(self.COLORS)

    @property
    def is_alive(self) -> bool:
        return self.age < self.lifetime

    @property
    def alpha(self) -> int:
        """Fade out over lifetime"""
        progress = self.age / self.lifetime
        return int(255 * (1 - progress))

    def update(self, dt: float) -> None:
        """Update particle position and age"""
        self.age += dt

        # Apply velocity
        self.x += self.vx * dt
        self.y += self.vy * dt

        # Apply gravity
        self.vy += self.gravity * dt

        # Shrink over time
        shrink_rate = self.size / self.lifetime
        self.size = max(0, self.size - shrink_rate * dt)

    def render(self, screen: pygame.Surface) -> None:
        """Render particle"""
        if not self.is_alive or self.size < 1:
            return

        # Create small circle with alpha
        alpha = self.alpha
        color_with_alpha = (*self.color, alpha)

        # Draw circle
        size = int(self.size)
        if size >= 1:
            surf = pygame.Surface((size * 2, size * 2), pygame.SRCALPHA)
            pygame.draw.circle(surf, color_with_alpha, (size, size), size)
            screen.blit(surf, (int(self.x) - size, int(self.y) - size))


class DustEffect:
    """Manager for multiple dust particles"""

    def __init__(self):
        self.particles: list[DustParticle] = []

    def spawn(self, x: float, y: float, count: int) -> None:
        """Spawn multiple dust particles at position"""
        for _ in range(count):
            # Add slight randomness to spawn position
            px = x + random.uniform(-10, 10)
            py = y + random.uniform(-5, 5)
            self.particles.append(DustParticle(px, py))

    def update(self, dt: float) -> None:
        """Update all particles and remove dead ones"""
        for particle in self.particles:
            particle.update(dt)

        # Remove dead particles
        self.particles = [p for p in self.particles if p.is_alive]

    def render(self, screen: pygame.Surface, offset: tuple[int, int] = (0, 0)) -> None:
        """Render all particles with optional offset (for screen shake)"""
        for particle in self.particles:
            # Apply offset
            original_x, original_y = particle.x, particle.y
            particle.x += offset[0]
            particle.y += offset[1]
            particle.render(screen)
            particle.x, particle.y = original_x, original_y

    @property
    def is_active(self) -> bool:
        """Check if any particles are still alive"""
        return len(self.particles) > 0
