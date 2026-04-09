"""
WebSocket message router.

Each handle_* function processes one client message type.  The main
handle_message dispatcher routes by "type" field.

Auth via WS replicates the HTTP Bearer logic but over the socket channel
so the client can authenticate without an extra REST call in the lobby.

PR-05 additions
---------------
* PONG handler: clears session.awaiting_pong (set by the heartbeat loop
  in endpoint.py).
* RECONNECT handler: validates a reconnect token and restores a disconnected
  seat without re-authenticating from scratch.
* _room_start now issues per-seat RECONNECT_TOKEN messages after MATCH_START.
* _room_start and _execute_turn start the card-selection timeout after each
  new SELECTING phase via _start_selection_timeout().
* _execute_turn receives a PresenceManager argument so it can cancel/restart
  timeouts and revoke tokens when a match ends.

PR-06 additions
---------------
* QUICK_MATCH_JOIN / QUICK_MATCH_LEAVE handlers.
* _start_quick_match() shared entry point used by both the immediate 4-player
  case and the fill-timer callback.
* _execute_turn triggers MMR persistence for eligible ranked matches.
"""

import logging

from fall_in.net.serializers import private_state_to_dict, public_state_to_dict
from fastapi import WebSocket
from jose import JWTError

from app.auth.jwt import decode_token
from app.config import settings
from app.models.db import UserStatus
from app.models.room import SeatControllerType
from app.repositories import user_repo
from app.services.match_service import MatchError, MatchService
from app.services.matchmaking_service import MatchmakingService
from app.services.room_service import RoomError, RoomService
from app.ws.connection_manager import ConnectionManager
from app.ws.presence import PresenceManager
from app.ws.session import WsSession

logger = logging.getLogger("fall_in.ws.handler")


async def handle_message(
    ws: WebSocket,
    session: WsSession,
    raw: dict,
    manager: ConnectionManager,
    room_service: RoomService,
    match_service: MatchService,
    presence_manager: PresenceManager,
    matchmaking_service: MatchmakingService,
    db,
) -> None:
    msg_type = raw.get("type")
    data = raw.get("data", {})

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
        await _room_start(ws, session, manager, room_service, match_service, presence_manager)
    elif msg_type == "CARD_SELECT":
        await _card_select(ws, session, data, manager, match_service, presence_manager)
    elif msg_type == "ROUND_READY":
        await _round_ready(ws, session, manager, match_service, room_service, presence_manager)
    elif msg_type == "RECONNECT":
        await _reconnect(
            ws, session, data, manager, room_service, match_service, presence_manager, db
        )
    elif msg_type == "QUICK_MATCH_JOIN":
        await _quick_match_join(
            ws,
            session,
            manager,
            room_service,
            match_service,
            presence_manager,
            matchmaking_service,
            db,
        )
    elif msg_type == "QUICK_MATCH_LEAVE":
        await _quick_match_leave(ws, session, matchmaking_service)
    elif msg_type == "MATCH_LEAVE":
        await _match_leave(ws, session, manager, room_service, match_service, presence_manager)
    elif msg_type == "EMOTE_SEND":
        await _emote_send(ws, session, data, manager)
    elif msg_type == "EMOTE_MUTE":
        await _emote_mute(ws, session, data)
    elif msg_type == "PING":
        await ws.send_json({"type": "PONG", "data": {}})
    elif msg_type == "PONG":
        # Client responding to a server-initiated PING; clear the awaiting flag.
        session.awaiting_pong = False
    else:
        logger.warning(
            "ws_unknown_message",
            extra={"conn_id": session.connection_id, "msg_type": msg_type},
        )
        await _error(ws, "UNKNOWN_MESSAGE", f"Unknown message type: {msg_type!r}", session=session)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _error(
    ws: WebSocket,
    code: str,
    message: str,
    *,
    session: WsSession | None = None,
    level: str = "warning",
) -> None:
    """
    Send an ERROR frame to the client and emit a structured log entry.

    ``level`` controls the log severity: "warning" for expected client errors
    (bad input, wrong state), "error" for unexpected server-side failures.
    """
    log_fn = logger.error if level == "error" else logger.warning
    log_fn(
        "ws_error",
        extra={
            "code": code,
            "detail": message,
            "conn_id": session.connection_id if session else None,
            "user_id": session.user_id if session else None,
        },
    )
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
            await manager.send_to(
                seat.connection_id,
                {
                    "type": "PRIVATE_HAND_STATE",
                    "data": private_state_to_dict(private),
                },
            )


async def _broadcast_selecting(
    room_code: str,
    match,
    manager: ConnectionManager,
    match_service: MatchService,
) -> None:
    """Broadcast PHASE_SELECTING + unicast PRIVATE_HAND_STATE to each human."""
    public = match_service.build_public_state(match)
    data = public_state_to_dict(public)
    data["remaining_time"] = settings.CARD_SELECTION_TIMEOUT_SECONDS
    await manager.broadcast_to_room(
        room_code,
        {
            "type": "PHASE_SELECTING",
            "data": data,
        },
    )
    await _broadcast_private_hands(match, manager, match_service)


