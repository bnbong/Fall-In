"""
Focused tests for multiplayer-specific GameScene helpers.
"""

from __future__ import annotations

from types import SimpleNamespace

from fall_in.core.game_manager import GameManager
from fall_in.core.player import PlayerType
from fall_in.multiplayer.models import (
    ControllerType,
    MatchCardPublic,
    PrivatePlayerState,
    PublicMatchState,
    SeatIdentity,
)
from fall_in.multiplayer.remote_adapter import RemoteGameAdapter
from fall_in.scenes.game_scene import GameScene


def _make_public_state() -> PublicMatchState:
    return PublicMatchState(
        match_id="match-42",
        round_number=1,
        phase="SELECTING",
        player_order_seats=[2, 0, 1, 3],
        board_rows=[[], [], [], []],
        played_cards_this_turn=[],
        committed_scores={0: 0, 1: 0, 2: 5, 3: 0},
        seats=[
            SeatIdentity(0, ControllerType.REMOTE, "HostGuest"),
            SeatIdentity(1, ControllerType.BOT, "AI 1"),
            SeatIdentity(2, ControllerType.REMOTE, "GuestTwo"),
            SeatIdentity(3, ControllerType.BOT, "AI 2"),
        ],
    )


def test_on_emote_selected_uses_local_multiplayer_seat():
    scene = object.__new__(GameScene)
    scene._remote_adapter = SimpleNamespace(my_seat=2)
    sent: list[str] = []
    shown: list[tuple[int, str]] = []
    scene._emote_send_callback = sent.append
    scene.show_emote = lambda seat_index, emote_id: shown.append((seat_index, emote_id))

    GameScene._on_emote_selected(scene, "fire")

    assert shown == [(2, "fire")]
    assert sent == ["fire"]


def test_confirm_card_selection_sends_card_number_in_remote_mode():
    adapter = RemoteGameAdapter(my_seat=2)
    adapter.apply_public_state(_make_public_state())
    adapter.apply_private_state(
        PrivatePlayerState(
            seat_index=2,
            hand=[
                MatchCardPublic(number=7, danger=1, owner_seat=2),
                MatchCardPublic(number=15, danger=2, owner_seat=2),
            ],
            has_selected=False,
        )
    )

    scene = object.__new__(GameScene)
    scene._remote_adapter = adapter
    scene._card_select_callback = None
    scene._emote_send_callback = None
    scene.selected_card_index = 1
    scene.message = ""
    scene.message_timer = 0.0
    scene.human_player = SimpleNamespace(hand=[])

    sent_cards: list[int] = []
    scene._card_select_callback = sent_cards.append

    GameScene._confirm_card_selection(scene)

    assert sent_cards == [15]
    assert scene.selected_card_index is None


def test_player_order_entries_use_remote_display_names():
    adapter = RemoteGameAdapter(my_seat=2)
    adapter.apply_public_state(_make_public_state())

    scene = object.__new__(GameScene)
    scene._remote_adapter = adapter

    entries = GameScene._get_player_order_entries(scene)

    assert entries == [
        ("나", True),
        ("1", False),
        ("2", False),
        ("4", False),
    ]


def test_remote_reveal_applies_one_snapshot_per_tick():
    selecting = _make_public_state()
    step_one = _make_public_state()
    step_two = _make_public_state()
    step_one.board_rows = [
        [MatchCardPublic(number=10, danger=3, owner_seat=0)],
        [],
        [],
        [],
    ]
    step_two.board_rows = [
        [
            MatchCardPublic(number=10, danger=3, owner_seat=0),
            MatchCardPublic(number=20, danger=2, owner_seat=1),
        ],
        [],
        [],
        [],
    ]

    adapter = RemoteGameAdapter(my_seat=2)
    adapter.apply_public_state(selecting)
    adapter.begin_turn_reveal()
    adapter.queue_turn_reveal_step({"seat_index": 0, "card_number": 10}, step_one)
    adapter.queue_turn_reveal_step({"seat_index": 1, "card_number": 20}, step_two)
    adapter.finish_turn_reveal()

    scene = object.__new__(GameScene)
    scene._remote_adapter = adapter
    scene._remote_reveal_step_timer = 0.0
    scene._remote_reveal_step_duration = 0.4
    scene._remote_current_reveal_seat = None
    scene.message = ""
    scene.message_timer = 0.0
    scene.penalty_cards_animating = []
    scene.penalty_tweens = type(
        "FakeTweenGroup",
        (),
        {"update": lambda self, dt: True, "clear": lambda self: None},
    )()
    scene.commander = type(
        "FakeCommander", (), {"say_penalty_taken": lambda self: None}
    )()

    GameScene._advance_remote_reveal(scene, 0.0)
    assert adapter.get_public_state() is step_one
    assert scene._remote_current_reveal_seat == 0

    GameScene._advance_remote_reveal(scene, 0.1)
    assert adapter.get_public_state() is step_one

    GameScene._advance_remote_reveal(scene, 0.4)
    assert adapter.get_public_state() is step_two
    assert scene._remote_current_reveal_seat == 1


