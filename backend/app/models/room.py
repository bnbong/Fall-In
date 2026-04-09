"""
In-memory room/lobby models.

These are not persisted to the database — rooms live only for the duration
of the lobby phase. Once a match starts (PR-04+), a match record is created.

Design rules:
  - RoomParticipant tracks seat_index (position at table), not user_id identity.
  - seat_index 0..3 maps to game seats; bots fill unoccupied seats on start.
  - connection_id is None for bot seats (they have no WS connection).
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class RoomPhase(str, Enum):
    WAITING = "waiting"  # accepting joins, host hasn't started
    STARTING = "starting"  # host pressed start, bots filled, match engine pending


class SeatControllerType(str, Enum):
    REMOTE = "remote"  # human connected via WebSocket
    BOT = "bot"  # AI-controlled seat


@dataclass
class RoomParticipant:
    seat_index: int
    display_name: str
    controller_type: SeatControllerType
    is_ready: bool = False
    account_type: str = "guest"  # "registered" | "guest" | "bot"
    user_id: Optional[str] = None  # None for guests and bots
    connection_id: Optional[str] = None  # None for bots


@dataclass
class Room:
    room_code: str
    host_seat_index: int
    phase: RoomPhase = RoomPhase.WAITING
    # Keyed by seat_index (0..3). Gaps are empty seats.
    participants: dict = field(default_factory=dict)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def next_available_seat(self) -> Optional[int]:
        for i in range(4):
            if i not in self.participants:
                return i
        return None

    def is_full(self) -> bool:
        return len(self.participants) >= 4

    def human_count(self) -> int:
        return sum(
            1 for p in self.participants.values() if p.controller_type == SeatControllerType.REMOTE
        )

    def to_dict(self) -> dict:
        """
        Return a JSON-serialisable representation for ROOM_STATE messages.

        user_id is deliberately excluded — it is a stable account identifier
        that other clients have no need for.  display_name is sufficient for
        the lobby UI.
        """
        return {
            "room_code": self.room_code,
            "phase": self.phase,
            "host_seat_index": self.host_seat_index,
            "participants": [
                {
                    "seat_index": p.seat_index,
                    "display_name": p.display_name,
                    "controller_type": p.controller_type,
                    "is_ready": p.is_ready,
                }
                for p in sorted(self.participants.values(), key=lambda x: x.seat_index)
            ],
        }