async def _issue_reconnect_tokens(
    room_code: str,
    match,
    manager: ConnectionManager,
    presence_manager: PresenceManager,
) -> None:
    """
    Issue reconnect tokens for the current round to connected registered seats.

    Guests are intentionally excluded from reconnect support.
    """
    for seat in match.seats.values():
        if seat.controller_type != SeatControllerType.REMOTE or not seat.connection_id:
            continue
        if seat.account_type != "registered" or not seat.user_id:
            continue

        token = presence_manager.issue_token(
            match_id=match.match_id,
            room_code=room_code,
            seat_index=seat.seat_index,
            user_id=seat.user_id,
            display_name=seat.display_name,
            account_type=seat.account_type,
        )
        ws_session = manager.get_session(seat.connection_id)
        if ws_session is not None:
            ws_session.reconnect_token = token
        await manager.send_to(
            seat.connection_id,
            {
                "type": "RECONNECT_TOKEN",
                "data": {
                    "token": token,
                    "seat_index": seat.seat_index,
                    "room_code": room_code,
                    "match_id": match.match_id,
                },
            },
        )


async def _take_over_disconnected_seats_for_new_round(
    room_code: str,
    match,
    manager: ConnectionManager,
    match_service: MatchService,
    room_service: RoomService,
    presence_manager: PresenceManager,
) -> None:
    """
    Finalise any still-disconnected human seats before the next round starts.

    This enforces the "same round only" reconnect rule: once a fresh round
    begins, a player who did not return in time permanently loses the seat.
    """
    for seat in list(match.seats.values()):
        if (
            seat.controller_type != SeatControllerType.REMOTE
            or seat.took_over_by_bot
            or not seat.is_disconnected
        ):
            continue

        presence_manager.cancel_grace_timer(match.match_id, seat.seat_index)
        presence_manager.revoke_seat_token(match.match_id, seat.seat_index)
        # Mark for elimination at round end (same as grace-timer expiry).
        if not seat.player.is_eliminated:
            match.voluntarily_left_seats.add(seat.seat_index)
        match_service.takeover_seat(match, seat.seat_index)
        room_service.mark_participant_bot_takeover(room_code, seat.seat_index)
        await manager.broadcast_to_room(
            room_code,
            {
                "type": "SEAT_BOT_TAKEOVER",
                "data": {"seat_index": seat.seat_index},
            },
        )


def _start_selection_timeout(
    room_code: str,
    match,
    manager: ConnectionManager,
    match_service: MatchService,
    presence_manager: PresenceManager,
    room_service: RoomService | None = None,
) -> None:
    """
    Schedule a card-selection timeout for the current SELECTING phase.

    The callback passed to PresenceManager will resolve the turn if all
    seats have selected after the timeout fires.
    """
    import time

    match.selection_started_at = time.time()

    async def on_ready(rc: str, m) -> None:
        await _execute_turn(rc, m, manager, match_service, presence_manager, room_service)

    presence_manager.start_selection_timeout(
        match_id=match.match_id,
        match=match,
        match_service=match_service,
        manager=manager,
        room_code=room_code,
        on_turn_ready=on_ready,
    )


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------


async def _hello(ws: WebSocket, session: WsSession) -> None:
    await ws.send_json(
        {
            "type": "WS_WELCOME",
            "data": {"connection_id": session.connection_id},
        }
    )


async def _auth(ws: WebSocket, session: WsSession, data: dict, db) -> None:
    token = data.get("token")
    if not token:
        await _error(ws, "MISSING_TOKEN", "token is required", session=session)
        return

    try:
        payload = decode_token(token)
    except JWTError:
        await _error(ws, "INVALID_TOKEN", "Invalid or expired token", session=session)
        return

    if payload.get("type") != "access":
        await _error(ws, "INVALID_TOKEN", "Must use an access token", session=session)
        return

    user_id = payload.get("sub")
    if not user_id:
        await _error(ws, "INVALID_TOKEN", "Token has no subject", session=session)
        return

    user = user_repo.get_by_id(db, user_id)
    if user is None:
        await _error(ws, "USER_NOT_FOUND", "User not found", session=session)
        return

    if user.status != UserStatus.ACTIVE:
        await _error(ws, "ACCOUNT_NOT_ACTIVE", "Account is not active", session=session)
        return

    session.user_id = user_id
    session.account_type = user.account_type.value
    session.display_name = user.profile.nickname

    logger.info(
        "ws_auth_ok",
        extra={
            "conn_id": session.connection_id,
            "user_id": user_id,
            "account_type": session.account_type,
        },
    )

    await ws.send_json(
        {
            "type": "AUTH_OK",
            "data": {
                "user_id": user_id,
                "display_name": session.display_name,
                "account_type": session.account_type,
            },
        }
    )


async def _room_create(
    ws: WebSocket,
    session: WsSession,
    manager: ConnectionManager,
    room_service: RoomService,
) -> None:
    if not session.is_authenticated:
        await _error(
            ws,
            "NOT_AUTHENTICATED",
            "Authenticate before creating a room",
            session=session,
        )
        return
    if session.in_room:
        await _error(ws, "ALREADY_IN_ROOM", "Leave your current room first", session=session)
        return

    room = room_service.create_room(
        display_name=session.display_name,
        connection_id=session.connection_id,
        user_id=session.user_id,
        account_type=session.account_type or "guest",
    )
    session.room_code = room.room_code
    session.seat_index = 0
    manager.join_room(session.connection_id, room.room_code)
    await manager.broadcast_to_room(
        room.room_code,
        {
            "type": "ROOM_STATE",
            "data": room.to_dict(),
        },
    )


