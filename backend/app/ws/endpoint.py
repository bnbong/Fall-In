"""
WebSocket entry point: GET /ws

Each connection gets a unique connection_id and a WsSession that tracks
identity and room/match membership for the duration of the connection.

The DB session, room_service, and match_service are injected via FastAPI's
dependency system so tests can override them with fresh instances per test.
"""

import uuid

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session

from app.database import get_db
from app.repositories.match_repo import InMemoryMatchRepo
from app.repositories.room_repo import InMemoryRoomRepo
from app.services.match_service import MatchService
from app.services.room_service import RoomService
from app.ws.connection_manager import manager
from app.ws.handler import handle_message
from app.ws.session import WsSession

router = APIRouter()

# Module-level singletons. Tests override get_room_service / get_match_service.
_room_repo = InMemoryRoomRepo()
_room_service = RoomService(_room_repo)

_match_repo = InMemoryMatchRepo()
_match_service = MatchService(_match_repo)


def get_room_service() -> RoomService:
    """Dependency — returns the shared RoomService (overridable in tests)."""
    return _room_service


def get_match_service() -> MatchService:
    """Dependency — returns the shared MatchService (overridable in tests)."""
    return _match_service


@router.websocket("/ws")
async def websocket_endpoint(
    ws: WebSocket,
    db: Session = Depends(get_db),
    room_service: RoomService = Depends(get_room_service),
    match_service: MatchService = Depends(get_match_service),
) -> None:
    conn_id = str(uuid.uuid4())
    await manager.connect(ws, conn_id)
    session = WsSession(connection_id=conn_id)

    try:
        while True:
            try:
                raw = await ws.receive_json()
            except Exception:
                break
            await handle_message(ws, session, raw, manager, room_service, match_service, db)
    except WebSocketDisconnect:
        pass
    finally:
        if session.in_room:
            updated = room_service.leave_room(session.room_code, session.seat_index)
            if updated:
                await manager.broadcast_to_room(session.room_code, {
                    "type": "ROOM_STATE",
                    "data": updated.to_dict(),
                })
        manager.disconnect(conn_id, session.room_code)
