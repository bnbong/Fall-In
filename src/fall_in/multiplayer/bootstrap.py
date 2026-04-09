"""
Helpers for bootstrapping a remote multiplayer GameScene.

This keeps the RoomLobbyScene and MultiplayerMenuScene reconnect path in
sync so both launch the exact same remote adapter / network routing stack.
"""

from __future__ import annotations

from typing import Iterable

from fall_in.core.game_manager import GameManager, GameState
from fall_in.multiplayer.models import (
    ControllerType,
    MatchCardPublic,
    PrivatePlayerState,
    PublicMatchState,
    SeatIdentity,
)
from fall_in.multiplayer.remote_adapter import RemoteGameAdapter


def build_remote_match_loading_scene(
    *,
    ws,
    my_seat: int,
    bootstrap_messages: Iterable[tuple[str, dict]] = (),
):
    """
    Build the loading-scene transition that launches a remote GameScene.

    ``bootstrap_messages`` lets callers preserve messages that arrived in the
    same pump batch as MATCH_START / RECONNECT_OK so no initial game-state
    packets are lost before the first frame.
    """
    adapter = RemoteGameAdapter(my_seat=my_seat)
    pending_messages = list(bootstrap_messages)

    def _network_tick() -> None:
        nonlocal pending_messages
        pending_reveal_step: dict | None = None

        messages = pending_messages + ws.pump()
        pending_messages = []
        for msg_type, data in messages:
            if msg_type == "TURN_REVEAL_START":
                adapter.begin_turn_reveal()
            elif msg_type == "TURN_REVEAL_STEP":
                pending_reveal_step = dict(data)
            elif msg_type == "TURN_RESOLVED":
                pending_reveal_step = None
                adapter.finish_turn_reveal()
            elif msg_type in ("PHASE_SELECTING", "PUBLIC_BOARD_STATE"):
                state = _deserialise_public(data)
                if state is not None:
                    if msg_type == "PHASE_SELECTING":
                        remaining = float(data.get("remaining_time", 30.0))
                        adapter.notify_selecting_phase_started(remaining)
                    if (
                        pending_reveal_step is not None
                        and adapter.is_turn_reveal_active()
                    ):
                        adapter.queue_turn_reveal_step(pending_reveal_step, state)
                        pending_reveal_step = None
                    elif adapter.is_turn_reveal_active():
                        adapter.queue_post_reveal_public_state(state)
                    else:
                        adapter.apply_public_state(state)
            elif msg_type == "PRIVATE_HAND_STATE":
                private = _deserialise_private(data)
                if private is not None:
                    try:
                        adapter.apply_private_state(private)
                    except ValueError:
                        pass
            elif msg_type == "ROUND_RESULT":
                adapter.queue_round_result(data)
            elif msg_type == "MATCH_RESULT":
                adapter.queue_match_result(data)
            elif msg_type == "EMOTE_BROADCAST":
                seat_idx = data.get("seat_index", 0)
                emote_id = data.get("emote_id", "")
                if emote_id:
                    adapter.apply_emote(seat_idx, emote_id)
            elif msg_type == "SELECTION_TIMEOUT":
                timed_out = data.get("timed_out_seats", [])
                adapter.notify_selection_timeout([int(s) for s in timed_out])
            elif msg_type == "PLAYER_DISCONNECTED":
                adapter.mark_seat_disconnected(int(data.get("seat_index", -1)))
            elif msg_type == "PLAYER_RECONNECTED":
                adapter.mark_seat_reconnected(int(data.get("seat_index", -1)))
            elif msg_type == "SEAT_BOT_TAKEOVER":
                adapter.mark_seat_bot_takeover(int(data.get("seat_index", -1)))
            elif msg_type == "RECONNECT_TOKEN":
                _store_reconnect_token(data)
            elif msg_type == "PING":
                ws.send("PONG")

    def _scene_builder():
        from fall_in.scenes.game_scene import GameScene

        GameManager().state = GameState.PLAYING
        scene = GameScene()
        scene.set_remote_adapter(adapter)
        scene.set_card_select_callback(
            lambda card_number: ws.send("CARD_SELECT", {"card_number": card_number})
        )
        scene.set_round_ready_callback(lambda: ws.send("ROUND_READY"))
        scene.set_emote_send_callback(
            lambda emote_id: ws.send("EMOTE_SEND", {"emote_id": emote_id})
        )
        scene.set_exit_match_callback(lambda: ws.send("MATCH_LEAVE"))
        scene.set_network_tick_callback(_network_tick)
        return scene

    gm = GameManager()
    prev_screen = gm.screen.copy() if gm.screen else None
    from fall_in.scenes.game_loading_scene import GameLoadingScene

    return GameLoadingScene(prev_screen=prev_screen, scene_builder=_scene_builder)


def _store_reconnect_token(data: dict) -> None:
    token = data.get("token")
    if not token:
        return

    GameManager().store_pending_match_reconnect(
        token=token,
        match_id=data.get("match_id", ""),
        room_code=data.get("room_code", ""),
        seat_index=int(data.get("seat_index", 0)),
    )


def _deserialise_public(data: dict):
    """Build a PublicMatchState from a wire dict, or return None on error."""
    try:
        board_rows = [
            [MatchCardPublic(**card) for card in row]
            for row in data.get("board_rows", [])
        ]
        played = [
            MatchCardPublic(**card) for card in data.get("played_cards_this_turn", [])
        ]
        seats = [
            SeatIdentity(
                seat_index=seat["seat_index"],
                controller_type=ControllerType(seat.get("controller_type", "remote")),
                display_name=seat.get("display_name", ""),
                user_id=seat.get("user_id"),
            )
            for seat in data.get("seats", [])
        ]
        return PublicMatchState(
            match_id=data.get("match_id", ""),
            round_number=data.get("round_number", 1),
            phase=data.get("phase", ""),
            player_order_seats=[
                int(seat) for seat in data.get("player_order_seats", [])
            ],
            board_rows=board_rows,
            played_cards_this_turn=played,
            committed_scores={
                int(seat_index): int(value)
                for seat_index, value in data.get("committed_scores", {}).items()
            },
            seats=seats,
        )
    except Exception:
        return None


def _deserialise_private(data: dict):
    """Build a PrivatePlayerState from a wire dict, or return None on error."""
    try:
        hand = [MatchCardPublic(**card) for card in data.get("hand", [])]
        return PrivatePlayerState(
            seat_index=int(data["seat_index"]),
            hand=hand,
            has_selected=bool(data.get("has_selected", False)),
            is_eliminated=bool(data.get("is_eliminated", False)),
        )
    except Exception:
        return None
