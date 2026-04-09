"""
Authoritative match engine tests.

Structure:
  TestMatchService      — unit tests (no WS, no HTTP)
  TestMatchDtoSafety    — DTO field-boundary tests
  TestMatchWebSocket    — WS integration tests for the full match flow
"""

import asyncio

import pytest
from fall_in.core.rules import RoundPhase
from fall_in.multiplayer.models import MatchCardPublic
from fall_in.net.serializers import (
    _PRIVATE_CARD_FIELDS,
    private_state_to_dict,
    public_state_to_dict,
)
from fastapi.testclient import TestClient

from app.database import get_db
from app.main import app
from app.models.match import RoundSummary
from app.models.room import Room, SeatControllerType
from app.repositories.match_repo import InMemoryMatchRepo
from app.repositories.room_repo import InMemoryRoomRepo
from app.services.match_service import MatchError, MatchService
from app.services.room_service import RoomService
from app.ws.endpoint import get_match_service, get_room_service
from app.ws.handler import _continue_after_round_settlement

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def room_service():
    return RoomService(InMemoryRoomRepo())


@pytest.fixture()
def match_service():
    return MatchService(InMemoryMatchRepo())


@pytest.fixture()
def client(db, room_service, match_service) -> TestClient:
    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_room_service] = lambda: room_service
    app.dependency_overrides[get_match_service] = lambda: match_service
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_full_room(room_service: RoomService, host_name: str = "Host") -> Room:
    """Create a room with seat 0 = REMOTE (host), seats 1-3 = BOT."""
    room = room_service.create_room(
        display_name=host_name,
        connection_id="conn-host",
        user_id="user-host",
    )
    # start_room fills remaining seats with bots and sets phase=STARTING.
    room = room_service.start_room(room.room_code, 0)
    return room


def _register(client: TestClient, email: str, nickname: str) -> str:
    resp = client.post(
        "/auth/register",
        json={
            "email": email,
            "password": "password123",
            "nickname": nickname,
        },
    )
    return resp.json()["access_token"]


def _ws_auth(ws, token: str) -> None:
    ws.send_json({"type": "WS_HELLO", "data": {}})
    ws.receive_json()  # WS_WELCOME
    ws.send_json({"type": "AUTH_LOGIN", "data": {"token": token}})
    ws.receive_json()  # AUTH_OK


def _consume_until(ws, target_type: str, max_msgs: int = 20) -> dict:
    """Drain messages until one with the given type is found."""
    for _ in range(max_msgs):
        msg = ws.receive_json()
        if msg["type"] == target_type:
            return msg
    raise AssertionError(f"Did not receive {target_type!r} in {max_msgs} messages")


def _play_remote_turn(ws) -> None:
    """Play one turn in a 1-human match until TURN_RESOLVED is reached."""
    _consume_until(ws, "PHASE_SELECTING")
    hand_msg = _consume_until(ws, "PRIVATE_HAND_STATE")
    card_number = hand_msg["data"]["hand"][0]["number"]
    ws.send_json({"type": "CARD_SELECT", "data": {"card_number": card_number}})
    _consume_until(ws, "PRIVATE_HAND_STATE")
    _consume_until(ws, "TURN_RESOLVED")


# ---------------------------------------------------------------------------
# TestMatchService — unit tests
# ---------------------------------------------------------------------------