def test_waiting_for_other_players_after_remote_selection():
    adapter = RemoteGameAdapter(my_seat=2)
    adapter.apply_public_state(_make_public_state())
    adapter.apply_private_state(
        PrivatePlayerState(
            seat_index=2,
            hand=[MatchCardPublic(number=7, danger=1, owner_seat=2)],
            has_selected=True,
        )
    )

    scene = object.__new__(GameScene)
    scene._remote_adapter = adapter
    scene._remote_round_result = None
    scene._remote_selection_sent_pending = False
    scene._remote_current_reveal_seat = None
    scene._remote_reveal_step_timer = 0.0

    assert GameScene._is_waiting_for_other_players(scene) is True
    assert GameScene._can_interact_with_cards(scene) is False


def test_remote_selecting_phase_resets_timer_and_clears_waiting_state():
    adapter = RemoteGameAdapter(my_seat=2)
    adapter.apply_public_state(_make_public_state())
    adapter.notify_selecting_phase_started()

    scene = object.__new__(GameScene)
    scene._remote_adapter = adapter
    scene._remote_round_result = {"round_number": 1}
    scene._remote_round_result_timer = 5.0
    scene._remote_round_result_acknowledged = True
    scene._remote_selection_sent_pending = True
    scene._remote_current_reveal_seat = None
    scene._remote_reveal_step_timer = 0.0
    scene.turn_timer = 3.0
    scene._last_timeout_tick = 2
    scene.selected_card_index = 1
    scene._timeout_sfx = None

    changed = GameScene._update_remote_match_flow(scene, 0.5)

    assert changed is False
    assert scene.turn_timer < 30.0 and scene.turn_timer > 29.0
    assert scene._remote_round_result is None
    assert scene._remote_selection_sent_pending is False
    assert scene.selected_card_index is None


def test_remote_round_result_transitions_to_shared_result_scene(monkeypatch):
    adapter = RemoteGameAdapter(my_seat=2)
    adapter.apply_public_state(_make_public_state())
    adapter.queue_round_result({"round_number": 1, "timeout_seconds": 8})

    scene = object.__new__(GameScene)
    scene._remote_adapter = adapter
    scene._network_tick_callback = None
    scene._round_ready_callback = None
    scene._remote_round_result = None
    scene._remote_round_result_timer = 0.0
    scene._remote_round_result_acknowledged = False
    scene._remote_selection_sent_pending = False
    scene._remote_current_reveal_seat = None
    scene._remote_reveal_step_timer = 0.0
    scene.turn_timer = 30.0
    scene._last_timeout_tick = -1
    scene.selected_card_index = None
    scene._timeout_sfx = None

    captured: dict[str, object] = {}
    import fall_in.scenes.result_scene as result_scene_module

    class _FakeResultScene:
        pass

    monkeypatch.setattr(
        result_scene_module.ResultScene,
        "from_remote",
        classmethod(lambda cls, **kwargs: _FakeResultScene()),
    )
    monkeypatch.setattr(
        GameManager,
        "change_scene",
        lambda self, new_scene: captured.setdefault("scene", new_scene),
    )

    changed = GameScene._update_remote_match_flow(scene, 0.0)

    assert changed is True
    assert isinstance(captured["scene"], _FakeResultScene)