async def _room_join(
    ws: WebSocket,
    session: WsSession,
    data: dict,
    manager: ConnectionManager,
    room_service: RoomService,
) -> None:
    if not session.is_authenticated:
        await _error(ws, "NOT_AUTHENTICATED", "Authenticate before joining a room", session=session)
        return
    if session.in_room:
        await _error(ws, "ALREADY_IN_ROOM", "Leave your current room first", session=session)
        return

    room_code = (data.get("room_code") or "").strip().upper()
    if not room_code:
        await _error(ws, "MISSING_ROOM_CODE", "room_code is required", session=session)
        return

    try:
        room = room_service.join_room(
            room_code=room_code,
            display_name=session.display_name,
            connection_id=session.connection_id,
            user_id=session.user_id,
            account_type=session.account_type or "guest",
        )
    except RoomError as exc:
        await _error(ws, "ROOM_ERROR", str(exc), session=session)
        return

    session.room_code = room.room_code
    for seat_idx, p in room.participants.items():
        if p.connection_id == session.connection_id:
            session.seat_index = seat_idx
            break

    manager.join_room(session.connection_id, room.room_code)
    await manager.broadcast_to_room(
        room.room_code,
        {
            "type": "ROOM_STATE",
            "data": room.to_dict(),
        },
    )


async def _room_leave(
    ws: WebSocket,
    session: WsSession,
    manager: ConnectionManager,
    room_service: RoomService,
) -> None:
    if not session.in_room:
        await _error(ws, "NOT_IN_ROOM", "You are not in a room", session=session)
        return

    room_code = session.room_code
    seat_index = session.seat_index
    session.room_code = None
    session.seat_index = None

    manager.leave_room(session.connection_id, room_code)
    updated = room_service.leave_room(room_code, seat_index)
    if updated:
        await manager.broadcast_to_room(
            room_code,
            {
                "type": "ROOM_STATE",
                "data": updated.to_dict(),
            },
        )


async def _ready_set(
    ws: WebSocket,
    session: WsSession,
    data: dict,
    manager: ConnectionManager,
    room_service: RoomService,
) -> None:
    if not session.in_room:
        await _error(ws, "NOT_IN_ROOM", "You are not in a room", session=session)
        return

    is_ready = bool(data.get("is_ready", False))
    try:
        room = room_service.set_ready(session.room_code, session.seat_index, is_ready)
    except RoomError as exc:
        await _error(ws, "ROOM_ERROR", str(exc), session=session)
        return

    await manager.broadcast_to_room(
        session.room_code,
        {
            "type": "ROOM_STATE",
            "data": room.to_dict(),
        },
    )


async def _room_start(
    ws: WebSocket,
    session: WsSession,
    manager: ConnectionManager,
    room_service: RoomService,
    match_service: MatchService,
    presence_manager: PresenceManager,
) -> None:
    if not session.in_room:
        await _error(ws, "NOT_IN_ROOM", "You are not in a room", session=session)
        return

    try:
        room = room_service.start_room(session.room_code, session.seat_index)
    except RoomError as exc:
        await _error(ws, "ROOM_ERROR", str(exc), session=session)
        return

    # Broadcast final lobby state (phase=STARTING, all bots visible).
    await manager.broadcast_to_room(
        session.room_code,
        {
            "type": "ROOM_STATE",
            "data": room.to_dict(),
        },
    )

    # Create the server-side match (deals cards, auto-selects bots).
    try:
        match = match_service.create_match(room)
    except MatchError as exc:
        await _error(ws, "MATCH_ERROR", str(exc), session=session)
        return

    session.match_id = match.match_id

    # Announce match to all room members.
    await manager.broadcast_to_room(
        session.room_code,
        {
            "type": "MATCH_START",
            "data": {"match_id": match.match_id},
        },
    )

    await _issue_reconnect_tokens(session.room_code, match, manager, presence_manager)

    # Send initial game state so clients can start rendering.
    await _broadcast_selecting(session.room_code, match, manager, match_service)
    # All-bot edge case: if every seat is already selected (all bots), resolve
    # immediately rather than waiting for the timeout.
    if match_service.all_selected(match):
        await _execute_turn(session.room_code, match, manager, match_service, presence_manager)
    else:
        _start_selection_timeout(session.room_code, match, manager, match_service, presence_manager)


async def _card_select(
    ws: WebSocket,
    session: WsSession,
    data: dict,
    manager: ConnectionManager,
    match_service: MatchService,
    presence_manager: PresenceManager,
) -> None:
    if not session.in_room:
        await _error(ws, "NOT_IN_MATCH", "You are not in an active match", session=session)
        return

    match = match_service.get_match_by_room(session.room_code)
    if match is None:
        await _error(ws, "MATCH_NOT_FOUND", "Match not found", session=session)
        return

    card_number = data.get("card_number")
    if card_number is None:
        await _error(ws, "MISSING_CARD", "card_number is required", session=session)
        return

    try:
        match_service.submit_selection(match, session.seat_index, int(card_number))
    except MatchError as exc:
        await _error(ws, "MATCH_ERROR", str(exc), session=session)
        return

    # Acknowledge selection to the submitting seat.
    private = match_service.build_private_state(match, session.seat_index)
    await manager.send_to(
        session.connection_id,
        {
            "type": "PRIVATE_HAND_STATE",
            "data": private_state_to_dict(private),
        },
    )

    # If all seats have now selected, cancel timeout and resolve the turn.
    if match_service.all_selected(match):
        presence_manager.cancel_selection_timeout(match.match_id)
        await _execute_turn(session.room_code, match, manager, match_service, presence_manager)