class TestMatchService:
    def test_create_match_produces_four_seats(self, match_service, room_service):
        room = _make_full_room(room_service)
        match = match_service.create_match(room)
        assert len(match.seats) == 4

    def test_create_match_host_seat_is_remote(self, match_service, room_service):
        room = _make_full_room(room_service)
        match = match_service.create_match(room)
        assert match.seats[0].controller_type == SeatControllerType.REMOTE

    def test_create_match_bot_seats_are_bots(self, match_service, room_service):
        room = _make_full_room(room_service)
        match = match_service.create_match(room)
        for seat_idx in [1, 2, 3]:
            assert match.seats[seat_idx].controller_type == SeatControllerType.BOT
            assert match.seats[seat_idx].ai_controller is not None

    def test_create_match_bots_have_already_selected(self, match_service, room_service):
        room = _make_full_room(room_service)
        match = match_service.create_match(room)
        # Bots auto-select at round start.
        for seat_idx in [1, 2, 3]:
            assert match.seats[seat_idx].player.selected_card is not None

    def test_create_match_human_has_not_selected(self, match_service, room_service):
        room = _make_full_room(room_service)
        match = match_service.create_match(room)
        assert match.seats[0].player.selected_card is None

    def test_create_match_deals_ten_cards_per_seat(self, match_service, room_service):
        room = _make_full_room(room_service)
        match = match_service.create_match(room)
        for seat in match.seats.values():
            assert len(seat.player.hand) == 10

    def test_create_match_board_has_four_rows(self, match_service, room_service):
        room = _make_full_room(room_service)
        match = match_service.create_match(room)
        rules = match.rules
        assert len(rules.board.rows) == 4
        for row in rules.board.rows:
            assert len(row) == 1  # one starter card per row

    def test_create_match_stored_in_repo(self, match_service, room_service):
        room = _make_full_room(room_service)
        match = match_service.create_match(room)
        found = match_service.get_match(match.match_id)
        assert found is match

    def test_create_match_indexed_by_room_code(self, match_service, room_service):
        room = _make_full_room(room_service)
        match = match_service.create_match(room)
        found = match_service.get_match_by_room(room.room_code)
        assert found is match

    def test_submit_selection_records_card(self, match_service, room_service):
        room = _make_full_room(room_service)
        match = match_service.create_match(room)
        # Pick any card from human hand.
        card = match.seats[0].player.hand[0]
        match_service.submit_selection(match, 0, card.number)
        assert match.seats[0].player.selected_card is not None
        assert match.seats[0].player.selected_card.number == card.number

    def test_submit_selection_invalid_card_raises(self, match_service, room_service):
        room = _make_full_room(room_service)
        match = match_service.create_match(room)
        with pytest.raises(MatchError, match="not in"):
            match_service.submit_selection(match, 0, 9999)

    def test_submit_selection_bot_seat_raises(self, match_service, room_service):
        room = _make_full_room(room_service)
        match = match_service.create_match(room)
        card = match.seats[1].player.hand[0]
        with pytest.raises(MatchError, match="REMOTE"):
            match_service.submit_selection(match, 1, card.number)

    def test_submit_selection_twice_raises(self, match_service, room_service):
        room = _make_full_room(room_service)
        match = match_service.create_match(room)
        card = match.seats[0].player.hand[0]
        match_service.submit_selection(match, 0, card.number)
        with pytest.raises(MatchError, match="already selected"):
            match_service.submit_selection(match, 0, card.number)

    def test_not_all_selected_before_human_submits(self, match_service, room_service):
        room = _make_full_room(room_service)
        match = match_service.create_match(room)
        assert not match_service.all_selected(match)

    def test_all_selected_after_human_submits(self, match_service, room_service):
        room = _make_full_room(room_service)
        match = match_service.create_match(room)
        card = match.seats[0].player.hand[0]
        match_service.submit_selection(match, 0, card.number)
        assert match_service.all_selected(match)

    def test_resolve_turn_returns_four_steps(self, match_service, room_service):
        room = _make_full_room(room_service)
        match = match_service.create_match(room)
        card = match.seats[0].player.hand[0]
        match_service.submit_selection(match, 0, card.number)
        steps = match_service.resolve_turn(match)
        assert len(steps) == 4

    def test_resolve_turn_seat_indices_present(self, match_service, room_service):
        room = _make_full_room(room_service)
        match = match_service.create_match(room)
        card = match.seats[0].player.hand[0]
        match_service.submit_selection(match, 0, card.number)
        steps = match_service.resolve_turn(match)
        seats_seen = {s.seat_index for s in steps}
        assert seats_seen == {0, 1, 2, 3}

    def test_resolve_turn_cards_removed_from_hands(self, match_service, room_service):
        room = _make_full_room(room_service)
        match = match_service.create_match(room)
        card = match.seats[0].player.hand[0]
        match_service.submit_selection(match, 0, card.number)
        match_service.resolve_turn(match)
        # Each player's hand should now have 9 cards.
        for seat in match.seats.values():
            if not seat.player.is_eliminated:
                assert len(seat.player.hand) == 9

    def test_resolve_turn_updates_last_turn_steps(self, match_service, room_service):
        room = _make_full_room(room_service)
        match = match_service.create_match(room)
        card = match.seats[0].player.hand[0]
        match_service.submit_selection(match, 0, card.number)
        steps = match_service.resolve_turn(match)
        assert match.last_turn_steps is steps

    def test_finalize_round_tracks_scores(self, match_service, room_service):
        room = _make_full_room(room_service)
        match = match_service.create_match(room)
        rules = match.rules
        # Play all 10 turns to reach ROUND_END.
        for turn in range(10):
            card = match.seats[0].player.hand[0]
            match_service.submit_selection(match, 0, card.number)
            match_service.resolve_turn(match)
            # Re-select bots for the next turn only if round is not over yet.
            if not rules.is_round_over():
                for seat in match.seats.values():
                    if seat.ai_controller and not seat.player.is_eliminated:
                        seat.ai_controller.select_card(rules.board)
        assert rules.is_round_over()
        summary = match_service.finalize_round(match)
        assert summary.round_number == 1
        # All scores must be non-negative integers.
        for seat_idx in range(4):
            assert isinstance(summary.total_scores.get(seat_idx, 0), int)

    def test_delete_match_removes_from_repo(self, match_service, room_service):
        room = _make_full_room(room_service)
        match = match_service.create_match(room)
        match_service.delete_match(match.match_id)
        assert match_service.get_match(match.match_id) is None
        assert match_service.get_match_by_room(room.room_code) is None


