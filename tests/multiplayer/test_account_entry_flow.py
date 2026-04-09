from __future__ import annotations

from fall_in.core.game_manager import GameManager
from fall_in.scenes.account_gate_scene import AccountGateScene
from fall_in.scenes.intro_cutscene_scene import IntroCutsceneScene


def test_intro_transitions_to_account_gate(monkeypatch):
    scene = object.__new__(IntroCutsceneScene)
    captured: dict[str, object] = {}

    monkeypatch.setattr(
        GameManager,
        "change_scene",
        lambda self, new_scene: captured.setdefault("scene", new_scene),
    )

    IntroCutsceneScene._transition_to_title(scene)

    assert isinstance(captured["scene"], AccountGateScene)
