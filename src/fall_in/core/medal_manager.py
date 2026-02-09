"""
Medal Manager - Achievement/medal system management
"""

import json
from typing import Optional

from fall_in.config import DATA_DIR


class MedalManager:
    """
    Medal (achievement) system manager.
    Tracks and awards medals earned through gameplay accomplishments.
    """

    _instance: Optional["MedalManager"] = None
    _MEDALS_FILE = "medals.json"
    _PLAYER_DATA_FILE = "player_data.json"

    def __new__(cls) -> "MedalManager":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        self._initialized = True
        self._medals_definitions: list[dict] = []
        self._player_medals: list[str] = []
        self._load_medals_definitions()
        self._load_player_medals()

    def _load_medals_definitions(self) -> None:
        """Load medal definitions from medals.json"""
        try:
            path = DATA_DIR / self._MEDALS_FILE
            if path.exists():
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self._medals_definitions = data.get("medals", [])
        except Exception:
            self._medals_definitions = []

    def _load_player_medals(self) -> None:
        """Load player's earned medals"""
        try:
            path = DATA_DIR / self._PLAYER_DATA_FILE
            if path.exists():
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self._player_medals = data.get("medals", [])
        except Exception:
            self._player_medals = []

    def _save_player_medals(self) -> None:
        """Save player's medals to player_data.json"""
        try:
            path = DATA_DIR / self._PLAYER_DATA_FILE
            data = {}
            if path.exists():
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)

            data["medals"] = self._player_medals

            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def get_all_medals(self) -> list[dict]:
        """Get all medal definitions"""
        return self._medals_definitions

    def get_player_medals(self) -> list[str]:
        """Get list of player's earned medal IDs"""
        return self._player_medals.copy()

    def has_medal(self, medal_id: str) -> bool:
        """Check if player has a specific medal"""
        return medal_id in self._player_medals

    def award_medal(self, medal_id: str) -> bool:
        """
        Award a medal to the player.
        Returns True if newly awarded, False if already owned.
        """
        if medal_id in self._player_medals:
            return False

        # Verify medal exists
        valid_ids = {m["id"] for m in self._medals_definitions}
        if medal_id not in valid_ids:
            return False

        self._player_medals.append(medal_id)
        self._save_player_medals()
        return True

    def check_medal_conditions(
        self,
        event_type: str,
        win_count: int = 0,
        survived_rounds: int = 0,
        final_danger: int = 0,
        is_victory: bool = False,
    ) -> list[str]:
        """
        Check and award medals based on game events.

        Args:
            event_type: "game_end", "interview_complete", "coup_ending"
            win_count: Total number of wins
            survived_rounds: Number of rounds survived this game
            final_danger: Player's final danger score
            is_victory: Whether player won

        Returns:
            List of newly awarded medal IDs
        """
        newly_awarded = []

        for medal in self._medals_definitions:
            if self.has_medal(medal["id"]):
                continue

            condition = medal.get("condition", {})
            cond_type = condition.get("type")
            cond_value = condition.get("value", 0)

            awarded = False

            if cond_type == "win_count" and is_victory:
                if win_count >= cond_value:
                    awarded = True

            elif cond_type == "collect_all" and event_type == "collect_all":
                awarded = True

            elif cond_type == "coup_ending" and event_type == "coup_ending":
                awarded = True

            elif cond_type == "survive_rounds":
                if survived_rounds >= cond_value:
                    awarded = True

            elif cond_type == "win_with_low_danger" and is_victory:
                if final_danger <= cond_value:
                    awarded = True

            if awarded:
                if self.award_medal(medal["id"]):
                    newly_awarded.append(medal["id"])

        return newly_awarded

    def has_all_soldiers_collected(self) -> bool:
        """Check if all soldiers have been collected (interviewed)"""
        try:
            collected_path = DATA_DIR / "collected_soldiers.json"
            if not collected_path.exists():
                return False

            with open(collected_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                collected_ids = set(data.get("collected_ids", []))

            # Total soldiers is 104 (cards 1-104)
            from fall_in.config import TOTAL_CARDS

            return len(collected_ids) >= TOTAL_CARDS
        except Exception:
            return False

    def get_medal_info(self, medal_id: str) -> Optional[dict]:
        """Get medal info by ID"""
        for medal in self._medals_definitions:
            if medal["id"] == medal_id:
                return medal
        return None

    def reset(self, keep_special: bool = True) -> None:
        """
        Reset player medals.

        Args:
            keep_special: If True, keep prestige-related medals (coup_master)
        """
        if keep_special:
            special_medals = {"coup_master"}
            self._player_medals = [
                m for m in self._player_medals if m in special_medals
            ]
        else:
            self._player_medals = []

        self._save_player_medals()
