"""
Ending Manager - Determines which ending scenario applies based on game result
and smuggled soldier combination.

Branching order:
  1. Victory or Defeat
  2. Smuggled soldier ID combination check (priority-sorted)
  3. Returns matched EndingScenario (background image key + name)
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class EndingScenario:
    """Definition of a single ending scenario."""

    id: str
    result_type: str | None  # "victory" | "defeat" | None (None = both)
    required_soldiers: frozenset[int]  # empty = no specific requirement
    requires_all_collected: bool  # True = all 104 soldiers must be interviewed
    bg_suffix: str  # filename suffix: f"{result}_{bg_suffix}.png"
    display_name: str  # Korean label shown in gallery (e.g. "승리")
    priority: int  # higher = checked first


# ---------------------------------------------------------------------------
# Scenario registry
# ---------------------------------------------------------------------------
# Add new scenarios here (higher priority = evaluated first).
# Default scenarios (priority=0, empty required_soldiers) always match last.
#
# Background file layout (under GAMEOVER_IMAGES_DIR):
#   gameover/
#     victory/
#       victory_bg.png          <- default victory
#       victory_1.png           <- combination 1 victory
#     defeat/
#       defeat_bg.png           <- default defeat
#       defeat_coup.png         <- coup ending
#       defeat_1.png            <- combination 1 defeat
#
# result_type=None means the combination applies to both victory and defeat;
# the loaded file is determined by actual game result at runtime.
# ---------------------------------------------------------------------------

ENDING_SCENARIOS: list[EndingScenario] = [
    # Coup ending: lost + all 104 soldiers interviewed + all 9 coup soldiers smuggled
    EndingScenario(
        id="coup",
        result_type="defeat",
        required_soldiers=frozenset({11, 22, 33, 44, 55, 66, 77, 88, 99}),
        requires_all_collected=True,
        bg_suffix="coup",
        display_name="쿠테타",
        priority=100,
    ),
    # Default victory (no specific soldier requirement)
    EndingScenario(
        id="victory",
        result_type="victory",
        required_soldiers=frozenset(),
        requires_all_collected=False,
        bg_suffix="bg",
        display_name="승리",
        priority=0,
    ),
    # Default defeat (no specific soldier requirement)
    EndingScenario(
        id="defeat",
        result_type="defeat",
        required_soldiers=frozenset(),
        requires_all_collected=False,
        bg_suffix="bg",
        display_name="패배",
        priority=0,
    ),
]


class EndingManager:
    """
    Determines the appropriate ending scenario for the current game session.

    Call determine_ending() once when the game is over to get the scenario
    whose background image should be displayed in GameOverScene.
    """

    def determine_ending(
        self,
        is_victory: bool,
        smuggled_soldiers: set[int],
    ) -> EndingScenario:
        """
        Return the highest-priority EndingScenario that matches the game state.

        Args:
            is_victory: True if the human player won.
            smuggled_soldiers: Set of soldier IDs smuggled during this session.

        Returns:
            The matched EndingScenario. Always returns at least the default
            victory or defeat scenario.
        """
        result_type = "victory" if is_victory else "defeat"

        # Include scenarios that match result_type OR apply to both (result_type=None)
        candidates = [
            s
            for s in ENDING_SCENARIOS
            if s.result_type is None or s.result_type == result_type
        ]
        candidates.sort(key=lambda s: s.priority, reverse=True)

        for scenario in candidates:
            if scenario.requires_all_collected and not self._all_soldiers_collected():
                continue
            if not scenario.required_soldiers.issubset(smuggled_soldiers):
                continue
            return scenario

        # Fallback: return the default scenario for this result type (priority=0)
        default = next(
            s
            for s in candidates
            if not s.required_soldiers and s.result_type == result_type
        )
        return default

    @staticmethod
    def get_all_scenarios() -> list[EndingScenario]:
        """Return all registered scenarios (for gallery display)."""
        return list(ENDING_SCENARIOS)

    @staticmethod
    def get_scenario_by_id(scenario_id: str) -> EndingScenario | None:
        """Find a scenario by its ID."""
        return next((s for s in ENDING_SCENARIOS if s.id == scenario_id), None)

    @staticmethod
    def get_scenario_by_bg_stem(stem: str) -> EndingScenario | None:
        """Find a scenario by its bg stem (e.g. 'victory_bg', 'defeat_coup').

        For result_type=None scenarios, matches either 'victory_{suffix}' or
        'defeat_{suffix}'.
        """
        for s in ENDING_SCENARIOS:
            if s.result_type is None:
                # stem starts with "victory_" or "defeat_" then bg_suffix
                if stem in (f"victory_{s.bg_suffix}", f"defeat_{s.bg_suffix}"):
                    return s
            else:
                if f"{s.result_type}_{s.bg_suffix}" == stem:
                    return s
        return None

    @staticmethod
    def _all_soldiers_collected() -> bool:
        from fall_in.core.medal_manager import MedalManager

        return MedalManager().has_all_soldiers_collected()
