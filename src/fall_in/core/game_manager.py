"""
Game Manager - Core game state and scene management
"""
from enum import Enum, auto
from typing import Optional, TYPE_CHECKING

import pygame

from fall_in.config import (
    SCREEN_WIDTH, SCREEN_HEIGHT, FPS, GAME_TITLE,
    SAND_BEIGE
)

if TYPE_CHECKING:
    from fall_in.scenes.base_scene import Scene


class GameState(Enum):
    """Game state enumeration"""
    TITLE = auto()
    TUTORIAL = auto()
    SETTINGS = auto()
    COLLECTION = auto()
    PLAYING = auto()
    RESULT = auto()
    GAMEOVER = auto()


class GameManager:
    """
    Manages overall game state, scene transitions, and main game loop.
    Implements singleton pattern for global access.
    """
    _instance: Optional['GameManager'] = None
    
    def __new__(cls) -> 'GameManager':
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        self._initialized = True
        self.running = False
        self.screen: Optional[pygame.Surface] = None
        self.clock: Optional[pygame.time.Clock] = None
        self.current_scene: Optional['Scene'] = None
        self.state = GameState.TITLE
        
        # Player data
        self.currency = 0  # 수당 (게임 재화)
        self.collected_soldiers: set[int] = set()  # 수집한 병사 ID
        self.current_difficulty = "normal"
        
        # Audio settings
        self.bgm_volume = 0.5
        self.sfx_volume = 0.7
    
    def add_currency(self, amount: int) -> None:
        """Add currency (수당) to player wallet"""
        self.currency += amount
    
    def initialize(self) -> None:
        """Initialize pygame and create game window"""
        pygame.init()
        pygame.mixer.init()
        
        self.screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
        pygame.display.set_caption(GAME_TITLE)
        self.clock = pygame.time.Clock()
        self.running = True
        
        # Start with title scene
        from fall_in.scenes.title_scene import TitleScene
        self.change_scene(TitleScene())
    
    def change_scene(self, new_scene: 'Scene') -> None:
        """Change to a new scene"""
        if self.current_scene:
            self.current_scene.on_exit()
        
        self.current_scene = new_scene
        self.current_scene.on_enter()
    
    def run(self) -> None:
        """Main game loop"""
        while self.running:
            dt = self.clock.tick(FPS) / 1000.0  # Delta time in seconds
            
            # Event handling
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.running = False
                elif self.current_scene:
                    self.current_scene.handle_event(event)
            
            # Update
            if self.current_scene:
                self.current_scene.update(dt)
            
            # Render
            self.screen.fill(SAND_BEIGE)
            if self.current_scene:
                self.current_scene.render(self.screen)
            
            pygame.display.flip()
        
        self.cleanup()
    
    def cleanup(self) -> None:
        """Clean up resources"""
        pygame.mixer.quit()
        pygame.quit()
    
    def quit(self) -> None:
        """Request game exit"""
        self.running = False
