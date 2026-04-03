"""Per-connection session state, kept in the WS endpoint's call stack."""

from dataclasses import dataclass
from typing import Optional


@dataclass
class WsSession:
    connection_id: str
    user_id: Optional[str] = None
    display_name: Optional[str] = None
    account_type: Optional[str] = None  # "registered" | "guest"
    room_code: Optional[str] = None
    seat_index: Optional[int] = None
    match_id: Optional[str] = None

    # Heartbeat state (PR-05).
    # Set True when the server sends a PING; cleared when the client PONGs.
    # If still True when the next PING is due, the connection is considered dead.
    awaiting_pong: bool = False

    # Reconnect token issued at match start for this session's seat (PR-05).
    # Stored so the endpoint can look it up without querying the repo on
    # normal (non-reconnect) disconnects.
    reconnect_token: Optional[str] = None

    # True while this connection is sitting in the quick-match queue (PR-06).
    # Cleared when a match is formed or the player leaves the queue manually.
    in_queue: bool = False

    @property
    def is_authenticated(self) -> bool:
        return self.display_name is not None

    @property
    def in_room(self) -> bool:
        return self.room_code is not None

    @property
    def in_match(self) -> bool:
        return self.match_id is not None
