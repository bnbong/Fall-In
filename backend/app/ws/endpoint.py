"""
WebSocket entry point: GET /ws

Each connection gets a unique connection_id and a WsSession that tracks
identity and room/match membership for the duration of the connection.

The DB session, room_service, match_service, and presence_manager are
injected via FastAPI's dependency system so tests can override them with
fresh instances per test.

PR-05 changes
-------------
* A heartbeat asyncio.Task is spawned alongside the receive loop.
  It sends a server-initiated PING every HEARTBEAT_INTERVAL_SECONDS and
  closes the connection if no PONG arrives before the next PING.
* On WebSocketDisconnect the cleanup logic now distinguishes between
  in-lobby and in-match disconnects:
    - In-lobby: leave room as before.
    - In-match: mark the seat disconnected and start the grace timer;
      the room/match state is preserved for a possible reconnect.
"""

import asyncio
import uuid

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models.room import SeatControllerType
from app.repositories.match_repo import InMemoryMatchRepo
from app.repositories.room_repo import InMemoryRoomRepo
from app.services.match_service import MatchService
from app.services.room_service import RoomService
from app.ws.connection_manager import manager
from app.ws.handler import _execute_turn, handle_message
from app.ws.presence import PresenceManager, presence_manager as _default_presence_manager
from app.ws.session import WsSession

router = APIRouter()

# Module-level singletons. Tests override get_room_service / get_match_service
# / get_presence_manager via app.dependency_overrides.
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


def get_presence_manager() -> PresenceManager:
    """Dependency — returns the shared PresenceManager (overridable in tests)."""
    return _default_presence_manager


# ---------------------------------------------------------------------------
# Heartbeat
# ---------------------------------------------------------------------------

async def _heartbeat_loop(ws: WebSocket, session: WsSession) -> None:
    """
    Send server-initiated PINGs and close the connection if no PONG is received.

    Interval: HEARTBEAT_INTERVAL_SECONDS (default 15 s).
    If session.awaiting_pong is still True when the next PING is due, the
    previous PING went unanswered and the connection is considered dead.
    """
    try:
        while True:
            await asyncio.sleep(settings.HEARTBEAT_INTERVAL_SECONDS)
            if session.awaiting_pong:
                # Previous PONG never arrived — close with "going away" code.
                try:
                    await ws.close(1001)
                except Exception:
                    pass
                return
            session.awaiting_pong = True
            try:
                await ws.send_json({"type": "PING", "data": {}})
            except Exception:
                return
    except asyncio.CancelledError:
        pass


# ---------------------------------------------------------------------------
# WebSocket endpoint
# ---------------------------------------------------------------------------

@router.websocket("/ws")
async def websocket_endpoint(
    ws: WebSocket,
    db: Session = Depends(get_db),
    room_service: RoomService = Depends(get_room_service),
    match_service: MatchService = Depends(get_match_service),
    presence_manager: PresenceManager = Depends(get_presence_manager),
) -> None:
    conn_id = str(uuid.uuid4())
    await manager.connect(ws, conn_id)
    session = WsSession(connection_id=conn_id)

    heartbeat = asyncio.create_task(_heartbeat_loop(ws, session))

    try:
        while True:
            try:
                raw = await ws.receive_json()
            except Exception:
                break
            await handle_message(
                ws, session, raw, manager,
                room_service, match_service, presence_manager, db,
            )
    except WebSocketDisconnect:
        pass
    finally:
        heartbeat.cancel()

        if session.in_room:
            active_match = match_service.get_match_by_room(session.room_code)

            if (
                active_match is not None
                and session.seat_index is not None
            ):
                seat = active_match.seats.get(session.seat_index)
                if (
                    seat is not None
                    and seat.controller_type == SeatControllerType.REMOTE
                    and not seat.took_over_by_bot
                ):
                    # In-match disconnect: preserve state, start grace timer.
                    match_service.mark_seat_disconnected(active_match, session.seat_index)
                    await manager.broadcast_to_room(session.room_code, {
                        "type": "PLAYER_DISCONNECTED",
                        "data": {"seat_index": session.seat_index},
                    })

                    async def _on_turn_ready(rc: str, m) -> None:
                        await _execute_turn(rc, m, manager, match_service, presence_manager)

                    presence_manager.start_grace_timer(
                        match_id=active_match.match_id,
                        seat_index=session.seat_index,
                        match=active_match,
                        match_service=match_service,
                        room_service=room_service,
                        manager=manager,
                        room_code=session.room_code,
                        on_turn_ready=_on_turn_ready,
                    )
            else:
                # In-lobby disconnect: leave room normally.
                updated = room_service.leave_room(session.room_code, session.seat_index)
                if updated:
                    await manager.broadcast_to_room(session.room_code, {
                        "type": "ROOM_STATE",
                        "data": updated.to_dict(),
                    })

        manager.disconnect(conn_id, session.room_code)
