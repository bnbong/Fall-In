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
from app.models.db import UserStatus
from app.models.room import SeatControllerType
from app.repositories import user_repo
from app.services.match_service import MatchError, MatchService
from app.services.room_service import RoomError, RoomService
from app.ws.connection_manager import ConnectionManager
from app.ws.session import WsSession
from fall_in.net.serializers import private_state_to_dict, public_state_to_dict


async def handle_message(
    ws: WebSocket,
    session: WsSession,
    raw: dict,
    manager: ConnectionManager,
    room_service: RoomService,
    match_service: MatchService,
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
        await _room_start(ws, session, manager, room_service, match_service)
    elif msg_type == "CARD_SELECT":
        await _card_select(ws, session, data, manager, match_service)
    elif msg_type == "PING":
        await ws.send_json({"type": "PONG", "data": {}})
    else:
        await _error(ws, "UNKNOWN_MESSAGE", f"Unknown message type: {msg_type!r}")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _error(ws: WebSocket, code: str, message: str) -> None:
    await ws.send_json({"type": "ERROR", "data": {"code": code, "message": message}})


async def _broadcast_private_hands(
    match,
    manager: ConnectionManager,
    match_service: MatchService,
) -> None:
    """Unicast PRIVATE_HAND_STATE to every connected human seat."""
    for seat in match.seats.values():
        if seat.controller_type == SeatControllerType.REMOTE and seat.connection_id:
            private = match_service.build_private_state(match, seat.seat_index)
            await manager.send_to(seat.connection_id, {
                "type": "PRIVATE_HAND_STATE",
                "data": private_state_to_dict(private),
            })


async def _broadcast_selecting(
    room_code: str,
    match,
    manager: ConnectionManager,
    match_service: MatchService,
) -> None:
    """Broadcast PHASE_SELECTING + unicast PRIVATE_HAND_STATE to each human."""
    public = match_service.build_public_state(match)
    await manager.broadcast_to_room(room_code, {
        "type": "PHASE_SELECTING",
        "data": public_state_to_dict(public),
    })
    await _broadcast_private_hands(match, manager, match_service)


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

    if user.status != UserStatus.ACTIVE:
        await _error(ws, "ACCOUNT_NOT_ACTIVE", "Account is not active")
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
    match_service: MatchService,
) -> None:
    if not session.in_room:
        await _error(ws, "NOT_IN_ROOM", "You are not in a room")
        return

    try:
        room = room_service.start_room(session.room_code, session.seat_index)
    except RoomError as exc:
        await _error(ws, "ROOM_ERROR", str(exc))
        return

    # Broadcast final lobby state (phase=STARTING, all bots visible).
    await manager.broadcast_to_room(session.room_code, {
        "type": "ROOM_STATE",
        "data": room.to_dict(),
    })

    # Create the server-side match (deals cards, auto-selects bots).
    try:
        match = match_service.create_match(room)
    except MatchError as exc:
        await _error(ws, "MATCH_ERROR", str(exc))
        return

    session.match_id = match.match_id

    # Announce match to all room members.
    await manager.broadcast_to_room(session.room_code, {
        "type": "MATCH_START",
        "data": {"match_id": match.match_id},
    })

    # Send initial game state so clients can start rendering.
    await _broadcast_selecting(session.room_code, match, manager, match_service)


async def _card_select(
    ws: WebSocket,
    session: WsSession,
    data: dict,
    manager: ConnectionManager,
    match_service: MatchService,
) -> None:
    if not session.in_room:
        await _error(ws, "NOT_IN_MATCH", "You are not in an active match")
        return

    match = match_service.get_match_by_room(session.room_code)
    if match is None:
        await _error(ws, "MATCH_NOT_FOUND", "Match not found")
        return

    card_number = data.get("card_number")
    if card_number is None:
        await _error(ws, "MISSING_CARD", "card_number is required")
        return

    try:
        match_service.submit_selection(match, session.seat_index, int(card_number))
    except MatchError as exc:
        await _error(ws, "MATCH_ERROR", str(exc))
        return

    # Acknowledge selection to the submitting seat.
    private = match_service.build_private_state(match, session.seat_index)
    await manager.send_to(session.connection_id, {
        "type": "PRIVATE_HAND_STATE",
        "data": private_state_to_dict(private),
    })

    # If all seats have now selected, resolve the turn.
    if match_service.all_selected(match):
        await _execute_turn(session.room_code, match, manager, match_service)


async def _execute_turn(
    room_code: str,
    match,
    manager: ConnectionManager,
    match_service: MatchService,
) -> None:
    """
    Resolve a full turn: broadcast each placement step, then either start
    the next selection phase or broadcast round/match end results.
    """
    await manager.broadcast_to_room(room_code, {
        "type": "TURN_REVEAL_START",
        "data": {"match_id": match.match_id},
    })

    # Resolve placements one at a time; each snapshot reflects the board
    # state *after* that specific card was placed, not the final board.
    step_snapshots = match_service.resolve_turn_stepwise(match)

    for step, snapshot in step_snapshots:
        await manager.broadcast_to_room(room_code, {
            "type": "TURN_REVEAL_STEP",
            "data": {
                "seat_index": step.seat_index,
                "card_number": step.card_number,
                "card_danger": step.card_danger,
                "row_index": step.row_index,
                "penalty_score": step.penalty_score,
                "had_to_take_row": step.had_to_take_row,
                "placement_order": step.order,
            },
        })
        # Board state after this individual placement (incremental snapshot).
        await manager.broadcast_to_room(room_code, {
            "type": "PUBLIC_BOARD_STATE",
            "data": public_state_to_dict(snapshot),
        })

    await manager.broadcast_to_room(room_code, {
        "type": "TURN_RESOLVED",
        "data": {"match_id": match.match_id},
    })

    rules = match.rules  # fall_in.core.rules.GameRules
    if rules.is_round_over():
        summary = match_service.finalize_round(match)

        await manager.broadcast_to_room(room_code, {
            "type": "ROUND_RESULT",
            "data": {
                "round_number": summary.round_number,
                "round_danger": summary.round_danger,
                "total_scores": summary.total_scores,
                "eliminated_seats": summary.eliminated_seats,
                "game_over": summary.game_over,
                "winner_seat": summary.winner_seat,
            },
        })

        if summary.game_over:
            await manager.broadcast_to_room(room_code, {
                "type": "MATCH_RESULT",
                "data": {
                    "match_id": match.match_id,
                    "winner_seat": summary.winner_seat,
                    "final_scores": summary.total_scores,
                },
            })
            match_service.delete_match(match.match_id)
        else:
            match_service.start_next_round(match)
            await _broadcast_selecting(room_code, match, manager, match_service)
    else:
        # More turns to go in this round — re-select bots, then re-enter SELECTING.
        match_service.reselect_bots(match)
        await _broadcast_selecting(room_code, match, manager, match_service)
