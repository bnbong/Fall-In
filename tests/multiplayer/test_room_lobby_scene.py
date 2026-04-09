"""
Tests for RoomLobbyScene multiplayer bootstrap.

These protect against two regressions:
  - MATCH_START must not force every client into seat 0.
  - Initial PHASE_SELECTING / PRIVATE_HAND_STATE messages that arrive in the
    same pump batch as MATCH_START must be preserved for the GameScene.
"""

from __future__ import annotations

from fall_in.core.game_manager import GameManager
from fall_in.scenes.room_lobby_scene import RoomLobbyScene


class _FakeWs:
    def __init__(self, messages: list[tuple[str, dict]]) -> None:
        self._messages = list(messages)
        self.sent: list[tuple[str, dict]] = []

    def pump(self) -> list[tuple[str, dict]]:
        messages = list(self._messages)
        self._messages.clear()
        return messages

    def send(self, msg_type: str, data: dict | None = None) -> None:
        self.sent.append((msg_type, data or {}))


class _FakeGameScene:
    def __init__(self) -> None:
        self.remote_adapter = None
        self.card_select_callback = None
        self.round_ready_callback = None
        self.emote_send_callback = None
        self.exit_match_callback = None
        self.network_tick_callback = None

    def set_remote_adapter(self, adapter) -> None:
        self.remote_adapter = adapter

    def set_card_select_callback(self, callback) -> None:
        self.card_select_callback = callback

    def set_round_ready_callback(self, callback) -> None:
        self.round_ready_callback = callback

    def set_emote_send_callback(self, callback) -> None:
        self.emote_send_callback = callback

    def set_exit_match_callback(self, callback) -> None:
        self.exit_match_callback = callback

    def set_network_tick_callback(self, callback) -> None:
        self.network_tick_callback = callback


class _FakeLoadingScene:
    def __init__(self, prev_screen=None, scene_builder=None) -> None:
        self.prev_screen = prev_screen
        self.scene_builder = scene_builder


def _make_room_data() -> dict:
    return {
        "room_code": "ABCD12",
        "host_seat_index": 0,
        "participants": [
            {
                "seat_index": 0,
                "display_name": "HostGuest",
                "controller_type": "remote",
                "is_ready": True,
            },
            {
                "seat_index": 1,
                "display_name": "GuestTwo",
                "controller_type": "remote",
                "is_ready": True,
            },
        ],
    }


def _make_public_state_dict() -> dict:
    return {
        "match_id": "match-123",
        "round_number": 1,
        "phase": "SELECTING",
        "player_order_seats": [1, 0, 2, 3],
        "board_rows": [[], [], [], []],
        "played_cards_this_turn": [],
        "committed_scores": {0: 0, 1: 0, 2: 0, 3: 0},
        "seats": [
            {"seat_index": 0, "controller_type": "remote", "display_name": "HostGuest"},
            {"seat_index": 1, "controller_type": "remote", "display_name": "GuestTwo"},
            {"seat_index": 2, "controller_type": "bot", "display_name": "AI 1"},
            {"seat_index": 3, "controller_type": "bot", "display_name": "AI 2"},
        ],
    }


def _make_private_state_dict() -> dict:
    return {
        "seat_index": 1,
        "hand": [
            {"number": 7, "danger": 1, "owner_seat": 1},
            {"number": 15, "danger": 2, "owner_seat": 1},
        ],
        "has_selected": False,
    }


def test_launch_game_uses_room_seat_when_match_start_has_no_my_seat(monkeypatch):
    ws = _FakeWs([("MATCH_START", {"match_id": "match-123"})])
    scene = RoomLobbyScene(
        ws=ws, room_data=_make_room_data(), my_display_name="GuestTwo"
    )

    captured: dict[str, object] = {}

    import fall_in.scenes.game_loading_scene as loading_module
    import fall_in.scenes.game_scene as game_scene_module

    monkeypatch.setattr(loading_module, "GameLoadingScene", _FakeLoadingScene)
    monkeypatch.setattr(game_scene_module, "GameScene", _FakeGameScene)
    monkeypatch.setattr(
        GameManager,
        "change_scene",
        lambda self, new_scene: captured.setdefault("scene", new_scene),
    )

    GameManager().screen = None

    scene._handle_ws_messages()

    loading_scene = captured["scene"]
    built_scene = loading_scene.scene_builder()
    assert built_scene.remote_adapter.my_seat == 1


