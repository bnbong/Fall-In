"""
In-memory room repository.

Designed so the storage backend can be swapped for Redis later (PR-06).
The interface contract callers must depend on:
  - generate_room_code() -> str
  - create(room) -> Room
  - get(room_code) -> Optional[Room]
  - update(room) -> None
  - delete(room_code) -> None
  - find_by_connection(conn_id) -> Optional[tuple[str, int]]
"""

import random
import string
from typing import Optional

from app.models.room import Room


class InMemoryRoomRepo:
    def __init__(self) -> None:
        self._rooms: dict[str, Room] = {}

    # ------------------------------------------------------------------
    # Code generation
    # ------------------------------------------------------------------

    def generate_room_code(self) -> str:
        chars = string.ascii_uppercase + string.digits
        for _ in range(200):
            code = "".join(random.choices(chars, k=6))
            if code not in self._rooms:
                return code
        raise RuntimeError("Could not generate a unique room code")

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def create(self, room: Room) -> Room:
        self._rooms[room.room_code] = room
        return room

    def get(self, room_code: str) -> Optional[Room]:
        return self._rooms.get(room_code.upper())

    def update(self, room: Room) -> None:
        self._rooms[room.room_code] = room

    def delete(self, room_code: str) -> None:
        self._rooms.pop(room_code, None)

    # ------------------------------------------------------------------
    # Lookups
    # ------------------------------------------------------------------

    def find_by_connection(self, conn_id: str) -> Optional[tuple[str, int]]:
        """Return (room_code, seat_index) for a connection, or None."""
        for room_code, room in self._rooms.items():
            for seat_idx, participant in room.participants.items():
                if participant.connection_id == conn_id:
                    return room_code, seat_idx
        return None

    def clear(self) -> None:
        """Reset all state. Used in tests between test runs."""
        self._rooms.clear()