# ---------------------------------------------------------------------------
# TestMatchDtoSafety — DTO boundary tests
# ---------------------------------------------------------------------------


class TestMatchDtoSafety:
    def test_public_state_no_private_card_fields(self, match_service, room_service):
        room = _make_full_room(room_service)
        match = match_service.create_match(room)
        pub = match_service.build_public_state(match)
        d = public_state_to_dict(pub)
        for row in d["board_rows"]:
            for card_dict in row:
                for field in _PRIVATE_CARD_FIELDS:
                    assert field not in card_dict, (
                        f"Private field {field!r} leaked into board row card"
                    )

    def test_private_state_no_private_card_fields(self, match_service, room_service):
        room = _make_full_room(room_service)
        match = match_service.create_match(room)
        priv = match_service.build_private_state(match, 0)
        d = private_state_to_dict(priv)
        for card_dict in d["hand"]:
            for field in _PRIVATE_CARD_FIELDS:
                assert field not in card_dict, f"Private field {field!r} leaked into hand card"

    def test_hand_card_owner_seat_is_viewer_seat(self, match_service, room_service):
        room = _make_full_room(room_service)
        match = match_service.create_match(room)
        for seat_idx in range(4):
            priv = match_service.build_private_state(match, seat_idx)
            for card in priv.hand:
                assert card.owner_seat == seat_idx, (
                    f"Hand card owner_seat should be {seat_idx}, got {card.owner_seat}"
                )

    def test_public_state_user_id_not_in_wire_dict(self, match_service, room_service):
        room = _make_full_room(room_service)
        match = match_service.create_match(room)
        pub = match_service.build_public_state(match)
        d = public_state_to_dict(pub)
        for seat_dict in d["seats"]:
            assert "user_id" not in seat_dict, "user_id must not appear in wire-level seat dict"

    def test_public_state_has_four_seats(self, match_service, room_service):
        room = _make_full_room(room_service)
        match = match_service.create_match(room)
        pub = match_service.build_public_state(match)
        assert len(pub.seats) == 4

    def test_public_state_phase_is_selecting_at_round_start(self, match_service, room_service):
        room = _make_full_room(room_service)
        match = match_service.create_match(room)
        pub = match_service.build_public_state(match)
        assert pub.phase == RoundPhase.SELECTING.name

    def test_private_state_has_selected_false_at_start(self, match_service, room_service):
        room = _make_full_room(room_service)
        match = match_service.create_match(room)
        priv = match_service.build_private_state(match, 0)
        assert priv.has_selected is False

    def test_private_state_has_selected_true_after_selection(self, match_service, room_service):
        room = _make_full_room(room_service)
        match = match_service.create_match(room)
        card = match.seats[0].player.hand[0]
        match_service.submit_selection(match, 0, card.number)
        priv = match_service.build_private_state(match, 0)
        assert priv.has_selected is True

    def test_board_row_owners_initialised_with_starters(self, match_service, room_service):
        room = _make_full_room(room_service)
        match = match_service.create_match(room)
        for owners in match.board_row_owners:
            assert owners == [-1], "Starter cards must have owner_seat -1"

    def test_board_cards_have_public_number_and_danger(self, match_service, room_service):
        room = _make_full_room(room_service)
        match = match_service.create_match(room)
        pub = match_service.build_public_state(match)
        for row in pub.board_rows:
            for card in row:
                assert isinstance(card, MatchCardPublic)
                assert 1 <= card.number <= 104
                assert 1 <= card.danger <= 7


# ---------------------------------------------------------------------------
# TestMatchWebSocket — integration tests via /ws
# ---------------------------------------------------------------------------


