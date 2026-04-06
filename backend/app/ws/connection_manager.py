"""
WebSocket connection manager.

Tracks the mapping from connection_id → WebSocket and room_code → members.
All operations are synchronous except the actual send, which must be awaited.

This is a single-process in-memory implementation suitable for dev and tests.
A Redis pub/sub backed version replaces this in PR-06 for multi-worker prod.
"""

from typing import TYPE_CHECKING, Optional

from fastapi import WebSocket

if TYPE_CHECKING:
    from app.ws.session import WsSession


class ConnectionManager:
    def __init__(self) -> None:
        self._connections: dict[str, WebSocket] = {}
        self._room_members: dict[str, set[str]] = {}  # room_code → set[conn_id]
        self._sessions: dict[str, "WsSession"] = {}  # conn_id → WsSession

    async def connect(self, ws: WebSocket, conn_id: str) -> None:
        await ws.accept()
        self._connections[conn_id] = ws

    def register_session(self, conn_id: str, session: "WsSession") -> None:
        """Register a WsSession so _start_quick_match() can update it by conn_id."""
        self._sessions[conn_id] = session

    def get_session(self, conn_id: str) -> Optional["WsSession"]:
        """Return the WsSession for a connection, or None if not found."""
        return self._sessions.get(conn_id)

    def disconnect(self, conn_id: str, room_code: Optional[str] = None) -> None:
        self._connections.pop(conn_id, None)
        self._sessions.pop(conn_id, None)
        if room_code:
            self._room_members.get(room_code, set()).discard(conn_id)
            if room_code in self._room_members and not self._room_members[room_code]:
                del self._room_members[room_code]

    def join_room(self, conn_id: str, room_code: str) -> None:
        if room_code not in self._room_members:
            self._room_members[room_code] = set()
        self._room_members[room_code].add(conn_id)

    def get_room_members(self, room_code: str) -> list[str]:
        """Return a snapshot of connection IDs currently in room_code."""
        return list(self._room_members.get(room_code, set()))

    def leave_room(self, conn_id: str, room_code: str) -> None:
        self._room_members.get(room_code, set()).discard(conn_id)

    async def send_to(self, conn_id: str, message: dict) -> None:
        ws = self._connections.get(conn_id)
        if ws:
            try:
                await ws.send_json(message)
            except Exception:
                pass

    async def broadcast_to_room(self, room_code: str, message: dict) -> None:
        for conn_id in list(self._room_members.get(room_code, set())):
            ws = self._connections.get(conn_id)
            if ws:
                try:
                    await ws.send_json(message)
                except Exception:
                    pass

    def reset(self) -> None:
        """Clear all state. Called between tests."""
        self._connections.clear()
        self._room_members.clear()
        self._sessions.clear()


manager = ConnectionManager()
