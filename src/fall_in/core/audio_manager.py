"""
AudioManager - Singleton for BGM playback and volume management.

Persists volume settings to player_data.json.
"""

import json

import pygame

from fall_in.config import DATA_DIR, SOUNDS_DIR


class AudioManager:
    """Singleton managing BGM playback and volume settings."""

    _instance = None

    def __new__(cls) -> "AudioManager":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self) -> None:
        if self._initialized:
            return
        self._initialized = True

        self._current_bgm: str | None = None
        self._bgm_volume: float = 0.7
        self._sfx_volume: float = 0.7
        self._sfx_cache: dict[str, pygame.mixer.Sound] = {}

        self._load_settings()
        pygame.mixer.music.set_volume(self._bgm_volume)

    # ------------------------------------------------------------------
    # BGM
    # ------------------------------------------------------------------

    def play_bgm(self, path: str) -> None:
        """Play a BGM file. If already playing the same file, do nothing."""
        full_path = str(SOUNDS_DIR / path)
        if self._current_bgm == full_path:
            return
        try:
            pygame.mixer.music.load(full_path)
            pygame.mixer.music.set_volume(self._bgm_volume)
            pygame.mixer.music.play(-1)  # loop forever
            self._current_bgm = full_path
        except Exception as e:
            print(f"[AudioManager] Failed to play BGM: {e}")

    def stop_bgm(self) -> None:
        """Stop BGM playback."""
        pygame.mixer.music.stop()
        self._current_bgm = None

    # ------------------------------------------------------------------
    # SFX
    # ------------------------------------------------------------------

    def play_sfx(self, path: str) -> None:
        """Play a sound effect. Cached after first load."""
        if self._sfx_volume <= 0:
            return
        try:
            if path not in self._sfx_cache:
                full_path = str(SOUNDS_DIR / path)
                self._sfx_cache[path] = pygame.mixer.Sound(full_path)
            sound = self._sfx_cache[path]
            sound.set_volume(self._sfx_volume)
            sound.play()
        except Exception as e:
            print(f"[AudioManager] Failed to play SFX '{path}': {e}")

    # ------------------------------------------------------------------
    # Volume
    # ------------------------------------------------------------------

    @property
    def bgm_volume(self) -> float:
        return self._bgm_volume

    @bgm_volume.setter
    def bgm_volume(self, vol: float) -> None:
        self._bgm_volume = max(0.0, min(1.0, vol))
        pygame.mixer.music.set_volume(self._bgm_volume)

    @property
    def sfx_volume(self) -> float:
        return self._sfx_volume

    @sfx_volume.setter
    def sfx_volume(self, vol: float) -> None:
        self._sfx_volume = max(0.0, min(1.0, vol))

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _load_settings(self) -> None:
        """Load volume settings from player_data.json."""
        path = DATA_DIR / "player_data.json"
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self._bgm_volume = float(data.get("bgm_volume", 0.7))
            self._sfx_volume = float(data.get("sfx_volume", 0.7))
        except (FileNotFoundError, json.JSONDecodeError, KeyError, ValueError):
            pass

    def save_settings(self) -> None:
        """Save volume settings to player_data.json."""
        path = DATA_DIR / "player_data.json"
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            data = {}

        data["bgm_volume"] = round(self._bgm_volume, 2)
        data["sfx_volume"] = round(self._sfx_volume, 2)

        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
