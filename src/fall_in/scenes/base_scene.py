"""
Base Scene class - Abstract base for all game scenes
"""
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

import pygame

if TYPE_CHECKING:
    pass


class Scene(ABC):
    """
    Abstract base class for game scenes.
    All scenes (Title, Game, Result, etc.) inherit from this class.
    """
    
    def __init__(self):
        self.ui_elements: list = []
    
    def on_enter(self) -> None:
        """Called when entering this scene"""
        pass
    
    def on_exit(self) -> None:
        """Called when leaving this scene"""
        pass
    
    @abstractmethod
    def handle_event(self, event: pygame.event.Event) -> None:
        """Handle pygame events"""
        pass
    
    @abstractmethod
    def update(self, dt: float) -> None:
        """Update scene state"""
        pass
    
    @abstractmethod
    def render(self, screen: pygame.Surface) -> None:
        """Render scene to screen"""
        pass