async def _round_ready(
    ws: WebSocket,
    session: WsSession,
    manager: ConnectionManager,
    match_service: MatchService,
    room_service: RoomService,
    presence_manager: PresenceManager,
) -> None:
    """Acknowledge the round-settlement screen and continue when all are ready."""
    if not session.in_room:
        await _error(ws, "NOT_IN_MATCH", "You are not in an active match", session=session)
        return

    match = match_service.get_match_by_room(session.room_code)
    if match is None:
        await _error(ws, "MATCH_NOT_FOUND", "Match not found", session=session)
        return

    try:
        everyone_ready = match_service.mark_round_ready(match, session.seat_index)
    except MatchError as exc:
        await _error(ws, "MATCH_ERROR", str(exc), session=session)
        return

    if everyone_ready:
        presence_manager.cancel_round_settlement_timeout(match.match_id)
        await _continue_after_round_settlement(
            session.room_code,
            match,
            manager,
            match_service,
            room_service,
            presence_manager,
        )


async def _match_leave(
    ws: WebSocket,
    session: WsSession,
    manager: ConnectionManager,
    room_service: RoomService,
    match_service: MatchService,
    presence_manager: PresenceManager,
) -> None:
    """
    Handle a player voluntarily leaving mid-match.

    The seat is immediately converted to bot control.  If the player was
    not already eliminated, they are added to voluntarily_left_seats so
    that finalize_round() will mark them as eliminated at round end.
    """
    if not session.in_room:
        await _error(ws, "NOT_IN_MATCH", "You are not in an active match", session=session)
        return

    match = match_service.get_match_by_room(session.room_code)
    if match is None:
        await _error(ws, "MATCH_NOT_FOUND", "Match not found", session=session)
        return

    seat = match.seats.get(session.seat_index)
    if seat is None:
        await _error(ws, "SEAT_NOT_FOUND", "Seat not found", session=session)
        return

    room_code = session.room_code
    seat_index = session.seat_index

    # Mark as voluntarily left (unless already eliminated).
    if not seat.player.is_eliminated:  # type: ignore[union-attr]
        match.voluntarily_left_seats.add(seat_index)

    # Convert to bot immediately.
    if seat.controller_type == SeatControllerType.REMOTE:
        presence_manager.cancel_grace_timer(match.match_id, seat_index)
        presence_manager.revoke_seat_token(match.match_id, seat_index)
        match_service.takeover_seat(match, seat_index)
        room_service.mark_participant_bot_takeover(room_code, seat_index)
        await manager.broadcast_to_room(
            room_code,
            {
                "type": "SEAT_BOT_TAKEOVER",
                "data": {"seat_index": seat_index},
            },
        )

    # Acknowledge the leave to the departing client.
    await ws.send_json({"type": "MATCH_LEAVE_OK", "data": {}})

    # Clear session match state so the client can return to lobby.
    session.room_code = None
    session.seat_index = None
    session.match_id = None
    session.reconnect_token = None
    manager.leave_room(session.connection_id, room_code)

    # If this was the last human seat pending selection, check all_selected.
    if match_service.all_selected(match):
        presence_manager.cancel_selection_timeout(match.match_id)
        await _execute_turn(room_code, match, manager, match_service, presence_manager)

    # If round settlement was waiting on this seat, check if everyone ready now.
    if match_service.has_round_settlement_pending(match):
        required = {
            s.seat_index
            for s in match.seats.values()
            if s.controller_type == SeatControllerType.REMOTE and not s.player.is_eliminated  # type: ignore[union-attr]
        }
        if required.issubset(match.round_settlement_ready_seats):
            presence_manager.cancel_round_settlement_timeout(match.match_id)
            await _continue_after_round_settlement(
                room_code,
                match,
                manager,
                match_service,
                room_service,
                presence_manager,
            )


