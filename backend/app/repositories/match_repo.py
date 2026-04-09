"""
In-memory repository for active matches.

Keyed by match_id; secondary index by room_code for O(1) lookup.
Replace with a Redis-backed implementation in PR-06 for multi-worker deployments.
"""

from typing import Optional

from app.models.match import ActiveMatch


class InMemoryMatchRepo:
    def __init__(self) -> None:
        self._matches: dict[str, ActiveMatch] = {}
        self._by_room: dict[str, str] = {}  # room_code -> match_id

    def create(self, match: ActiveMatch) -> None:
        self._matches[match.match_id] = match
        self._by_room[match.room_code] = match.match_id

    def get(self, match_id: str) -> Optional[ActiveMatch]:
        return self._matches.get(match_id)

    def get_by_room(self, room_code: str) -> Optional[ActiveMatch]:
        mid = self._by_room.get(room_code)
        return self._matches.get(mid) if mid else None

    def delete(self, match_id: str) -> None:
        match = self._matches.pop(match_id, None)
        if match:
            self._by_room.pop(match.room_code, None)

    def clear(self) -> None:
        self._matches.clear()
        self._by_room.clear()
