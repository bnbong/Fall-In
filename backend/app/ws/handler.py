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
        await _room_start(ws, session, manager, room_service, match_service, presence_manager)
    elif msg_type == "CARD_SELECT":
        await _card_select(ws, session, data, manager, match_service, presence_manager)
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
    await manager.broadcast_to_room(
        room_code,
        {
            "type": "PHASE_SELECTING",
            "data": public_state_to_dict(public),
        },
    )
    await _broadcast_private_hands(match, manager, match_service)


def _start_selection_timeout(
    room_code: str,
    match,
    manager: ConnectionManager,
    match_service: MatchService,
    presence_manager: PresenceManager,
) -> None:
    """
    Schedule a card-selection timeout for the current SELECTING phase.

    The callback passed to PresenceManager will resolve the turn if all
    seats have selected after the timeout fires.
    """
    import time

    match.selection_started_at = time.time()

    async def on_ready(rc: str, m) -> None:
        await _execute_turn(rc, m, manager, match_service, presence_manager)

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
        await _error(ws, "NOT_IN_ROOM", "You are not in a room")
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
        await _error(ws, "NOT_IN_ROOM", "You are not in a room")
        return

    is_ready = bool(data.get("is_ready", False))
    try:
        room = room_service.set_ready(session.room_code, session.seat_index, is_ready)
    except RoomError as exc:
        await _error(ws, "ROOM_ERROR", str(exc))
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
        await _error(ws, "NOT_IN_ROOM", "You are not in a room")
        return

    try:
        room = room_service.start_room(session.room_code, session.seat_index)
    except RoomError as exc:
        await _error(ws, "ROOM_ERROR", str(exc))
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
        await _error(ws, "MATCH_ERROR", str(exc))
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

    # Issue a reconnect token to each human seat and unicast it.
    for seat in match.seats.values():
        if seat.controller_type == SeatControllerType.REMOTE and seat.connection_id:
            account_type = "registered" if seat.user_id else "guest"
            token = presence_manager.issue_token(
                match_id=match.match_id,
                room_code=session.room_code,
                seat_index=seat.seat_index,
                user_id=seat.user_id,
                display_name=seat.display_name,
                account_type=account_type,
            )
            # Store token on the issuing seat's session (host).
            # Non-host human sessions receive their token below via send_to.
            if seat.connection_id == session.connection_id:
                session.reconnect_token = token
            await manager.send_to(
                seat.connection_id,
                {
                    "type": "RECONNECT_TOKEN",
                    "data": {"token": token, "seat_index": seat.seat_index},
                },
            )

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
        await _error(ws, "MISSING_TOKEN", "token is required")
        return

    entry = presence_manager.lookup_token(token)
    if entry is None:
        await _error(ws, "INVALID_RECONNECT_TOKEN", "Reconnect token is invalid or expired")
        return

    # Re-check account status for registered users so that suspended/deleted
    # accounts cannot slip back in via a still-valid reconnect token.
    if entry.account_type == "registered" and entry.user_id:
        from app.models.db import UserStatus

        user = user_repo.get_by_id(db, entry.user_id)
        if user is None or user.status != UserStatus.ACTIVE:
            await _error(ws, "ACCOUNT_NOT_ACTIVE", "Account is not active")
            return

    match = match_service.get_match(entry.match_id)
    if match is None:
        await _error(ws, "MATCH_NOT_FOUND", "Match has already ended")
        return

    seat = match.seats.get(entry.seat_index)
    if seat is None:
        await _error(ws, "SEAT_NOT_FOUND", "Seat no longer exists in match")
        return

    if seat.took_over_by_bot:
        await _error(ws, "SEAT_TAKEN_OVER", "This seat has been permanently taken over by a bot")
        return

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
    if session.room_code:
        manager.leave_room(session.connection_id, session.room_code)

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
) -> None:
    """
    Resolve a full turn: broadcast each placement step, then either start
    the next selection phase or broadcast round/match end results.
    """
    # Cancel any lingering selection timeout for this turn.
    presence_manager.cancel_selection_timeout(match.match_id)

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
                },
            },
        )

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
            # Persist hidden MMR for eligible ranked quick-match results.
            if match.is_ranked and summary.winner_seat is not None:
                _apply_mmr_update(match, summary.winner_seat)
            presence_manager.revoke_match_tokens(match.match_id)
            match_service.delete_match(match.match_id)
        else:
            match_service.start_next_round(match)
            await _broadcast_selecting(room_code, match, manager, match_service)
            # Short-circuit: if bots hold all seats, no humans need to select.
            if match_service.all_selected(match):
                await _execute_turn(room_code, match, manager, match_service, presence_manager)
            else:
                _start_selection_timeout(room_code, match, manager, match_service, presence_manager)
    else:
        # More turns to go in this round — re-select bots, then re-enter SELECTING.
        match_service.reselect_bots(match)
        await _broadcast_selecting(room_code, match, manager, match_service)
        # Short-circuit: if bots hold all seats, no humans need to select.
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
        await _error(ws, "NOT_AUTHENTICATED", "Authenticate before joining quick match")
        return
    if session.in_room:
        await _error(ws, "ALREADY_IN_ROOM", "Leave your current room before joining quick match")
        return
    if session.in_queue:
        await _error(ws, "ALREADY_IN_QUEUE", "You are already in the matchmaking queue")
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
        await _error(ws, "NOT_IN_QUEUE", "You are not in the matchmaking queue")
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

    # Issue reconnect tokens to each human seat.
    for seat in match.seats.values():
        if seat.controller_type == SeatControllerType.REMOTE and seat.connection_id:
            account_type = seat.user_id and "registered" or "guest"
            # Check if there's a matching entry to determine account_type accurately.
            for e in human_entries:
                if e.connection_id == seat.connection_id:
                    account_type = e.account_type
                    break
            token = presence_manager.issue_token(
                match_id=match.match_id,
                room_code=room.room_code,
                seat_index=seat.seat_index,
                user_id=seat.user_id,
                display_name=seat.display_name,
                account_type=account_type,
            )
            await manager.send_to(
                seat.connection_id,
                {
                    "type": "RECONNECT_TOKEN",
                    "data": {"token": token, "seat_index": seat.seat_index},
                },
            )

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
        await _error(ws, "NOT_AUTHENTICATED", "Authenticate before sending emotes")
        return

    if not session.in_room:
        await _error(ws, "NOT_IN_ROOM", "Join a room before sending emotes")
        return

    emote_id = data.get("emote_id", "")
    if not emote_service.is_valid_emote(emote_id):
        await _error(ws, "INVALID_EMOTE", f"Unknown emote: {emote_id!r}")
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