async def _reconnect(
    ws: WebSocket,
    session: WsSession,
    data: dict,
    manager: ConnectionManager,
    room_service: RoomService,
    match_service: MatchService,
    presence_manager: PresenceManager,
    db,
) -> None:
    """
    Restore a disconnected seat to a live WebSocket connection.

    The client sends RECONNECT with the token that was issued at match start.
    On success the session is fully restored and a snapshot is sent so the
    client can re-render the current game state.
    """
    token = data.get("token")
    if not token:
        await _error(ws, "MISSING_TOKEN", "token is required", session=session)
        return

    entry = presence_manager.lookup_token(token)
    if entry is None:
        logger.warning("reconnect_invalid_token", extra={"conn_id": session.connection_id})
        await _error(
            ws,
            "INVALID_RECONNECT_TOKEN",
            "Reconnect token is invalid or expired",
            session=session,
        )
        return

    if entry.account_type != "registered":
        logger.warning(
            "reconnect_guest_denied",
            extra={"conn_id": session.connection_id, "match_id": entry.match_id},
        )
        await _error(
            ws,
            "GUEST_RECONNECT_NOT_ALLOWED",
            "Guest seats cannot reconnect",
            session=session,
        )
        return

    # Re-check account status for registered users so that suspended/deleted
    # accounts cannot slip back in via a still-valid reconnect token.
    if entry.account_type == "registered" and entry.user_id:
        from app.models.db import UserStatus

        user = user_repo.get_by_id(db, entry.user_id)
        if user is None or user.status != UserStatus.ACTIVE:
            logger.warning(
                "reconnect_account_inactive",
                extra={"user_id": entry.user_id, "match_id": entry.match_id},
            )
            await _error(
                ws, "ACCOUNT_NOT_ACTIVE", "Account is not active",
                session=session,
            )
            return

    match = match_service.get_match(entry.match_id)
    if match is None:
        logger.info(
            "reconnect_match_ended",
            extra={"match_id": entry.match_id, "conn_id": session.connection_id},
        )
        await _error(ws, "MATCH_NOT_FOUND", "Match has already ended", session=session)
        return

    seat = match.seats.get(entry.seat_index)
    if seat is None:
        logger.warning(
            "reconnect_seat_missing",
            extra={"match_id": entry.match_id, "seat": entry.seat_index},
        )
        await _error(ws, "SEAT_NOT_FOUND", "Seat no longer exists in match", session=session)
        return

    if seat.took_over_by_bot:
        logger.info(
            "reconnect_seat_taken_over",
            extra={"match_id": entry.match_id, "seat": entry.seat_index},
        )
        await _error(
            ws,
            "SEAT_TAKEN_OVER",
            "This seat has been permanently taken over by a bot",
            session=session,
        )
        return

    old_room_code = session.room_code

    # Restore full session state.
    session.user_id = entry.user_id
    session.display_name = entry.display_name
    session.account_type = entry.account_type
    session.room_code = entry.room_code
    session.seat_index = entry.seat_index
    session.match_id = entry.match_id
    session.reconnect_token = token
    session.awaiting_pong = False

    # If this socket is already in a room (possibly different), leave it first
    # to prevent cross-room broadcast leaks.
    if old_room_code:
        manager.leave_room(session.connection_id, old_room_code)

    # Update match seat and room participant to the new connection.
    match_service.reconnect_seat(match, entry.seat_index, session.connection_id)
    room_service.reconnect_participant(entry.room_code, entry.seat_index, session.connection_id)

    # Re-join the ConnectionManager room so broadcasts reach this connection.
    manager.join_room(session.connection_id, entry.room_code)

    # Cancel the grace timer — the player is back.
    presence_manager.cancel_grace_timer(entry.match_id, entry.seat_index)

    # Acknowledge reconnect and send a full state snapshot.
    await ws.send_json(
        {
            "type": "RECONNECT_OK",
            "data": {
                "seat_index": entry.seat_index,
                "match_id": entry.match_id,
                "room_code": entry.room_code,
            },
        }
    )
    public = match_service.build_public_state(match)
    await ws.send_json(
        {
            "type": "PUBLIC_BOARD_STATE",
            "data": public_state_to_dict(public),
        }
    )
    private = match_service.build_private_state(match, entry.seat_index)
    await ws.send_json(
        {
            "type": "PRIVATE_HAND_STATE",
            "data": private_state_to_dict(private),
        }
    )
    if match_service.has_round_settlement_pending(match):
        summary = match.round_summary_pending
        if summary is not None:
            await ws.send_json(
                {
                    "type": "ROUND_RESULT",
                    "data": {
                        "round_number": summary.round_number,
                        "round_danger": summary.round_danger,
                        "total_scores": summary.total_scores,
                        "eliminated_seats": summary.eliminated_seats,
                        "game_over": summary.game_over,
                        "winner_seat": summary.winner_seat,
                        "timeout_seconds": settings.ROUND_SETTLEMENT_TIMEOUT_SECONDS,
                    },
                }
            )

    # Notify remaining room members.
    await manager.broadcast_to_room(
        entry.room_code,
        {
            "type": "PLAYER_RECONNECTED",
            "data": {"seat_index": entry.seat_index},
        },
    )


