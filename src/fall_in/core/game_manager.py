"""
Game Manager - Core game state and scene management
"""

import json
from enum import Enum, auto
from pathlib import Path
from typing import Optional, TYPE_CHECKING

import pygame

from fall_in.config import SCREEN_WIDTH, SCREEN_HEIGHT, FPS, GAME_TITLE, SAND_BEIGE

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

    _instance: Optional["GameManager"] = None
    _DATA_FILE = "player_data.json"

    def __new__(cls) -> "GameManager":
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
        self.current_scene: Optional["Scene"] = None
        self.state = GameState.TITLE

        # Player data
        self.currency = 0  # In-game currency
        self.collected_soldiers: set[int] = set()  # Collected soldier IDs
        self.current_difficulty = "normal"

        # Audio settings
        self.bgm_volume = 0.5
        self.sfx_volume = 0.7

        # Load saved currency
        self.load_currency()

    def _get_data_path(self) -> Path:
        """Get path to player data file"""
        # Try to find data folder relative to config
        from fall_in.config import DATA_DIR

        return DATA_DIR / self._DATA_FILE

    def load_currency(self) -> None:
        """Load currency from saved data"""
        try:
            data_path = self._get_data_path()
            if data_path.exists():
                with open(data_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.currency = data.get("currency", 0)
        except Exception:
            self.currency = 0

    def save_currency(self) -> None:
        """Save currency to data file, preserving other fields"""
        try:
            data_path = self._get_data_path()
            data_path.parent.mkdir(parents=True, exist_ok=True)

            # Read existing data to preserve other fields
            existing_data = {}
            if data_path.exists():
                with open(data_path, "r", encoding="utf-8") as f:
                    existing_data = json.load(f)

            # Update only the currency field
            existing_data["currency"] = self.currency

            with open(data_path, "w", encoding="utf-8") as f:
                json.dump(existing_data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass  # Fail silently

    def add_currency(self, amount: int) -> None:
        """Add currency (수당) to player wallet"""
        self.currency += amount
        self.save_currency()

    def spend_currency(self, amount: int) -> bool:
        """
        Spend currency if sufficient funds available.
        Returns True if successful, False if insufficient funds.
        """
        if self.currency >= amount:
            self.currency -= amount
            self.save_currency()
            return True
        return False

    def has_currency(self, amount: int) -> bool:
        """Check if player has enough currency"""
        return self.currency >= amount

    def initialize(self) -> None:
        """Initialize pygame and create game window"""
        pygame.init()
        pygame.mixer.init()

        self.screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
        pygame.display.set_caption(GAME_TITLE)
        self.clock = pygame.time.Clock()
        self.running = True

        # Pre-load all assets registered in the manifest
        from fall_in.utils.asset_loader import AssetLoader

        loader = AssetLoader()
        loaded = loader.preload_all()
        print(
            f"[AssetLoader] Pre-loaded {loaded} assets ({loader.preloaded_count} cached)"
        )

        # Start with intro cutscene scene
        from fall_in.scenes.intro_cutscene_scene import IntroCutsceneScene

        self.change_scene(IntroCutsceneScene())

    def change_scene(self, new_scene: "Scene") -> None:
        """Change to a new scene"""
        if self.current_scene:
            self.current_scene.on_exit()

        self.current_scene = new_scene
        self.current_scene.on_enter()

    def run(self) -> None:
        """Main game loop"""
        while self.running:
            dt = self.clock.tick(FPS) / 1000.0  # type: ignore # Delta time in seconds

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
            self.screen.fill(SAND_BEIGE)  # type: ignore
            if self.current_scene:
                self.current_scene.render(self.screen)  # type: ignore

            pygame.display.flip()

        self.cleanup()

    def cleanup(self) -> None:
        """Clean up resources"""
        self.save_currency()  # Save before exit
        pygame.mixer.quit()
        pygame.quit()

    def quit(self) -> None:
        """Request game exit"""
        self.running = False
