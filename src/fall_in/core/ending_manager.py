"""
Ending Manager - Determines which ending scenario applies based on game result
and smuggled soldier combination.

Branching order:
  1. Victory or Defeat
  2. Smuggled soldier ID combination check (priority-sorted)
  3. Returns matched EndingScenario (cutscene key + folder)
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class EndingScenario:
    """Definition of a single ending scenario."""

    id: str
    result_type: str  # "victory" | "defeat"
    required_soldiers: frozenset[int]  # empty = no specific requirement
    requires_all_collected: bool  # True = all 104 soldiers must be interviewed
    cutscene_key: str  # file prefix, e.g. "victory", "defeat", "coup"
    priority: int  # higher = checked first


# ---------------------------------------------------------------------------
# Scenario registry
# ---------------------------------------------------------------------------
# Add new scenarios here (higher priority = evaluated first).
# Default scenarios (priority=0, empty required_soldiers) always match last.
# ---------------------------------------------------------------------------

ENDING_SCENARIOS: list[EndingScenario] = [
    # Coup ending: lost + all 104 soldiers interviewed + all 9 coup soldiers smuggled
    EndingScenario(
        id="coup",
        result_type="defeat",
        required_soldiers=frozenset({11, 22, 33, 44, 55, 66, 77, 88, 99}),
        requires_all_collected=True,
        cutscene_key="coup",
        priority=100,
    ),
    # Default victory (no specific soldier requirement)
    EndingScenario(
        id="victory",
        result_type="victory",
        required_soldiers=frozenset(),
        requires_all_collected=False,
        cutscene_key="victory",
        priority=0,
    ),
    # Default defeat (no specific soldier requirement)
    EndingScenario(
        id="defeat",
        result_type="defeat",
        required_soldiers=frozenset(),
        requires_all_collected=False,
        cutscene_key="defeat",
        priority=0,
    ),
]


class EndingManager:
    """
    Determines the appropriate ending scenario for the current game session.

    Call determine_ending() once when the game is over to get the scenario
    that should be used for the game over cutscene.
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

        candidates = [s for s in ENDING_SCENARIOS if s.result_type == result_type]
        candidates.sort(key=lambda s: s.priority, reverse=True)

        for scenario in candidates:
            if scenario.requires_all_collected and not self._all_soldiers_collected():
                continue
            if not scenario.required_soldiers.issubset(smuggled_soldiers):
                continue
            return scenario

        # Fallback: return lowest-priority default for this result type
        return candidates[-1]

    @staticmethod
    def _all_soldiers_collected() -> bool:
        from fall_in.core.medal_manager import MedalManager

        return MedalManager().has_all_soldiers_collected()
