"""Per-connection session state, kept in the WS endpoint's call stack."""

from dataclasses import dataclass
from typing import Optional


@dataclass
class WsSession:
    connection_id: str
    user_id: Optional[str] = None
    display_name: Optional[str] = None
    account_type: Optional[str] = None   # "registered" | "guest"
    room_code: Optional[str] = None
    seat_index: Optional[int] = None

    @property
    def is_authenticated(self) -> bool:
        return self.display_name is not None

    match_id: Optional[str] = None

    @property
    def in_room(self) -> bool:
        return self.room_code is not None

    @property
    def in_match(self) -> bool:
        return self.match_id is not None
