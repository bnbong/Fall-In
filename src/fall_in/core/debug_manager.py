"""
Debug Manager - Debugging/cheat options for testing
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass


class DebugManager:
    """
    Debug/cheat options for testing.
    Provides cheat functions for quickly testing hard-to-reach game features.
    Accessed via F12 key in title scene (only when DEBUG_MODE=True).
    """

    @classmethod
    def is_debug_enabled(cls) -> bool:
        """Check if debug mode is enabled"""
        from fall_in.config import DEBUG_MODE

        return DEBUG_MODE

    @classmethod
    def unlock_all_soldiers(cls) -> None:
        """Mark all soldiers as collected."""
        import json

        from fall_in.config import DATA_DIR, TOTAL_CARDS

        path = DATA_DIR / "collected_soldiers.json"
        data = {"collected_ids": list(range(1, TOTAL_CARDS + 1))}

        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        print("[DEBUG] All soldiers unlocked!")

    @classmethod
    def clear_all_soldiers(cls) -> None:
        """Reset all soldier collection progress."""
        import json

        from fall_in.config import DATA_DIR

        path = DATA_DIR / "collected_soldiers.json"
        data = {"collected_ids": []}

        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        print("[DEBUG] All soldiers cleared!")

    @classmethod
    def set_coup_unlocked(cls, value: bool = True) -> None:
        """Set coup ending achievement state."""
        from fall_in.core.prestige_manager import PrestigeManager

        PrestigeManager().set_coup_unlocked(value)
        print(f"[DEBUG] Coup unlocked set to: {value}")

    @classmethod
    def add_currency(cls, amount: int = 10000) -> None:
        """Add currency to player wallet."""
        from fall_in.core.game_manager import GameManager

        GameManager().add_currency(amount)
        print(f"[DEBUG] Added {amount} currency. Total: {GameManager().currency}")

    @classmethod
    def set_currency(cls, amount: int) -> None:
        """Set currency to a specific amount."""
        import json

        from fall_in.config import DATA_DIR

        path = DATA_DIR / "player_data.json"
        if path.exists():
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)

            data["currency"] = amount

            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

        from fall_in.core.game_manager import GameManager

        GameManager().currency = amount
        print(f"[DEBUG] Currency set to: {amount}")

    @classmethod
    def set_prestige_count(cls, count: int) -> None:
        """Set prestige counter value."""
        from fall_in.core.prestige_manager import PrestigeManager

        PrestigeManager().set_prestige_count(count)
        print(f"[DEBUG] Prestige count set to: {count}")

    @classmethod
    def force_smuggle_soldiers(cls, soldier_ids: list[int]) -> None:
        """Force-set specific soldiers as smuggled."""
        from fall_in.core.smuggling_manager import SmugglingManager

        SmugglingManager().force_set_smuggled(soldier_ids)
        print(f"[DEBUG] Smuggled soldiers set to: {soldier_ids}")

    @classmethod
    def setup_coup_condition(cls) -> None:
        """Fully set up coup condition (collect all soldiers + smuggle coup soldiers)."""
        cls.unlock_all_soldiers()
        coup_soldiers = [11, 22, 33, 44, 55, 66, 77, 88, 99]
        cls.force_smuggle_soldiers(coup_soldiers)
        print("[DEBUG] Coup condition fully set up!")

    @classmethod
    def award_all_medals(cls) -> None:
        """Award all medals to the player."""
        from fall_in.core.medal_manager import MedalManager

        manager = MedalManager()
        for medal in manager.get_all_medals():
            manager.award_medal(medal["id"])
        print("[DEBUG] All medals awarded!")

    @classmethod
    def reset_medals(cls) -> None:
        """Reset all medals."""
        from fall_in.core.medal_manager import MedalManager

        MedalManager().reset(keep_special=False)
        print("[DEBUG] All medals reset!")

    @classmethod
    def trigger_game_over(cls) -> None:
        """Trigger immediate game over (from current game session)."""
        # This would need to be called from within a game scene
        print("[DEBUG] Game over triggered - use from GameScene")

    @classmethod
    def print_player_status(cls) -> None:
        """Print current player status to console."""
        import json

        from fall_in.config import DATA_DIR

        # Player data
        player_path = DATA_DIR / "player_data.json"
        if player_path.exists():
            with open(player_path, "r", encoding="utf-8") as f:
                player_data = json.load(f)
            print("\n[DEBUG] Player Data:")
            print(json.dumps(player_data, ensure_ascii=False, indent=2))

        # Collected soldiers
        collected_path = DATA_DIR / "collected_soldiers.json"
        if collected_path.exists():
            with open(collected_path, "r", encoding="utf-8") as f:
                collected_data = json.load(f)
            count = len(collected_data.get("collected_ids", []))
            print(f"\n[DEBUG] Collected Soldiers: {count}/104")

        # Smuggling status
        from fall_in.core.smuggling_manager import SmugglingManager

        smuggling = SmugglingManager()
        print(f"\n[DEBUG] Smuggled Soldiers: {smuggling.get_smuggled_soldiers()}")
        print(f"[DEBUG] Coup Condition Met: {smuggling.check_coup_condition()}")

    @classmethod
    def get_debug_options(cls) -> list[tuple[str, callable]]:
        """Get list of debug menu options."""
        return [
            ("모든 병사 수집", cls.unlock_all_soldiers),
            ("병사 수집 초기화", cls.clear_all_soldiers),
            ("쿠테타 해금", lambda: cls.set_coup_unlocked(True)),
            ("쿠테타 잠금", lambda: cls.set_coup_unlocked(False)),
            ("수당 +10000", lambda: cls.add_currency(10000)),
            ("수당 초기화", lambda: cls.set_currency(0)),
            (
                "프레스티지 +1",
                lambda: cls.set_prestige_count(cls._get_current_prestige() + 1),
            ),
            ("모든 훈장 획득", cls.award_all_medals),
            ("훈장 초기화", cls.reset_medals),
            ("쿠테타 조건 설정", cls.setup_coup_condition),
            ("상태 출력 (콘솔)", cls.print_player_status),
        ]

    @classmethod
    def _get_current_prestige(cls) -> int:
        """Get current prestige count"""
        from fall_in.core.prestige_manager import PrestigeManager

        return PrestigeManager().get_prestige_count()