class TestMatchWebSocket:
    def test_room_start_broadcasts_match_start(self, client):
        token = _register(client, "ms_host@example.com", "MSHost")
        with client.websocket_connect("/ws") as ws:
            _ws_auth(ws, token)
            ws.send_json({"type": "ROOM_CREATE", "data": {}})
            _consume_until(ws, "ROOM_STATE")
            ws.send_json({"type": "ROOM_START", "data": {}})
            _consume_until(ws, "ROOM_STATE")  # STARTING lobby state
            msg = _consume_until(ws, "MATCH_START")
            assert msg["data"]["match_id"]

    def test_room_start_broadcasts_phase_selecting(self, client):
        token = _register(client, "ms_sel@example.com", "MSSel")
        with client.websocket_connect("/ws") as ws:
            _ws_auth(ws, token)
            ws.send_json({"type": "ROOM_CREATE", "data": {}})
            _consume_until(ws, "ROOM_STATE")
            ws.send_json({"type": "ROOM_START", "data": {}})
            _consume_until(ws, "MATCH_START")
            msg = _consume_until(ws, "PHASE_SELECTING")
            assert msg["data"]["round_number"] == 1
            assert msg["data"]["phase"] == "SELECTING"

    def test_room_start_unicasts_private_hand_state(self, client):
        token = _register(client, "ms_hand@example.com", "MSHand")
        with client.websocket_connect("/ws") as ws:
            _ws_auth(ws, token)
            ws.send_json({"type": "ROOM_CREATE", "data": {}})
            _consume_until(ws, "ROOM_STATE")
            ws.send_json({"type": "ROOM_START", "data": {}})
            _consume_until(ws, "MATCH_START")
            _consume_until(ws, "PHASE_SELECTING")
            msg = _consume_until(ws, "PRIVATE_HAND_STATE")
            assert len(msg["data"]["hand"]) == 10
            assert msg["data"]["has_selected"] is False

    def test_card_select_before_match_returns_error(self, client):
        token = _register(client, "ms_early@example.com", "MSEarly")
        with client.websocket_connect("/ws") as ws:
            _ws_auth(ws, token)
            ws.send_json({"type": "CARD_SELECT", "data": {"card_number": 1}})
            msg = ws.receive_json()
            assert msg["type"] == "ERROR"
            assert msg["data"]["code"] == "NOT_IN_MATCH"

    def test_card_select_invalid_card_returns_error(self, client):
        token = _register(client, "ms_inv@example.com", "MSInv")
        with client.websocket_connect("/ws") as ws:
            _ws_auth(ws, token)
            ws.send_json({"type": "ROOM_CREATE", "data": {}})
            _consume_until(ws, "ROOM_STATE")
            ws.send_json({"type": "ROOM_START", "data": {}})
            _consume_until(ws, "MATCH_START")
            _consume_until(ws, "PHASE_SELECTING")
            _consume_until(ws, "PRIVATE_HAND_STATE")
            ws.send_json({"type": "CARD_SELECT", "data": {"card_number": 9999}})
            msg = _consume_until(ws, "ERROR")
            assert msg["data"]["code"] == "MATCH_ERROR"

    def test_card_select_valid_card_acks_with_private_hand(self, client):
        token = _register(client, "ms_ack@example.com", "MSAck")
        with client.websocket_connect("/ws") as ws:
            _ws_auth(ws, token)
            ws.send_json({"type": "ROOM_CREATE", "data": {}})
            _consume_until(ws, "ROOM_STATE")
            ws.send_json({"type": "ROOM_START", "data": {}})
            _consume_until(ws, "MATCH_START")
            _consume_until(ws, "PHASE_SELECTING")
            private_msg = _consume_until(ws, "PRIVATE_HAND_STATE")

            card_number = private_msg["data"]["hand"][0]["number"]
            ws.send_json({"type": "CARD_SELECT", "data": {"card_number": card_number}})

            ack = _consume_until(ws, "PRIVATE_HAND_STATE")
            assert ack["data"]["has_selected"] is True

    def test_card_select_triggers_full_turn_resolution(self, client):
        """After human selects (all 3 bots already selected), full turn runs."""
        token = _register(client, "ms_turn@example.com", "MSTurn")
        with client.websocket_connect("/ws") as ws:
            _ws_auth(ws, token)
            ws.send_json({"type": "ROOM_CREATE", "data": {}})
            _consume_until(ws, "ROOM_STATE")
            ws.send_json({"type": "ROOM_START", "data": {}})
            _consume_until(ws, "MATCH_START")
            _consume_until(ws, "PHASE_SELECTING")
            private_msg = _consume_until(ws, "PRIVATE_HAND_STATE")

            card_number = private_msg["data"]["hand"][0]["number"]
            ws.send_json({"type": "CARD_SELECT", "data": {"card_number": card_number}})

            # Consume acknowledgement
            _consume_until(ws, "PRIVATE_HAND_STATE")
            # Turn reveal sequence
            _consume_until(ws, "TURN_REVEAL_START")

    def test_turn_resolution_broadcasts_four_reveal_steps(self, client):
        token = _register(client, "ms_steps@example.com", "MSSteps")
        with client.websocket_connect("/ws") as ws:
            _ws_auth(ws, token)
            ws.send_json({"type": "ROOM_CREATE", "data": {}})
            _consume_until(ws, "ROOM_STATE")
            ws.send_json({"type": "ROOM_START", "data": {}})
            _consume_until(ws, "MATCH_START")
            _consume_until(ws, "PHASE_SELECTING")
            private_msg = _consume_until(ws, "PRIVATE_HAND_STATE")

            card_number = private_msg["data"]["hand"][0]["number"]
            ws.send_json({"type": "CARD_SELECT", "data": {"card_number": card_number}})

            _consume_until(ws, "PRIVATE_HAND_STATE")  # ack
            _consume_until(ws, "TURN_REVEAL_START")

            # Expect 4 TURN_REVEAL_STEP messages (one per seat).
            steps = []
            for _ in range(4):
                msg = _consume_until(ws, "TURN_REVEAL_STEP")
                steps.append(msg)
            assert len(steps) == 4
            # Each step has required fields.
            for step in steps:
                d = step["data"]
                assert "seat_index" in d
                assert "card_number" in d
                assert "row_index" in d

    def test_turn_resolution_ends_with_turn_resolved(self, client):
        token = _register(client, "ms_resolved@example.com", "MSResolved")
        with client.websocket_connect("/ws") as ws:
            _ws_auth(ws, token)
            ws.send_json({"type": "ROOM_CREATE", "data": {}})
            _consume_until(ws, "ROOM_STATE")
            ws.send_json({"type": "ROOM_START", "data": {}})
            _consume_until(ws, "MATCH_START")
            _consume_until(ws, "PHASE_SELECTING")
            private_msg = _consume_until(ws, "PRIVATE_HAND_STATE")

            card_number = private_msg["data"]["hand"][0]["number"]
            ws.send_json({"type": "CARD_SELECT", "data": {"card_number": card_number}})
            _consume_until(ws, "PRIVATE_HAND_STATE")  # ack
            _consume_until(ws, "TURN_REVEAL_START")
            for _ in range(4):
                _consume_until(ws, "TURN_REVEAL_STEP")
            _consume_until(ws, "TURN_RESOLVED")

    def test_after_turn_resolved_returns_to_selecting(self, client):
        """After 1 turn, there are 9 more in round 1 — next message is PHASE_SELECTING."""
        token = _register(client, "ms_resel@example.com", "MSResel")
        with client.websocket_connect("/ws") as ws:
            _ws_auth(ws, token)
            ws.send_json({"type": "ROOM_CREATE", "data": {}})
            _consume_until(ws, "ROOM_STATE")
            ws.send_json({"type": "ROOM_START", "data": {}})
            _consume_until(ws, "MATCH_START")
            _consume_until(ws, "PHASE_SELECTING")
            private_msg = _consume_until(ws, "PRIVATE_HAND_STATE")

            card_number = private_msg["data"]["hand"][0]["number"]
            ws.send_json({"type": "CARD_SELECT", "data": {"card_number": card_number}})
            _consume_until(ws, "PRIVATE_HAND_STATE")  # ack
            _consume_until(ws, "TURN_REVEAL_START")
            for _ in range(4):
                _consume_until(ws, "TURN_REVEAL_STEP")
            _consume_until(ws, "TURN_RESOLVED")

            # After first turn there are 9 turns left — should re-enter SELECTING.
            msg = _consume_until(ws, "PHASE_SELECTING")
            assert msg["data"]["round_number"] == 1

    def test_card_select_without_missing_field_returns_error(self, client):
        token = _register(client, "ms_nofield@example.com", "MSNoField")
        with client.websocket_connect("/ws") as ws:
            _ws_auth(ws, token)
            ws.send_json({"type": "ROOM_CREATE", "data": {}})
            _consume_until(ws, "ROOM_STATE")
            ws.send_json({"type": "ROOM_START", "data": {}})
            _consume_until(ws, "MATCH_START")
            _consume_until(ws, "PHASE_SELECTING")
            _consume_until(ws, "PRIVATE_HAND_STATE")

            # Send CARD_SELECT without card_number.
            ws.send_json({"type": "CARD_SELECT", "data": {}})
            msg = _consume_until(ws, "ERROR")
            assert msg["data"]["code"] == "MISSING_CARD"

    def test_phase_selecting_board_has_four_rows(self, client):
        token = _register(client, "ms_board@example.com", "MSBoard")
        with client.websocket_connect("/ws") as ws:
            _ws_auth(ws, token)
            ws.send_json({"type": "ROOM_CREATE", "data": {}})
            _consume_until(ws, "ROOM_STATE")
            ws.send_json({"type": "ROOM_START", "data": {}})
            _consume_until(ws, "MATCH_START")
            phase_msg = _consume_until(ws, "PHASE_SELECTING")
            assert len(phase_msg["data"]["board_rows"]) == 4

    def test_phase_selecting_no_private_fields_in_board(self, client):
        token = _register(client, "ms_priv@example.com", "MSPriv")
        with client.websocket_connect("/ws") as ws:
            _ws_auth(ws, token)
            ws.send_json({"type": "ROOM_CREATE", "data": {}})
            _consume_until(ws, "ROOM_STATE")
            ws.send_json({"type": "ROOM_START", "data": {}})
            _consume_until(ws, "MATCH_START")
            phase_msg = _consume_until(ws, "PHASE_SELECTING")
            for row in phase_msg["data"]["board_rows"]:
                for card_dict in row:
                    for field in _PRIVATE_CARD_FIELDS:
                        assert field not in card_dict

    def test_round_result_waits_for_round_ready_before_next_round(self, client, match_service):
        token = _register(client, "ms_round_ready@example.com", "MSRoundReady")
        with client.websocket_connect("/ws") as ws:
            _ws_auth(ws, token)
            ws.send_json({"type": "ROOM_CREATE", "data": {}})
            room_msg = _consume_until(ws, "ROOM_STATE")
            room_code = room_msg["data"]["room_code"]
            ws.send_json({"type": "ROOM_START", "data": {}})
            _consume_until(ws, "MATCH_START")

            for _ in range(9):
                _play_remote_turn(ws)

            _consume_until(ws, "PHASE_SELECTING")
            hand_msg = _consume_until(ws, "PRIVATE_HAND_STATE")
            card_number = hand_msg["data"]["hand"][0]["number"]
            ws.send_json({"type": "CARD_SELECT", "data": {"card_number": card_number}})
            _consume_until(ws, "PRIVATE_HAND_STATE")
            _consume_until(ws, "TURN_RESOLVED")
            round_result = _consume_until(ws, "ROUND_RESULT")

            assert round_result["data"]["round_number"] == 1
            match = match_service.get_match_by_room(room_code)
            assert match is not None
            assert match_service.has_round_settlement_pending(match)

            ws.send_json({"type": "ROUND_READY", "data": {}})
            next_phase = _consume_until(ws, "PHASE_SELECTING")
            assert next_phase["data"]["round_number"] == 2
            assert not match_service.has_round_settlement_pending(match)