async def _execute_turn(
    room_code: str,
    match,
    manager: ConnectionManager,
    match_service: MatchService,
    presence_manager: PresenceManager,
    room_service: RoomService | None = None,
) -> None:
    """
    Resolve a full turn: broadcast each placement step, then either start
    the next selection phase or broadcast round/match end results.

    NOTE: callers are responsible for cancelling the selection timeout
    before invoking this function.  Cancelling inside _execute_turn would
    self-cancel the task when the call originates from _selection_timer's
    on_turn_ready callback, interrupting the turn resolution.
    """
    if room_service is None:
        from app.ws.endpoint import get_room_service

        room_service = get_room_service()

    await manager.broadcast_to_room(
        room_code,
        {
            "type": "TURN_REVEAL_START",
            "data": {"match_id": match.match_id},
        },
    )

    # Resolve placements one at a time; each snapshot reflects the board
    # state *after* that specific card was placed, not the final board.
    step_snapshots = match_service.resolve_turn_stepwise(match)

    for step, snapshot in step_snapshots:
        await manager.broadcast_to_room(
            room_code,
            {
                "type": "TURN_REVEAL_STEP",
                "data": {
                    "seat_index": step.seat_index,
                    "card_number": step.card_number,
                    "card_danger": step.card_danger,
                    "row_index": step.row_index,
                    "penalty_score": step.penalty_score,
                    "had_to_take_row": step.had_to_take_row,
                    "placement_order": step.order,
                    "penalty_card_count": step.penalty_card_count,
                },
            },
        )
        # Board state after this individual placement (incremental snapshot).
        await manager.broadcast_to_room(
            room_code,
            {
                "type": "PUBLIC_BOARD_STATE",
                "data": public_state_to_dict(snapshot),
            },
        )

    await manager.broadcast_to_room(
        room_code,
        {
            "type": "TURN_RESOLVED",
            "data": {"match_id": match.match_id},
        },
    )

    rules = match.rules  # fall_in.core.rules.GameRules
    if rules.is_round_over():
        summary = match_service.finalize_round(match)
        match_service.begin_round_settlement(match, summary)

        await manager.broadcast_to_room(
            room_code,
            {
                "type": "ROUND_RESULT",
                "data": {
                    "round_number": summary.round_number,
                    "round_danger": summary.round_danger,
                    "total_scores": summary.total_scores,
                    "eliminated_seats": summary.eliminated_seats,
                    "game_over": summary.game_over,
                    "winner_seat": summary.winner_seat,
                    "timeout_seconds": settings.ROUND_SETTLEMENT_TIMEOUT_SECONDS,
                },
            },
        )
        presence_manager.start_round_settlement_timeout(
            match.match_id,
            lambda: _continue_after_round_settlement(
                room_code,
                match,
                manager,
                match_service,
                room_service,
                presence_manager,
            ),
        )
    else:
        # More turns to go in this round — re-select bots, then re-enter SELECTING.
        match_service.reselect_bots(match)
        await _broadcast_selecting(room_code, match, manager, match_service)
        # Short-circuit: if bots hold all seats, no humans need to select.
        if match_service.all_selected(match):
            await _execute_turn(
                room_code,
                match,
                manager,
                match_service,
                presence_manager,
                room_service,
            )
        else:
            _start_selection_timeout(
                room_code,
                match,
                manager,
                match_service,
                presence_manager,
                room_service,
            )


async def _continue_after_round_settlement(
    room_code: str,
    match,
    manager: ConnectionManager,
    match_service: MatchService,
    room_service: RoomService,
    presence_manager: PresenceManager,
) -> None:
    """
    Resume match flow after the round-settlement screen.

    Non-gameover matches start the next round; gameover matches emit
    MATCH_RESULT and then clean up the match.
    """
    if not match_service.has_round_settlement_pending(match):
        return

    summary = match_service.clear_round_settlement(match)
    if summary is None:
        return

    presence_manager.cancel_round_settlement_timeout(match.match_id)

    if summary.game_over:
        await manager.broadcast_to_room(
            room_code,
            {
                "type": "MATCH_RESULT",
                "data": {
                    "match_id": match.match_id,
                    "winner_seat": summary.winner_seat,
                    "final_scores": summary.total_scores,
                },
            },
        )
        if match.is_ranked and summary.winner_seat is not None:
            _apply_mmr_update(match, summary.winner_seat)
        presence_manager.revoke_match_tokens(match.match_id)
        match_service.delete_match(match.match_id)
        return

    await _take_over_disconnected_seats_for_new_round(
        room_code,
        match,
        manager,
        match_service,
        room_service,
        presence_manager,
    )
    presence_manager.revoke_match_tokens(match.match_id)
    match_service.start_next_round(match)
    await _issue_reconnect_tokens(room_code, match, manager, presence_manager)
    await _broadcast_selecting(room_code, match, manager, match_service)
    if match_service.all_selected(match):
        await _execute_turn(room_code, match, manager, match_service, presence_manager)
    else:
        _start_selection_timeout(room_code, match, manager, match_service, presence_manager)


# ---------------------------------------------------------------------------
# MMR helper (PR-06)
# ---------------------------------------------------------------------------


def _apply_mmr_update(match, winner_seat: int) -> None:
    """
    Persist hidden MMR deltas for a ranked quick-match in a fresh DB session.

    Called synchronously from _execute_turn (which is async) so we create our
    own short-lived session rather than threading `db` through all callers.
    """
    from app.database import SessionLocal
    from app.services.mmr_service import mmr_service

    db = SessionLocal()
    try:
        mmr_service.persist_updates(db, match, winner_seat)
    except Exception:
        logger.exception(
            "mmr_update_failed",
            extra={"match_id": match.match_id, "winner_seat": winner_seat},
        )
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Quick-match handlers (PR-06)
# ---------------------------------------------------------------------------


