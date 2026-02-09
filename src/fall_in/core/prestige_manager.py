"""
Prestige Manager - Prestige/rebirth system management
"""

import json
from typing import Optional

from fall_in.config import DATA_DIR


class PrestigeManager:
    """
    Prestige (rebirth) system manager.
    After achieving the coup ending, players can reset their data
    to receive permanent rewards and start over with bonuses.
    """

    _instance: Optional["PrestigeManager"] = None
    _PLAYER_DATA_FILE = "player_data.json"
    _COLLECTED_SOLDIERS_FILE = "collected_soldiers.json"

    # Prestige rewards
    PRESTIGE_BORDER_STYLES = [
        "prestige_bronze",
        "prestige_silver",
        "prestige_gold",
        "prestige_platinum",
        "prestige_diamond",
    ]

    def __new__(cls) -> "PrestigeManager":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        self._initialized = True
        self._prestige_count = 0
        self._coup_unlocked = False
        self._load_prestige_data()

    def _load_prestige_data(self) -> None:
        """Load prestige data from player_data.json"""
        try:
            path = DATA_DIR / self._PLAYER_DATA_FILE
            if path.exists():
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self._prestige_count = data.get("prestige_count", 0)
                    self._coup_unlocked = data.get("coup_unlocked", False)
        except Exception:
            self._prestige_count = 0
            self._coup_unlocked = False

    def _save_prestige_data(self) -> None:
        """Save prestige data"""
        try:
            path = DATA_DIR / self._PLAYER_DATA_FILE
            data = {}
            if path.exists():
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)

            data["prestige_count"] = self._prestige_count
            data["coup_unlocked"] = self._coup_unlocked

            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def can_prestige(self) -> bool:
        """
        Check if prestige is available.
        Requires coup ending to have been achieved at least once.
        """
        return self._coup_unlocked

    def unlock_coup(self) -> None:
        """Unlock prestige by achieving coup ending"""
        self._coup_unlocked = True
        self._save_prestige_data()

    def is_coup_unlocked(self) -> bool:
        """Check if coup has been unlocked"""
        return self._coup_unlocked

    def get_prestige_count(self) -> int:
        """Get current prestige count"""
        return self._prestige_count

    def get_prestige_rewards(self) -> dict:
        """
        Get rewards for current prestige level.
        Returns dict with:
        - extra_smuggle_slots: Number of additional smuggle slots
        - border_style: Unlocked border style name
        """
        rewards = {
            "extra_smuggle_slots": self._prestige_count,
            "border_style": None,
        }

        if self._prestige_count > 0:
            # Get border style based on prestige count
            idx = min(self._prestige_count - 1, len(self.PRESTIGE_BORDER_STYLES) - 1)
            rewards["border_style"] = self.PRESTIGE_BORDER_STYLES[idx]

        return rewards

    def execute_prestige(self) -> bool:
        """
        Execute prestige (rebirth).
        Resets most player data except:
        - prestige_count (incremented)
        - coup_master medal (preserved)

        Note: coup_unlocked is RESET to False - player must achieve coup again for next prestige.

        Returns True if successful.
        """
        if not self.can_prestige():
            return False

        try:
            # Increment prestige count
            self._prestige_count += 1

            # Reset coup_unlocked - player must achieve coup again for next prestige
            self._coup_unlocked = False

            # Reset player data
            path = DATA_DIR / self._PLAYER_DATA_FILE
            new_data = {
                "currency": 0,
                "prestige_count": self._prestige_count,
                "profile": {
                    "icon": "default",
                    "border": self.get_prestige_rewards().get("border_style", "basic"),
                },
                "medals": ["coup_master"],  # Preserve coup medal
                "coup_unlocked": False,  # Reset - must achieve coup again
                "max_smuggle_count": 1 + self._prestige_count,  # Base + prestige bonus
                "win_count": 0,
                "max_survived_rounds": 0,
            }

            with open(path, "w", encoding="utf-8") as f:
                json.dump(new_data, f, ensure_ascii=False, indent=2)

            # Reset collected soldiers
            collected_path = DATA_DIR / self._COLLECTED_SOLDIERS_FILE
            with open(collected_path, "w", encoding="utf-8") as f:
                json.dump({"collected_ids": []}, f, ensure_ascii=False, indent=2)

            return True
        except Exception:
            return False

    def set_prestige_count(self, count: int) -> None:
        """Set prestige count (for debugging)"""
        self._prestige_count = count
        self._save_prestige_data()

    def set_coup_unlocked(self, value: bool) -> None:
        """Set coup unlocked state (for debugging)"""
        self._coup_unlocked = value
        self._save_prestige_data()
