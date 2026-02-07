"""
Soldier Data Manager - Load soldier data and manage collected state
"""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from fall_in.core.card import Card, calculate_danger


@dataclass
class SoldierInfo:
    """Extended soldier information for recruitment scene"""

    id: int
    name: str
    rank: str
    unit: str
    note: str
    intro: str
    danger: int
    frozen_food_count: int = 2  # 면담 시 냉동식품 개수 (1-5)
    is_collected: bool = False

    def to_card(self) -> Card:
        """Convert to Card object for game use"""
        return Card(
            number=self.id,
            danger=self.danger,
            is_collected=self.is_collected,
            name=self.name,
            rank=self.rank,
            unit=self.unit,
            note=self.note,
        )


class SoldierDataManager:
    """Manages soldier data loading and collection state persistence"""

    # Save file location
    SAVE_FILE = "collected_soldiers.json"

    def __init__(self):
        self.soldiers: dict[int, SoldierInfo] = {}
        self.collected_ids: set[int] = set()
        self._load_soldier_data()
        self._load_collected_state()

    def _get_save_path(self) -> Path:
        """Get path to save file in data directory"""
        # Use project data directory
        data_dir = Path(__file__).parent.parent.parent.parent / "data"
        return data_dir / self.SAVE_FILE

    def _load_soldier_data(self) -> None:
        """Load soldier data from soldiers.json"""
        data_path = (
            Path(__file__).parent.parent.parent.parent / "data" / "soldiers.json"
        )

        try:
            with open(data_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            for soldier_data in data.get("soldiers", []):
                soldier = SoldierInfo(
                    id=soldier_data["id"],
                    name=soldier_data.get("name", f"병사 {soldier_data['id']}"),
                    rank=soldier_data.get("rank", "일병"),
                    unit=soldier_data.get("unit", "미정"),
                    note=soldier_data.get("note", ""),
                    intro=soldier_data.get("intro", "필승!"),
                    danger=soldier_data.get(
                        "danger", calculate_danger(soldier_data["id"])
                    ),
                    frozen_food_count=soldier_data.get("frozen_food_count", 2),
                )
                self.soldiers[soldier.id] = soldier
        except FileNotFoundError:
            pass  # No soldier data yet

    def _load_collected_state(self) -> None:
        """Load collected soldier IDs from save file"""
        save_path = self._get_save_path()

        try:
            with open(save_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                self.collected_ids = set(data.get("collected_ids", []))

            # Apply collected state to soldiers
            for soldier_id in self.collected_ids:
                if soldier_id in self.soldiers:
                    self.soldiers[soldier_id].is_collected = True
        except FileNotFoundError:
            pass  # No save file yet

    def save_collected_state(self) -> None:
        """Save collected soldier IDs to file"""
        save_path = self._get_save_path()

        data = {"collected_ids": sorted(list(self.collected_ids))}

        with open(save_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def get_soldier(self, soldier_id: int) -> Optional[SoldierInfo]:
        """Get soldier info by ID"""
        return self.soldiers.get(soldier_id)

    def collect_soldier(self, soldier_id: int) -> bool:
        """Mark soldier as collected and save state"""
        if soldier_id in self.soldiers:
            self.soldiers[soldier_id].is_collected = True
            self.collected_ids.add(soldier_id)
            self.save_collected_state()
            return True
        return False

    def is_collected(self, soldier_id: int) -> bool:
        """Check if soldier is collected"""
        return soldier_id in self.collected_ids

    def get_uncollected_soldier(self) -> Optional[SoldierInfo]:
        """Get a random uncollected soldier for interview"""
        import random

        uncollected = [s for s in self.soldiers.values() if not s.is_collected]
        if uncollected:
            return random.choice(uncollected)
        return None

    def get_all_soldiers(self) -> list[SoldierInfo]:
        """Get all soldiers sorted by ID"""
        return sorted(self.soldiers.values(), key=lambda s: s.id)

    def get_collected_count(self) -> int:
        """Get number of collected soldiers"""
        return len(self.collected_ids)

    def get_total_available(self) -> int:
        """Get total number of available soldiers in data"""
        return len(self.soldiers)


# Singleton instance
_manager: Optional[SoldierDataManager] = None


def get_soldier_manager() -> SoldierDataManager:
    """Get singleton soldier data manager"""
    global _manager
    if _manager is None:
        _manager = SoldierDataManager()
    return _manager