async def _quick_match_join(
    ws: WebSocket,
    session: WsSession,
    manager: ConnectionManager,
    room_service: RoomService,
    match_service: MatchService,
    presence_manager: PresenceManager,
    matchmaking_service: MatchmakingService,
    db,
) -> None:
    """
    Enter the quick-match queue.

    Flow:
      1. Validate session state.
      2. Look up (or default) the player's hidden MMR.
      3. Add to the appropriate bucket queue.
      4. If bucket now has 4 players → form match immediately.
      5. Else start (or reuse) the bucket's fill timer.
      6. Send QUEUE_JOINED acknowledgement.
    """
    if not session.is_authenticated:
        await _error(
            ws,
            "NOT_AUTHENTICATED",
            "Authenticate before joining quick match",
            session=session,
        )
        return
    if session.in_room:
        await _error(
            ws,
            "ALREADY_IN_ROOM",
            "Leave your current room before joining quick match",
            session=session,
        )
        return
    if session.in_queue:
        await _error(
            ws,
            "ALREADY_IN_QUEUE",
            "You are already in the matchmaking queue",
            session=session,
        )
        return

    # Resolve MMR (guests always get DEFAULT_MMR; not stored).
    from app.services.mmr_service import mmr_service

    mmr = mmr_service.get_mmr_for_session(db, session.user_id, session.account_type or "guest")

    entry = matchmaking_service.join_queue(
        connection_id=session.connection_id,
        user_id=session.user_id,
        display_name=session.display_name,
        account_type=session.account_type or "guest",
        mmr=mmr,
    )
    session.in_queue = True

    bucket = entry.bucket
    queue_size = matchmaking_service.bucket_size(bucket)

    # Check for immediate 4-player match.
    four = matchmaking_service.try_form_match(bucket)
    if four is not None:
        # Cancel the fill timer if one was running for this bucket.
        matchmaking_service.cancel_fill_timer(bucket)
        # All 4 are human — ranked match.
        is_ranked = True
        await _start_quick_match(
            four,
            0,
            is_ranked,
            manager,
            room_service,
            match_service,
            presence_manager,
        )
        # WsSession fields (room_code, seat_index, match_id, in_queue) for all
        # four players are updated inside _start_quick_match() via the session
        # registry.  No extra work needed here.
        return

    # Start fill timer if this is the first player in the bucket.
    async def _on_fill(human_entries: list, ai_count: int, ranked: bool) -> None:
        await _start_quick_match(
            human_entries,
            ai_count,
            ranked,
            manager,
            room_service,
            match_service,
            presence_manager,
        )
        # Clear in_queue for each matched human connection (best-effort).
        for _e in human_entries:
            # The WsSession is not directly accessible here; endpoint.py
            # manages in_queue via the disconnect handler.  The session flag
            # is cleared when the connection receives MATCH_FOUND.
            pass

    matchmaking_service.start_fill_timer(bucket, _on_fill)

    await ws.send_json(
        {
            "type": "QUEUE_JOINED",
            "data": {
                # bucket is intentionally omitted — it would expose approximate
                # hidden MMR tier to the client, violating the hidden-MMR policy.
                "queue_size": queue_size,
                "fill_seconds": settings.QUICK_MATCH_FILL_SECONDS,
            },
        }
    )


async def _quick_match_leave(
    ws: WebSocket,
    session: WsSession,
    matchmaking_service: MatchmakingService,
) -> None:
    """Leave the quick-match queue before a match is formed."""
    if not session.in_queue:
        await _error(ws, "NOT_IN_QUEUE", "You are not in the matchmaking queue", session=session)
        return

    entry = matchmaking_service.leave_queue(session.connection_id)
    session.in_queue = False

    if entry is not None:
        # Cancel the fill timer if the bucket is now empty.
        if matchmaking_service.bucket_size(entry.bucket) == 0:
            matchmaking_service.cancel_fill_timer(entry.bucket)

    await ws.send_json({"type": "QUEUE_LEFT", "data": {}})