# ---------------------------------------------------------------------------
# Regression tests for code-review fixes
# ---------------------------------------------------------------------------


class TestRegressionFixes:
    """
    Targeted tests for the four issues found in the PR-04 code review.

    Fix 1 – non-host humans can submit CARD_SELECT (room_code lookup).
    Fix 2 – bots are re-selected after each turn (no stall on turn 2+).
    Fix 3 – multiplayer game-end uses survivor count, not players[0].
    Fix 4 – resolve_turn_stepwise produces incremental board snapshots.
    """

    # ------------------------------------------------------------------
    # Fix 1: non-host human CARD_SELECT
    # ------------------------------------------------------------------

    def test_non_host_human_can_submit_card_select(self, client):
        """
        A player who joined a room but did NOT start it (no match_id on
        their session) must still be able to submit CARD_SELECT.
        """
        token_host = _register(client, "fix1_host@example.com", "Fix1Host")
        token_guest = _register(client, "fix1_guest@example.com", "Fix1Guest")

        with client.websocket_connect("/ws") as ws_host:
            with client.websocket_connect("/ws") as ws_guest:
                _ws_auth(ws_host, token_host)
                _ws_auth(ws_guest, token_guest)

                # Host creates room; guest joins before start.
                ws_host.send_json({"type": "ROOM_CREATE", "data": {}})
                room_msg = _consume_until(ws_host, "ROOM_STATE")
                room_code = room_msg["data"]["room_code"]

                ws_guest.send_json({"type": "ROOM_JOIN", "data": {"room_code": room_code}})
                _consume_until(ws_guest, "ROOM_STATE")  # join broadcast

                # Guest must be ready before host can start.
                ws_guest.send_json({"type": "READY_SET", "data": {"is_ready": True}})
                _consume_until(ws_guest, "ROOM_STATE")  # ready broadcast

                # Host starts — fills seats 2-3 with bots.
                ws_host.send_json({"type": "ROOM_START", "data": {}})
                _consume_until(ws_guest, "MATCH_START")
                _consume_until(ws_guest, "PHASE_SELECTING")
                hand_msg = _consume_until(ws_guest, "PRIVATE_HAND_STATE")

                card_number = hand_msg["data"]["hand"][0]["number"]
                ws_guest.send_json(
                    {
                        "type": "CARD_SELECT",
                        "data": {"card_number": card_number},
                    }
                )
                # Must NOT return NOT_IN_MATCH; must ack with updated hand state.
                ack = _consume_until(ws_guest, "PRIVATE_HAND_STATE")
                assert ack["data"]["has_selected"] is True

    # ------------------------------------------------------------------
    # Fix 2: bot reselection after each turn
    # ------------------------------------------------------------------

    def test_reselect_bots_restores_bot_selections(self, match_service, room_service):
        """After resolve_turn clears selected_card, reselect_bots gives bots new cards."""
        room = _make_full_room(room_service)
        match = match_service.create_match(room)
        card = match.seats[0].player.hand[0]
        match_service.submit_selection(match, 0, card.number)
        match_service.resolve_turn(match)
        # Bots' selected_card is now None after turn resolution.
        for seat_idx in [1, 2, 3]:
            assert match.seats[seat_idx].player.selected_card is None
        # After reselect_bots they should have a card chosen again.
        match_service.reselect_bots(match)
        for seat_idx in [1, 2, 3]:
            assert match.seats[seat_idx].player.selected_card is not None

    def test_second_turn_can_resolve(self, client):
        """
        Two consecutive turns must both resolve without stalling.
        (Regression: bots were not re-selected before turn 2.)
        """
        token = _register(client, "fix2_t2@example.com", "Fix2T2")
        with client.websocket_connect("/ws") as ws:
            _ws_auth(ws, token)
            ws.send_json({"type": "ROOM_CREATE", "data": {}})
            _consume_until(ws, "ROOM_STATE")
            ws.send_json({"type": "ROOM_START", "data": {}})
            _consume_until(ws, "MATCH_START")

            # --- Turn 1 ---
            _consume_until(ws, "PHASE_SELECTING")
            hand_msg = _consume_until(ws, "PRIVATE_HAND_STATE")
            card_number = hand_msg["data"]["hand"][0]["number"]
            ws.send_json({"type": "CARD_SELECT", "data": {"card_number": card_number}})
            _consume_until(ws, "TURN_RESOLVED")

            # --- Turn 2 ---
            # Server must have re-selected bots before broadcasting PHASE_SELECTING.
            phase2 = _consume_until(ws, "PHASE_SELECTING")
            assert phase2["data"]["round_number"] == 1  # still round 1

            hand2_msg = _consume_until(ws, "PRIVATE_HAND_STATE")
            card2_number = hand2_msg["data"]["hand"][0]["number"]
            ws.send_json({"type": "CARD_SELECT", "data": {"card_number": card2_number}})
            # Must trigger another turn — not stall waiting for bots.
            _consume_until(ws, "TURN_RESOLVED")

    # ------------------------------------------------------------------
    # Fix 3: multiplayer game-end logic
    # ------------------------------------------------------------------

    def test_multiplayer_game_does_not_end_when_seat0_eliminated(self, match_service, room_service):
        """
        In multiplayer mode (human_seat=None), eliminating seat 0 alone must
        NOT end the game while other players remain active.
        """
        room = _make_full_room(room_service)
        match = match_service.create_match(room)
        rules = match.rules

        # Forcibly eliminate seat 0 without touching the others.
        seat0_player = match.seats[0].player
        seat0_player.penalty_score = 200
        seat0_player.check_elimination(threshold=66)
        assert seat0_player.is_eliminated

        # Directly invoke the game-end check.
        rules._check_game_end()

        # Three other players are still active → game must NOT be over.
        assert not rules.game_over

    def test_multiplayer_game_ends_when_one_survivor_remains(self, match_service, room_service):
        """Game ends when only 1 active player survives (multiplayer mode)."""
        room = _make_full_room(room_service)
        match = match_service.create_match(room)
        rules = match.rules

        # Eliminate seats 0, 1, 2 — leave only seat 3 active.
        for seat_idx in [0, 1, 2]:
            p = match.seats[seat_idx].player
            p.penalty_score = 200
            p.check_elimination(threshold=66)

        rules._check_game_end()

        assert rules.game_over
        assert rules.winner is match.seats[3].player

    # ------------------------------------------------------------------
    # Fix 4: stepwise board snapshots
    # ------------------------------------------------------------------

    def test_resolve_turn_stepwise_returns_four_entries(self, match_service, room_service):
        room = _make_full_room(room_service)
        match = match_service.create_match(room)
        card = match.seats[0].player.hand[0]
        match_service.submit_selection(match, 0, card.number)
        results = match_service.resolve_turn_stepwise(match)
        assert len(results) == 4

    def test_resolve_turn_stepwise_snapshots_grow_incrementally(self, match_service, room_service):
        """Each snapshot's played_cards_this_turn must be one longer than the previous."""
        room = _make_full_room(room_service)
        match = match_service.create_match(room)
        card = match.seats[0].player.hand[0]
        match_service.submit_selection(match, 0, card.number)
        results = match_service.resolve_turn_stepwise(match)
        for idx, (step, snapshot) in enumerate(results):
            assert len(snapshot.played_cards_this_turn) == idx + 1, (
                f"Step {idx}: expected {idx + 1} played cards, "
                f"got {len(snapshot.played_cards_this_turn)}"
            )

    def test_resolve_turn_stepwise_last_step_matches_resolve_turn(
        self, match_service, room_service
    ):
        """The final last_turn_steps after stepwise resolution equals the full step list."""
        room = _make_full_room(room_service)
        match = match_service.create_match(room)
        card = match.seats[0].player.hand[0]
        match_service.submit_selection(match, 0, card.number)
        results = match_service.resolve_turn_stepwise(match)
        steps_from_stepwise = [step for step, _ in results]
        assert [s.seat_index for s in match.last_turn_steps] == [
            s.seat_index for s in steps_from_stepwise
        ]


