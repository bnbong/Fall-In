"""
Smuggling Manager - Soldier smuggling session management
"""

import json
from typing import Optional

from fall_in.config import DATA_DIR


class SmugglingManager:
    """
    Soldier smuggling session manager.
    Manages the system where players select penalty soldiers to smuggle
    after each round. The combination of smuggled soldiers determines
    whether the coup ending condition is met.

    Attributes:
        max_smuggle_count: Max soldiers selectable per smuggling screen.
        smuggled_ids: Cumulative set of smuggled soldiers across the game session.
    """

    # Soldier numbers required for the coup ending
    COUP_SOLDIERS = frozenset({11, 22, 33, 44, 55, 66, 77, 88, 99})

    _instance: Optional["SmugglingManager"] = None
    _PLAYER_DATA_FILE = "player_data.json"
    _COLLECTED_SOLDIERS_FILE = "collected_soldiers.json"

    def __new__(cls) -> "SmugglingManager":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        self._initialized = True
        # Cumulative smuggled soldiers across the entire game session
        self.smuggled_ids: set[int] = set()
        # Currently selected soldiers in the smuggling screen
        self.current_selection: set[int] = set()
        # Max soldiers selectable per smuggling screen
        self._max_count = 1
        self._load_max_count()

    def _load_max_count(self) -> None:
        """Load max smuggle count from player data"""
        try:
            path = DATA_DIR / self._PLAYER_DATA_FILE
            if path.exists():
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self._max_count = data.get("max_smuggle_count", 1)
        except Exception:
            self._max_count = 1

    def get_max_smuggle_count(self) -> int:
        """
        Get maximum number of soldiers that can be selected per smuggling screen.
        Base: 1
        + 1 if all soldiers collected
        + 1 per prestige level
        """
        return self._max_count

    def update_max_count(self) -> None:
        """Update max count based on current player state"""
        try:
            path = DATA_DIR / self._PLAYER_DATA_FILE
            if path.exists():
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)

                prestige_count = data.get("prestige_count", 0)
                base_count = 1

                # Check if all soldiers collected
                from fall_in.core.medal_manager import MedalManager

                if MedalManager().has_all_soldiers_collected():
                    base_count += 1

                # Add prestige bonus
                base_count += prestige_count

                self._max_count = base_count

                # Save updated max count
                data["max_smuggle_count"] = self._max_count
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def get_collected_ids(self) -> set[int]:
        """Return all collected soldier IDs (reads JSON once)."""
        try:
            path = DATA_DIR / self._COLLECTED_SOLDIERS_FILE
            if path.exists():
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    return set(data.get("collected_ids", []))
        except Exception:
            pass
        return set()

    def is_soldier_collected(self, soldier_id: int) -> bool:
        """Check if a soldier has been collected (interviewed)"""
        return soldier_id in self.get_collected_ids()

    def can_select(self, soldier_id: int) -> bool:
        """
        Check if a soldier can be selected in current smuggling screen.
        - Must be a collected (interviewed) soldier
        - Current selection must not exceed max count
        """
        if not self.is_soldier_collected(soldier_id):
            return False

        # Already selected - can always toggle off
        if soldier_id in self.current_selection:
            return True

        # Check if we can add more
        return len(self.current_selection) < self._max_count

    def select_soldier(self, soldier_id: int) -> bool:
        """
        Toggle selection of a soldier in current smuggling screen.
        Returns True if selection changed.
        """
        if soldier_id in self.current_selection:
            self.current_selection.discard(soldier_id)
            return True

        if self.can_select(soldier_id):
            self.current_selection.add(soldier_id)
            return True

        return False

    def is_selected(self, soldier_id: int) -> bool:
        """Check if soldier is currently selected"""
        return soldier_id in self.current_selection

    def get_current_selection(self) -> set[int]:
        """Get currently selected soldiers"""
        return self.current_selection.copy()

    def get_remaining_slots(self) -> int:
        """Get number of remaining selection slots for this screen"""
        return max(0, self._max_count - len(self.current_selection))

    def confirm_selection(self) -> None:
        """
        Confirm current selection - add to session's smuggled soldiers.
        Called when player confirms smuggling.
        """
        self.smuggled_ids.update(self.current_selection)
        self.current_selection.clear()

    def cancel_selection(self) -> None:
        """Cancel current selection without smuggling"""
        self.current_selection.clear()

    def start_new_selection(self) -> None:
        """Start a new smuggling selection (called at round end)"""
        self.current_selection.clear()

    def get_smuggled_soldiers(self) -> set[int]:
        """Get set of all smuggled soldier IDs in this game session"""
        return self.smuggled_ids.copy()

    def check_coup_condition(self) -> bool:
        """
        Check if coup ending condition is met.
        Requires: All COUP_SOLDIERS (11, 22, 33, 44, 55, 66, 77, 88, 99) smuggled.
        """
        return self.COUP_SOLDIERS.issubset(self.smuggled_ids)

    def reset_session(self) -> None:
        """Reset smuggling session for a new game"""
        self.smuggled_ids.clear()
        self.current_selection.clear()
        self.update_max_count()

    def force_set_smuggled(self, soldier_ids: list[int]) -> None:
        """Force set smuggled soldiers (for debugging)"""
        self.smuggled_ids = set(soldier_ids)
