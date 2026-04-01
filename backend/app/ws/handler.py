"""
WebSocket message router.

Each handle_* function processes one client message type.  The main
handle_message dispatcher routes by "type" field.

Auth via WS replicates the HTTP Bearer logic but over the socket channel
so the client can authenticate without an extra REST call in the lobby.
"""

from fastapi import WebSocket
from jose import JWTError

from app.auth.jwt import decode_token
from app.repositories import user_repo
from app.services.room_service import RoomError, RoomService
from app.ws.connection_manager import ConnectionManager
from app.ws.session import WsSession


async def handle_message(
    ws: WebSocket,
    session: WsSession,
    raw: dict,
    manager: ConnectionManager,
    room_service: RoomService,
    db,
) -> None:
    msg_type = raw.get("type")
    data = raw.get("data") or {}

    if msg_type == "WS_HELLO":
        await _hello(ws, session)
    elif msg_type in ("AUTH_LOGIN", "AUTH_GUEST"):
        await _auth(ws, session, data, db)
    elif msg_type == "ROOM_CREATE":
        await _room_create(ws, session, manager, room_service)
    elif msg_type == "ROOM_JOIN":
        await _room_join(ws, session, data, manager, room_service)
    elif msg_type == "ROOM_LEAVE":
        await _room_leave(ws, session, manager, room_service)
    elif msg_type == "READY_SET":
        await _ready_set(ws, session, data, manager, room_service)
    elif msg_type == "ROOM_START":
        await _room_start(ws, session, manager, room_service)
    elif msg_type == "PING":
        await ws.send_json({"type": "PONG", "data": {}})
    else:
        await _error(ws, "UNKNOWN_MESSAGE", f"Unknown message type: {msg_type!r}")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _error(ws: WebSocket, code: str, message: str) -> None:
    await ws.send_json({"type": "ERROR", "data": {"code": code, "message": message}})


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------

async def _hello(ws: WebSocket, session: WsSession) -> None:
    await ws.send_json({
        "type": "WS_WELCOME",
        "data": {"connection_id": session.connection_id},
    })


async def _auth(ws: WebSocket, session: WsSession, data: dict, db) -> None:
    token = data.get("token")
    if not token:
        await _error(ws, "MISSING_TOKEN", "token is required")
        return

    try:
        payload = decode_token(token)
    except JWTError:
        await _error(ws, "INVALID_TOKEN", "Invalid or expired token")
        return

    if payload.get("type") != "access":
        await _error(ws, "INVALID_TOKEN", "Must use an access token")
        return

    user_id = payload.get("sub")
    if not user_id:
        await _error(ws, "INVALID_TOKEN", "Token has no subject")
        return

    user = user_repo.get_by_id(db, user_id)
    if user is None:
        await _error(ws, "USER_NOT_FOUND", "User not found")
        return

    session.user_id = user_id
    session.account_type = user.account_type.value
    session.display_name = user.profile.nickname

    await ws.send_json({
        "type": "AUTH_OK",
        "data": {
            "user_id": user_id,
            "display_name": session.display_name,
            "account_type": session.account_type,
        },
    })


async def _room_create(
    ws: WebSocket,
    session: WsSession,
    manager: ConnectionManager,
    room_service: RoomService,
) -> None:
    if not session.is_authenticated:
        await _error(ws, "NOT_AUTHENTICATED", "Authenticate before creating a room")
        return
    if session.in_room:
        await _error(ws, "ALREADY_IN_ROOM", "Leave your current room first")
        return

    room = room_service.create_room(
        display_name=session.display_name,
        connection_id=session.connection_id,
        user_id=session.user_id,
    )
    session.room_code = room.room_code
    session.seat_index = 0
    manager.join_room(session.connection_id, room.room_code)
    await manager.broadcast_to_room(room.room_code, {
        "type": "ROOM_STATE",
        "data": room.to_dict(),
    })


async def _room_join(
    ws: WebSocket,
    session: WsSession,
    data: dict,
    manager: ConnectionManager,
    room_service: RoomService,
) -> None:
    if not session.is_authenticated:
        await _error(ws, "NOT_AUTHENTICATED", "Authenticate before joining a room")
        return
    if session.in_room:
        await _error(ws, "ALREADY_IN_ROOM", "Leave your current room first")
        return

    room_code = (data.get("room_code") or "").strip().upper()
    if not room_code:
        await _error(ws, "MISSING_ROOM_CODE", "room_code is required")
        return

    try:
        room = room_service.join_room(
            room_code=room_code,
            display_name=session.display_name,
            connection_id=session.connection_id,
            user_id=session.user_id,
        )
    except RoomError as exc:
        await _error(ws, "ROOM_ERROR", str(exc))
        return

    session.room_code = room.room_code
    # Resolve the seat we were assigned
    for seat_idx, p in room.participants.items():
        if p.connection_id == session.connection_id:
            session.seat_index = seat_idx
            break

    manager.join_room(session.connection_id, room.room_code)
    await manager.broadcast_to_room(room.room_code, {
        "type": "ROOM_STATE",
        "data": room.to_dict(),
    })


async def _room_leave(
    ws: WebSocket,
    session: WsSession,
    manager: ConnectionManager,
    room_service: RoomService,
) -> None:
    if not session.in_room:
        await _error(ws, "NOT_IN_ROOM", "You are not in a room")
        return

    room_code = session.room_code
    seat_index = session.seat_index
    session.room_code = None
    session.seat_index = None

    manager.leave_room(session.connection_id, room_code)
    updated = room_service.leave_room(room_code, seat_index)
    if updated:
        await manager.broadcast_to_room(room_code, {
            "type": "ROOM_STATE",
            "data": updated.to_dict(),
        })


async def _ready_set(
    ws: WebSocket,
    session: WsSession,
    data: dict,
    manager: ConnectionManager,
    room_service: RoomService,
) -> None:
    if not session.in_room:
        await _error(ws, "NOT_IN_ROOM", "You are not in a room")
        return

    is_ready = bool(data.get("is_ready", False))
    try:
        room = room_service.set_ready(session.room_code, session.seat_index, is_ready)
    except RoomError as exc:
        await _error(ws, "ROOM_ERROR", str(exc))
        return

    await manager.broadcast_to_room(session.room_code, {
        "type": "ROOM_STATE",
        "data": room.to_dict(),
    })


async def _room_start(
    ws: WebSocket,
    session: WsSession,
    manager: ConnectionManager,
    room_service: RoomService,
) -> None:
    if not session.in_room:
        await _error(ws, "NOT_IN_ROOM", "You are not in a room")
        return

    try:
        room = room_service.start_room(session.room_code, session.seat_index)
    except RoomError as exc:
        await _error(ws, "ROOM_ERROR", str(exc))
        return

    await manager.broadcast_to_room(session.room_code, {
        "type": "ROOM_STATE",
        "data": room.to_dict(),
    })