async def _start_quick_match(
    human_entries: list,
    ai_count: int,
    is_ranked: bool,
    manager: ConnectionManager,
    room_service: RoomService,
    match_service: MatchService,
    presence_manager: PresenceManager,
) -> None:
    """
    Create a match from queued players and broadcast the start to all humans.

    This is the shared entry point used by both the immediate-match path
    (4 humans found) and the fill-timer path (1-3 humans + AI bots).
    """
    from app.services.matchmaking_service import MatchmakingService as _MS

    room = _MS.build_quick_match_room(human_entries, ai_count)

    # Register the room so match_service can look it up by room_code.
    room_service.repo.create(room)

    try:
        match = match_service.create_match(room)
    except MatchError as exc:
        # Notify all affected humans; they must re-queue.
        for entry in human_entries:
            await manager.send_to(
                entry.connection_id,
                {
                    "type": "ERROR",
                    "data": {"code": "MATCH_ERROR", "message": str(exc)},
                },
            )
        return

    match.is_ranked = is_ranked

    logger.info(
        "match_start",
        extra={
            "match_id": match.match_id,
            "room_code": room.room_code,
            "is_ranked": is_ranked,
            "human_count": len(human_entries),
            "ai_count": ai_count,
        },
    )

    # Notify each human: MATCH_FOUND clears in_queue on the client side.
    for seat_idx, entry in enumerate(human_entries):
        # Update the server-side WsSession so CARD_SELECT / disconnect paths
        # work correctly.  The session must reflect room/match membership before
        # the client can send any match messages.
        ws_session = manager.get_session(entry.connection_id)
        if ws_session is not None:
            ws_session.in_queue = False
            ws_session.room_code = room.room_code
            ws_session.seat_index = seat_idx
            ws_session.match_id = match.match_id

        await manager.send_to(
            entry.connection_id,
            {
                "type": "MATCH_FOUND",
                "data": {
                    "match_id": match.match_id,
                    "room_code": room.room_code,
                    "seat_index": seat_idx,
                    "is_ranked": is_ranked,
                },
            },
        )
        # Add to ConnectionManager room so broadcasts reach this connection.
        manager.join_room(entry.connection_id, room.room_code)

    # Announce match start.
    await manager.broadcast_to_room(
        room.room_code,
        {
            "type": "MATCH_START",
            "data": {"match_id": match.match_id},
        },
    )

    await _issue_reconnect_tokens(room.room_code, match, manager, presence_manager)

    # Send initial game state.
    public = match_service.build_public_state(match)
    await manager.broadcast_to_room(
        room.room_code,
        {
            "type": "PHASE_SELECTING",
            "data": public_state_to_dict(public),
        },
    )
    for seat in match.seats.values():
        if seat.controller_type == SeatControllerType.REMOTE and seat.connection_id:
            private = match_service.build_private_state(match, seat.seat_index)
            await manager.send_to(
                seat.connection_id,
                {
                    "type": "PRIVATE_HAND_STATE",
                    "data": private_state_to_dict(private),
                },
            )

    # Schedule selection timeout (or short-circuit if all-bot).
    if match_service.all_selected(match):
        await _execute_turn(room.room_code, match, manager, match_service, presence_manager)
    else:
        import time as _time

        match.selection_started_at = _time.time()

        async def _on_ready(rc: str, m) -> None:
            await _execute_turn(rc, m, manager, match_service, presence_manager)

        presence_manager.start_selection_timeout(
            match_id=match.match_id,
            match=match,
            match_service=match_service,
            manager=manager,
            room_code=room.room_code,
            on_turn_ready=_on_ready,
        )


# ---------------------------------------------------------------------------
# Emote handlers (PR-07)
# ---------------------------------------------------------------------------


async def _emote_send(
    ws: WebSocket,
    session: WsSession,
    data: dict,
    manager: ConnectionManager,
) -> None:
    """
    Relay an emote from one player to all room participants.

    Validation:
      - Session must be authenticated and in a room.
      - emote_id must be in the permitted catalog.
      - Per-connection rate limits (cooldown + burst cap) must not be exceeded.

    On success: broadcasts EMOTE_BROADCAST to every room member whose
    session does not have emotes_muted=True.
    The sender always receives the broadcast (they see their own emote).
    """
    from app.services.emote_service import emote_service

    if not session.is_authenticated:
        await _error(ws, "NOT_AUTHENTICATED", "Authenticate before sending emotes", session=session)
        return

    if not session.in_room:
        await _error(ws, "NOT_IN_ROOM", "Join a room before sending emotes", session=session)
        return

    emote_id = data.get("emote_id", "")
    if not emote_service.is_valid_emote(emote_id):
        await _error(ws, "INVALID_EMOTE", f"Unknown emote: {emote_id!r}", session=session)
        return

    if not emote_service.check_and_record(session.connection_id, emote_id):
        reason = emote_service.last_deny_reason(session.connection_id)
        if reason == "cooldown":
            cooldown = emote_service.remaining_cooldown(session.connection_id)
            msg = f"Sending emotes too fast — wait {cooldown:.1f}s"
        elif reason == "burst":
            msg = "Emote burst cap reached — slow down"
        else:  # same_emote
            msg = "Send a different emote before repeating"
        logger.warning(
            "emote_rate_limited",
            extra={
                "conn_id": session.connection_id,
                "emote_id": emote_id,
                "reason": reason,
            },
        )
        await ws.send_json(
            {
                "type": "ERROR",
                "data": {
                    "code": "EMOTE_RATE_LIMITED",
                    "reason": reason,
                    "message": msg,
                },
            }
        )
        return

    payload = {
        "type": "EMOTE_BROADCAST",
        "data": {
            "seat_index": session.seat_index,
            "emote_id": emote_id,
        },
    }

    # Fan out to every room member, skipping connections with mutes.
    for conn_id in manager.get_room_members(session.room_code):
        target_session = manager.get_session(conn_id)
        if target_session is not None and target_session.emotes_muted:
            continue
        await manager.send_to(conn_id, payload)


async def _emote_mute(
    ws: WebSocket,
    session: WsSession,
    data: dict,
) -> None:
    """
    Toggle emote broadcast reception for this connection.

    The client sends {"type": "EMOTE_MUTE", "data": {"muted": true|false}}.
    The server acknowledges with EMOTE_MUTE_ACK carrying the new state.
    When muted=True, this connection will no longer receive EMOTE_BROADCAST
    messages until it explicitly unmutes.
    """
    muted = bool(data.get("muted", True))
    session.emotes_muted = muted
    await ws.send_json({"type": "EMOTE_MUTE_ACK", "data": {"muted": session.emotes_muted}})