def test_match_start_preserves_initial_public_and_private_messages(monkeypatch):
    ws = _FakeWs(
        [
            ("MATCH_START", {"match_id": "match-123"}),
            ("PHASE_SELECTING", _make_public_state_dict()),
            ("PRIVATE_HAND_STATE", _make_private_state_dict()),
        ]
    )
    scene = RoomLobbyScene(
        ws=ws, room_data=_make_room_data(), my_display_name="GuestTwo"
    )

    captured: dict[str, object] = {}

    import fall_in.scenes.game_loading_scene as loading_module
    import fall_in.scenes.game_scene as game_scene_module

    monkeypatch.setattr(loading_module, "GameLoadingScene", _FakeLoadingScene)
    monkeypatch.setattr(game_scene_module, "GameScene", _FakeGameScene)
    monkeypatch.setattr(
        GameManager,
        "change_scene",
        lambda self, new_scene: captured.setdefault("scene", new_scene),
    )

    GameManager().screen = None

    scene._handle_ws_messages()

    loading_scene = captured["scene"]
    built_scene = loading_scene.scene_builder()
    built_scene.network_tick_callback()

    public = built_scene.remote_adapter.get_public_state()
    private = built_scene.remote_adapter.get_private_state()

    assert public is not None
    assert private is not None
    assert public.seats[1].display_name == "GuestTwo"
    assert private.seat_index == 1
    assert [card.number for card in private.hand] == [7, 15]


def test_network_tick_routes_round_and_match_results(monkeypatch):
    ws = _FakeWs(
        [
            ("MATCH_START", {"match_id": "match-123"}),
            ("ROUND_RESULT", {"round_number": 1, "timeout_seconds": 8}),
            ("MATCH_RESULT", {"winner_seat": 1}),
        ]
    )
    scene = RoomLobbyScene(
        ws=ws, room_data=_make_room_data(), my_display_name="GuestTwo"
    )

    captured: dict[str, object] = {}

    import fall_in.scenes.game_loading_scene as loading_module
    import fall_in.scenes.game_scene as game_scene_module

    monkeypatch.setattr(loading_module, "GameLoadingScene", _FakeLoadingScene)
    monkeypatch.setattr(game_scene_module, "GameScene", _FakeGameScene)
    monkeypatch.setattr(
        GameManager,
        "change_scene",
        lambda self, new_scene: captured.setdefault("scene", new_scene),
    )

    GameManager().screen = None

    scene._handle_ws_messages()

    built_scene = captured["scene"].scene_builder()
    built_scene.network_tick_callback()

    assert built_scene.remote_adapter.pop_round_result() == {
        "round_number": 1,
        "timeout_seconds": 8,
    }
    assert built_scene.remote_adapter.pop_match_result() == {"winner_seat": 1}


def test_scene_builder_wires_round_ready_callback(monkeypatch):
    ws = _FakeWs([("MATCH_START", {"match_id": "match-123"})])
    scene = RoomLobbyScene(
        ws=ws, room_data=_make_room_data(), my_display_name="GuestTwo"
    )

    captured: dict[str, object] = {}

    import fall_in.scenes.game_loading_scene as loading_module
    import fall_in.scenes.game_scene as game_scene_module

    monkeypatch.setattr(loading_module, "GameLoadingScene", _FakeLoadingScene)
    monkeypatch.setattr(game_scene_module, "GameScene", _FakeGameScene)
    monkeypatch.setattr(
        GameManager,
        "change_scene",
        lambda self, new_scene: captured.setdefault("scene", new_scene),
    )

    GameManager().screen = None

    scene._handle_ws_messages()

    built_scene = captured["scene"].scene_builder()
    built_scene.round_ready_callback()

    assert ("ROUND_READY", {}) in ws.sent