class TestRoundSettlementFlow:
    def test_continue_after_round_settlement_broadcasts_match_result_for_game_over(
        self, match_service, room_service
    ):
        room = _make_full_room(room_service)
        match = match_service.create_match(room)
        summary = RoundSummary(
            round_number=3,
            round_danger={0: 2, 1: 0, 2: 0, 3: 0},
            total_scores={0: 12, 1: 40, 2: 66, 3: 66},
            eliminated_seats=[2, 3],
            game_over=True,
            winner_seat=0,
        )
        match_service.begin_round_settlement(match, summary)

        class _FakeManager:
            def __init__(self) -> None:
                self.broadcasts: list[tuple[str, dict]] = []

            async def broadcast_to_room(self, room_code: str, payload: dict) -> None:
                self.broadcasts.append((room_code, payload))

        class _FakePresence:
            def __init__(self) -> None:
                self.cancelled: list[str] = []
                self.revoked: list[str] = []

            def cancel_round_settlement_timeout(self, match_id: str) -> None:
                self.cancelled.append(match_id)

            def revoke_match_tokens(self, match_id: str) -> None:
                self.revoked.append(match_id)

        manager = _FakeManager()
        presence = _FakePresence()
        fake_room_service = object()

        asyncio.run(
            _continue_after_round_settlement(
                room.room_code,
                match,
                manager,
                match_service,
                fake_room_service,
                presence,
            )
        )

        assert manager.broadcasts == [
            (
                room.room_code,
                {
                    "type": "MATCH_RESULT",
                    "data": {
                        "match_id": match.match_id,
                        "winner_seat": 0,
                        "final_scores": {0: 12, 1: 40, 2: 66, 3: 66},
                        "rewards": {0: 130, 1: 45, 2: 45, 3: 45},
                    },
                },
            )
        ]
        assert presence.cancelled == [match.match_id]
        assert presence.revoked == [match.match_id]
        assert match_service.get_match(match.match_id) is None

    def test_rewards_use_per_seat_elimination_round(self, match_service, room_service):
        """Players eliminated in different rounds receive different rewards."""
        room = _make_full_room(room_service)
        match = match_service.create_match(room)

        # Simulate seat 3 eliminated in round 2, seats 1 & 2 in round 4.
        match.seat_eliminated_round[3] = 2
        match.seat_eliminated_round[1] = 4
        match.seat_eliminated_round[2] = 4

        summary = RoundSummary(
            round_number=4,
            round_danger={0: 5, 1: 20, 2: 20, 3: 0},
            total_scores={0: 30, 1: 66, 2: 70, 3: 80},
            eliminated_seats=[1, 2, 3],
            game_over=True,
            winner_seat=0,
        )

        from app.ws.handler import _calculate_match_rewards

        rewards = _calculate_match_rewards(match, summary)

        # Winner (seat 0): 100 + 4*10 = 140
        assert rewards[0] == 140
        # Losers eliminated in round 4 (seats 1, 2): 30 + 4*5 = 50
        assert rewards[1] == 50
        assert rewards[2] == 50
        # Loser eliminated in round 2 (seat 3): 30 + 2*5 = 40
        assert rewards[3] == 40
