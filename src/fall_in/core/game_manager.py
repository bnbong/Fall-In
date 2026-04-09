"""
Game Manager - Core game state and scene management
"""

import json
import threading
from enum import Enum, auto
from pathlib import Path
from typing import Optional, TYPE_CHECKING

import pygame

from fall_in.config import (
    SCREEN_WIDTH,
    SCREEN_HEIGHT,
    FPS,
    GAME_TITLE,
    SAND_BEIGE,
    IMAGES_DIR,
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
        self.user_id: Optional[str] = None
        self.nickname: str = ""
        self.account_type: Optional[str] = None
        self.access_token: Optional[str] = None
        self.refresh_token: Optional[str] = None
        self.pending_match_reconnect: Optional[dict] = None

        # Audio settings
        self.bgm_volume = 0.5
        self.sfx_volume = 0.7

        # Load saved local progress
        self.load_local_progress()

    def _get_data_path(self) -> Path:
        """Get path to player data file"""
        # Try to find data folder relative to config
        from fall_in.config import DATA_DIR

        return DATA_DIR / self._DATA_FILE

    def load_local_progress(self) -> None:
        """Load locally saved wallet and collection data."""
        try:
            self.currency = self.load_player_data().get("currency", 0)
        except Exception:
            self.currency = 0
        try:
            pending = self.load_player_data().get("pending_match_reconnect")
            self.pending_match_reconnect = pending if isinstance(pending, dict) else None
        except Exception:
            self.pending_match_reconnect = None
        try:
            from fall_in.data.soldier_data import get_soldier_manager

            self.collected_soldiers = set(get_soldier_manager().collected_ids)
        except Exception:
            self.collected_soldiers = set()

    def load_currency(self) -> None:
        """Backward-compatible alias used by older scenes."""
        self.load_local_progress()

    def load_player_data(self) -> dict:
        """Load full player data from saved JSON file."""
        try:
            data_path = self._get_data_path()
            if data_path.exists():
                with open(data_path, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception:
            pass
        return {}

    def save_currency(self) -> None:
        """Save currency to data file, preserving other fields"""
        try:
            existing_data = self.load_player_data()
            existing_data["currency"] = self.currency
            self._write_player_data(existing_data)
        except Exception:
            pass  # Fail silently

    def _write_player_data(self, data: dict) -> None:
        """Persist the shared player-data JSON file."""
        data_path = self._get_data_path()
        data_path.parent.mkdir(parents=True, exist_ok=True)
        with open(data_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def add_currency(self, amount: int) -> None:
        """Add currency (수당) to player wallet"""
        self.currency += amount
        self.save_currency()
        self._sync_currency_async()

    def spend_currency(self, amount: int) -> bool:
        """
        Spend currency if sufficient funds available.
        Returns True if successful, False if insufficient funds.
        """
        if self.currency >= amount:
            self.currency -= amount
            self.save_currency()
            self._sync_currency_async()
            return True
        return False

    def has_currency(self, amount: int) -> bool:
        """Check if player has enough currency"""
        return self.currency >= amount

    def has_auth_session(self) -> bool:
        return bool(self.access_token and self.account_type)

    def has_registered_session(self) -> bool:
        return self.has_auth_session() and self.account_type == "registered"

    def apply_auth_session(
        self,
        *,
        access_token: str,
        account_type: str,
        refresh_token: str | None = None,
    ) -> None:
        self.access_token = access_token
        self.account_type = account_type
        self.refresh_token = refresh_token

    def clear_auth_session(self) -> None:
        self.user_id = None
        self.nickname = ""
        self.account_type = None
        self.access_token = None
        self.refresh_token = None

    def store_pending_match_reconnect(
        self,
        *,
        token: str,
        match_id: str,
        room_code: str,
        seat_index: int,
    ) -> None:
        """Persist the current match reconnect token for later app relaunch."""
        if not token:
            return

        payload = {
            "token": token,
            "match_id": match_id,
            "room_code": room_code,
            "seat_index": int(seat_index),
        }
        if self.user_id:
            payload["user_id"] = self.user_id

        self.pending_match_reconnect = payload
        try:
            data = self.load_player_data()
            data["pending_match_reconnect"] = payload
            self._write_player_data(data)
        except Exception:
            pass

    def get_pending_match_reconnect(self) -> Optional[dict]:
        """Return the locally persisted match reconnect payload, if any."""
        pending = self.pending_match_reconnect
        return dict(pending) if isinstance(pending, dict) else None

    def clear_pending_match_reconnect(self) -> None:
        """Forget any saved reconnect token for a finished/invalid match."""
        self.pending_match_reconnect = None
        try:
            data = self.load_player_data()
            data.pop("pending_match_reconnect", None)
            self._write_player_data(data)
        except Exception:
            pass

    def get_local_progress_snapshot(self) -> dict:
        from fall_in.data.soldier_data import get_soldier_manager

        manager = get_soldier_manager()
        self.collected_soldiers = set(manager.collected_ids)
        return {
            "currency": self.currency,
            "collected_soldier_ids": sorted(self.collected_soldiers),
        }

    def apply_synced_progress(
        self,
        *,
        currency: int,
        collected_soldier_ids: list[int],
    ) -> None:
        self.currency = currency
        self.save_currency()

        from fall_in.data.soldier_data import get_soldier_manager

        manager = get_soldier_manager()
        manager.replace_collected_state(set(collected_soldier_ids))
        self.collected_soldiers = set(collected_soldier_ids)

    def bootstrap_authenticated_account(self, sync_local_progress: bool) -> dict:
        """
        Populate account identity and optionally merge local progress into the
        authenticated registered account.
        """
        if not self.has_auth_session() or self.access_token is None:
            return {}

        from fall_in.net.backend_api import get_json, post_json

        if self.has_registered_session() and sync_local_progress:
            merged = post_json(
                "/me/progress/merge",
                self.get_local_progress_snapshot(),
                token=self.access_token,
            )
            self.apply_synced_progress(
                currency=merged.get("currency", self.currency),
                collected_soldier_ids=merged.get("collected_soldier_ids", []),
            )
        elif self.has_registered_session():
            profile = get_json("/me/profile", self.access_token)
            collection = get_json("/me/collection", self.access_token)
            self.apply_synced_progress(
                currency=profile.get("currency", self.currency),
                collected_soldier_ids=[
                    item.get("soldier_id")
                    for item in collection.get("items", [])
                    if "soldier_id" in item
                ],
            )

        profile = get_json("/me/profile", self.access_token)
        self.user_id = profile.get("user_id")
        self.nickname = profile.get("nickname", self.nickname)
        self.account_type = profile.get("account_type", self.account_type)
        return profile

    def sync_registered_unlock_async(self, soldier_id: int) -> None:
        if not self.has_registered_session() or self.access_token is None:
            return

        def _worker() -> None:
            try:
                from fall_in.net.backend_api import post_json

                post_json(
                    "/me/collection/unlock",
                    {"soldier_id": soldier_id},
                    token=self.access_token,
                )
            except Exception:
                pass

        threading.Thread(target=_worker, daemon=True).start()

    def _sync_currency_async(self) -> None:
        if not self.has_registered_session() or self.access_token is None:
            return

        currency = self.currency

        def _worker() -> None:
            try:
                from fall_in.net.backend_api import put_json

                put_json(
                    "/me/currency",
                    {"currency": currency},
                    token=self.access_token,
                )
            except Exception:
                pass

        threading.Thread(target=_worker, daemon=True).start()

    def initialize(self) -> None:
        """Initialize pygame and create game window"""
        pygame.init()
        pygame.mixer.init()

        self.screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
        pygame.display.set_caption(GAME_TITLE)
        icon_path = IMAGES_DIR / "fall_in_icon.png"
        icon = pygame.image.load(str(icon_path))
        pygame.display.set_icon(icon)

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