def test_start_remote_round_result_normalizes_json_keys():
    scene = object.__new__(GameScene)
    scene._remote_selection_sent_pending = True
    scene.selected_card_index = 2
    scene.message = "busy"
    scene.message_timer = 1.0

    GameScene._start_remote_round_result(
        scene,
        {
            "round_number": 2,
            "round_danger": {"0": 3, "2": 1},
            "total_scores": {"0": 14, "2": 9},
            "eliminated_seats": ["3"],
            "timeout_seconds": 8,
        },
    )

    assert scene._remote_round_result["round_danger"] == {0: 3, 2: 1}
    assert scene._remote_round_result["total_scores"] == {0: 14, 2: 9}
    assert scene._remote_round_result["eliminated_seats"] == [3]
    assert scene._remote_round_result_timer == 8
    assert scene._remote_selection_sent_pending is False
    assert scene.selected_card_index is None


def test_selection_timer_clamps_large_frame_hitch():
    scene = object.__new__(GameScene)
    scene.turn_timer = 30.0
    scene._timeout_sfx = None
    scene._last_timeout_tick = -1

    timed_out: list[bool] = []
    changed = GameScene._consume_selection_timer(
        scene,
        5.0,
        on_timeout=lambda: timed_out.append(True),
    )

    assert changed is False
    assert timed_out == []
    assert abs(scene.turn_timer - 29.75) < 1e-6


def test_remote_match_result_transitions_to_game_over_scene(monkeypatch):
    adapter = RemoteGameAdapter(my_seat=2)
    adapter.apply_public_state(_make_public_state())
    adapter.queue_match_result({"winner_seat": 0, "final_scores": {"0": 12, "2": 8}})

    scene = object.__new__(GameScene)
    scene._remote_adapter = adapter
    scene._remote_round_result = {"round_number": 1}
    scene._remote_round_result_timer = 5.0
    scene._remote_round_result_acknowledged = False
    scene._remote_selection_sent_pending = False
    scene._remote_current_reveal_seat = None
    scene._remote_reveal_step_timer = 0.0
    scene.turn_timer = 30.0
    scene._last_timeout_tick = -1
    scene.selected_card_index = None
    scene._timeout_sfx = None

    captured: dict[str, object] = {}
    import fall_in.scenes.game_over_scene as game_over_module

    class _FakeGameOverScene:
        def __init__(self, winner, players, round_number, multiplayer_reward=None):
            self.winner = winner
            self.players = players
            self.round_number = round_number
            self.multiplayer_reward = multiplayer_reward

    monkeypatch.setattr(game_over_module, "GameOverScene", _FakeGameOverScene)
    monkeypatch.setattr(
        GameManager,
        "change_scene",
        lambda self, new_scene: captured.setdefault("scene", new_scene),
    )

    changed = GameScene._update_remote_match_flow(scene, 0.0)

    assert changed is True
    assert isinstance(captured["scene"], _FakeGameOverScene)
    assert captured["scene"].winner.player_id == 0
    assert any(
        player.player_type == PlayerType.HUMAN for player in captured["scene"].players
    )


def test_other_player_panels_include_disconnect_status():
    public = _make_public_state()
    public.seats[3] = SeatIdentity(3, ControllerType.REMOTE, "GuestThree")

    adapter = RemoteGameAdapter(my_seat=2)
    adapter.apply_public_state(public)
    adapter.mark_seat_disconnected(0)
    adapter.mark_seat_bot_takeover(3)

    scene = object.__new__(GameScene)
    scene._remote_adapter = adapter

    panels = GameScene._get_other_player_panels(scene)
    by_seat = {panel["seat_index"]: panel for panel in panels}

    assert by_seat[0]["status"] == "재접속 중"
    assert by_seat[3]["status"] == "BOT 대체"


def test_confirm_remote_round_result_uses_callback_once():
    scene = object.__new__(GameScene)
    scene._remote_round_result = {"round_number": 1}
    scene._remote_round_result_acknowledged = False
    calls: list[str] = []
    scene._round_ready_callback = lambda: calls.append("ready")

    GameScene._confirm_remote_round_result(scene)
    GameScene._confirm_remote_round_result(scene)

    assert calls == ["ready"]
    assert scene._remote_round_result_acknowledged is True
