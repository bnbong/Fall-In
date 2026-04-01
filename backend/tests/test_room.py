"""
Room lobby and WebSocket session tests.

Structure:
  TestRoomService     — unit tests for business logic (no WS, no HTTP)
  TestRoomWebSocket   — integration tests via the /ws endpoint

WebSocket integration tests use a single client at a time.  Multi-client
broadcast behaviour is covered by TestRoomService unit tests, keeping the
WS tests simple and free of threading.

The local `client` fixture overrides the conftest.py one to also inject a
fresh RoomService (via get_room_service dependency override) so each test
starts with an empty in-memory room store.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.database import get_db
from app.main import app
from app.models.room import RoomPhase, SeatControllerType
from app.repositories.room_repo import InMemoryRoomRepo
from app.services.room_service import RoomError, RoomService
from app.ws.endpoint import get_room_service


# ---------------------------------------------------------------------------
# Fixtures — local overrides of conftest.py
# ---------------------------------------------------------------------------

@pytest.fixture()
def room_service():
    """Fresh room service for each test."""
    return RoomService(InMemoryRoomRepo())


@pytest.fixture()
def client(db, room_service) -> TestClient:
    """TestClient that overrides both get_db and get_room_service."""

    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_room_service] = lambda: room_service
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _register(client: TestClient, email: str, nickname: str) -> str:
    resp = client.post("/auth/register", json={
        "email": email,
        "password": "password123",
        "nickname": nickname,
    })
    assert resp.status_code == 201, resp.json()
    return resp.json()["access_token"]


def _guest(client: TestClient, nickname: str = "GuestPlayer") -> str:
    resp = client.post("/auth/guest", json={"nickname": nickname})
    assert resp.status_code == 200, resp.json()
    return resp.json()["access_token"]


def _ws_auth(ws, token: str) -> None:
    """Send HELLO+AUTH and consume the two response messages."""
    ws.send_json({"type": "WS_HELLO"})
    welcome = ws.receive_json()
    assert welcome["type"] == "WS_WELCOME"

    ws.send_json({"type": "AUTH_LOGIN", "data": {"token": token}})
    auth_ok = ws.receive_json()
    assert auth_ok["type"] == "AUTH_OK"


# ===========================================================================
# Unit tests — RoomService
# ===========================================================================

class TestRoomService:
    def test_create_room_returns_six_char_code(self, room_service):
        room = room_service.create_room("Alice", "conn-1")
        assert len(room.room_code) == 6
        assert room.room_code.isupper() or room.room_code.isalnum()

    def test_create_room_host_at_seat_0(self, room_service):
        room = room_service.create_room("Alice", "conn-1")
        assert room.host_seat_index == 0
        assert 0 in room.participants
        assert room.participants[0].display_name == "Alice"
        assert room.participants[0].controller_type == SeatControllerType.REMOTE

    def test_create_room_initial_phase_is_waiting(self, room_service):
        room = room_service.create_room("Alice", "conn-1")
        assert room.phase == RoomPhase.WAITING

    def test_join_room_assigns_next_seat(self, room_service):
        room = room_service.create_room("Alice", "conn-1")
        updated = room_service.join_room(room.room_code, "Bob", "conn-2")
        assert 1 in updated.participants
        assert updated.participants[1].display_name == "Bob"

    def test_join_room_returns_two_participants(self, room_service):
        room = room_service.create_room("Alice", "conn-1")
        updated = room_service.join_room(room.room_code, "Bob", "conn-2")
        assert len(updated.participants) == 2

    def test_join_nonexistent_room_raises(self, room_service):
        with pytest.raises(RoomError, match="not found"):
            room_service.join_room("XXXXXX", "Bob", "conn-2")

    def test_join_full_room_raises(self, room_service):
        room = room_service.create_room("A", "c0")
        room_service.join_room(room.room_code, "B", "c1")
        room_service.join_room(room.room_code, "C", "c2")
        room_service.join_room(room.room_code, "D", "c3")
        with pytest.raises(RoomError, match="full"):
            room_service.join_room(room.room_code, "E", "c4")

    def test_join_starting_room_raises(self, room_service):
        room = room_service.create_room("Alice", "conn-1")
        room_service.start_room(room.room_code, 0)
        with pytest.raises(RoomError, match="not accepting"):
            room_service.join_room(room.room_code, "Late", "conn-late")

    def test_leave_room_removes_participant(self, room_service):
        room = room_service.create_room("Alice", "conn-1")
        room_service.join_room(room.room_code, "Bob", "conn-2")
        updated = room_service.leave_room(room.room_code, 1)
        assert 1 not in updated.participants
        assert len(updated.participants) == 1

    def test_leave_room_last_player_returns_none(self, room_service):
        room = room_service.create_room("Alice", "conn-1")
        result = room_service.leave_room(room.room_code, 0)
        assert result is None

    def test_leave_room_host_reassigns_to_lowest_seat(self, room_service):
        room = room_service.create_room("Alice", "conn-1")  # seat 0 = host
        room_service.join_room(room.room_code, "Bob", "conn-2")    # seat 1
        updated = room_service.leave_room(room.room_code, 0)       # host leaves
        assert updated.host_seat_index == 1

    def test_set_ready_updates_flag(self, room_service):
        room = room_service.create_room("Alice", "conn-1")
        updated = room_service.set_ready(room.room_code, 0, True)
        assert updated.participants[0].is_ready is True

    def test_set_ready_nonexistent_room_raises(self, room_service):
        with pytest.raises(RoomError, match="not found"):
            room_service.set_ready("XXXXXX", 0, True)

    def test_start_fills_missing_seats_with_bots(self, room_service):
        room = room_service.create_room("Alice", "conn-1")
        started = room_service.start_room(room.room_code, 0)
        assert len(started.participants) == 4
        bots = [p for p in started.participants.values()
                if p.controller_type == SeatControllerType.BOT]
        assert len(bots) == 3

    def test_start_bots_are_marked_ready(self, room_service):
        room = room_service.create_room("Alice", "conn-1")
        started = room_service.start_room(room.room_code, 0)
        for p in started.participants.values():
            if p.controller_type == SeatControllerType.BOT:
                assert p.is_ready is True

    def test_start_bots_have_no_connection_id(self, room_service):
        room = room_service.create_room("Alice", "conn-1")
        started = room_service.start_room(room.room_code, 0)
        for p in started.participants.values():
            if p.controller_type == SeatControllerType.BOT:
                assert p.connection_id is None
                assert p.user_id is None

    def test_start_changes_phase_to_starting(self, room_service):
        room = room_service.create_room("Alice", "conn-1")
        started = room_service.start_room(room.room_code, 0)
        assert started.phase == RoomPhase.STARTING

    def test_start_non_host_raises(self, room_service):
        room = room_service.create_room("Alice", "conn-1")
        room_service.join_room(room.room_code, "Bob", "conn-2")
        with pytest.raises(RoomError, match="host"):
            room_service.start_room(room.room_code, 1)

    def test_start_already_starting_raises(self, room_service):
        room = room_service.create_room("Alice", "conn-1")
        room_service.start_room(room.room_code, 0)
        with pytest.raises(RoomError, match="already"):
            room_service.start_room(room.room_code, 0)

    def test_two_rooms_have_distinct_codes(self, room_service):
        room_a = room_service.create_room("Alice", "conn-1")
        room_b = room_service.create_room("Bob", "conn-2")
        assert room_a.room_code != room_b.room_code

    def test_room_to_dict_structure(self, room_service):
        room = room_service.create_room("Alice", "conn-1")
        d = room.to_dict()
        assert "room_code" in d
        assert "phase" in d
        assert "host_seat_index" in d
        assert "participants" in d
        assert isinstance(d["participants"], list)
        assert d["participants"][0]["seat_index"] == 0
        assert d["participants"][0]["controller_type"] == SeatControllerType.REMOTE

    def test_room_to_dict_excludes_connection_id(self, room_service):
        """connection_id must never leak to the wire."""
        room = room_service.create_room("Alice", "conn-secret")
        d = room.to_dict()
        for p in d["participants"]:
            assert "connection_id" not in p


# ===========================================================================
# Integration tests — WebSocket endpoint
# ===========================================================================

class TestRoomWebSocket:
    def test_ws_hello_welcome(self, client):
        with client.websocket_connect("/ws") as ws:
            ws.send_json({"type": "WS_HELLO"})
            msg = ws.receive_json()
        assert msg["type"] == "WS_WELCOME"
        assert "connection_id" in msg["data"]

    def test_ws_welcome_connection_id_is_string(self, client):
        with client.websocket_connect("/ws") as ws:
            ws.send_json({"type": "WS_HELLO"})
            msg = ws.receive_json()
        assert isinstance(msg["data"]["connection_id"], str)
        assert len(msg["data"]["connection_id"]) > 0

    def test_ws_ping_pong(self, client):
        with client.websocket_connect("/ws") as ws:
            ws.send_json({"type": "PING"})
            msg = ws.receive_json()
        assert msg["type"] == "PONG"

    def test_ws_unknown_message_returns_error(self, client):
        with client.websocket_connect("/ws") as ws:
            ws.send_json({"type": "DOES_NOT_EXIST"})
            msg = ws.receive_json()
        assert msg["type"] == "ERROR"
        assert msg["data"]["code"] == "UNKNOWN_MESSAGE"

    def test_ws_auth_registered_user(self, client):
        token = _register(client, "ws_reg@example.com", "WsReg")
        with client.websocket_connect("/ws") as ws:
            ws.send_json({"type": "WS_HELLO"})
            ws.receive_json()  # WELCOME
            ws.send_json({"type": "AUTH_LOGIN", "data": {"token": token}})
            msg = ws.receive_json()
        assert msg["type"] == "AUTH_OK"
        assert msg["data"]["account_type"] == "registered"
        assert msg["data"]["display_name"] == "WsReg"

    def test_ws_auth_guest_user(self, client):
        token = _guest(client, "WsGuest")
        with client.websocket_connect("/ws") as ws:
            ws.send_json({"type": "WS_HELLO"})
            ws.receive_json()
            ws.send_json({"type": "AUTH_GUEST", "data": {"token": token}})
            msg = ws.receive_json()
        assert msg["type"] == "AUTH_OK"
        assert msg["data"]["account_type"] == "guest"
        assert msg["data"]["display_name"] == "WsGuest"

    def test_ws_auth_invalid_token_returns_error(self, client):
        with client.websocket_connect("/ws") as ws:
            ws.send_json({"type": "AUTH_LOGIN", "data": {"token": "not.a.token"}})
            msg = ws.receive_json()
        assert msg["type"] == "ERROR"
        assert msg["data"]["code"] == "INVALID_TOKEN"

    def test_ws_auth_missing_token_returns_error(self, client):
        with client.websocket_connect("/ws") as ws:
            ws.send_json({"type": "AUTH_LOGIN", "data": {}})
            msg = ws.receive_json()
        assert msg["type"] == "ERROR"
        assert msg["data"]["code"] == "MISSING_TOKEN"

    def test_ws_room_create_returns_room_state(self, client):
        token = _guest(client, "Creator")
        with client.websocket_connect("/ws") as ws:
            _ws_auth(ws, token)
            ws.send_json({"type": "ROOM_CREATE"})
            msg = ws.receive_json()
        assert msg["type"] == "ROOM_STATE"
        data = msg["data"]
        assert len(data["room_code"]) == 6
        assert data["phase"] == RoomPhase.WAITING
        assert data["host_seat_index"] == 0
        assert len(data["participants"]) == 1
        assert data["participants"][0]["controller_type"] == SeatControllerType.REMOTE

    def test_ws_room_create_without_auth_rejected(self, client):
        with client.websocket_connect("/ws") as ws:
            ws.send_json({"type": "ROOM_CREATE"})
            msg = ws.receive_json()
        assert msg["type"] == "ERROR"
        assert msg["data"]["code"] == "NOT_AUTHENTICATED"

    def test_ws_room_join_success(self, client, room_service):
        """Use room_service fixture to pre-create a room, then join via WS."""
        existing = room_service.create_room("Host", "pre-conn")
        room_code = existing.room_code

        token = _guest(client, "Joiner")
        with client.websocket_connect("/ws") as ws:
            _ws_auth(ws, token)
            ws.send_json({"type": "ROOM_JOIN", "data": {"room_code": room_code}})
            msg = ws.receive_json()
        assert msg["type"] == "ROOM_STATE"
        assert len(msg["data"]["participants"]) == 2

    def test_ws_room_join_nonexistent_returns_error(self, client):
        token = _guest(client, "Orphan")
        with client.websocket_connect("/ws") as ws:
            _ws_auth(ws, token)
            ws.send_json({"type": "ROOM_JOIN", "data": {"room_code": "XXXXXX"}})
            msg = ws.receive_json()
        assert msg["type"] == "ERROR"
        assert msg["data"]["code"] == "ROOM_ERROR"
        assert "not found" in msg["data"]["message"].lower()

    def test_ws_room_join_missing_code_returns_error(self, client):
        token = _guest(client, "NoCode")
        with client.websocket_connect("/ws") as ws:
            _ws_auth(ws, token)
            ws.send_json({"type": "ROOM_JOIN", "data": {}})
            msg = ws.receive_json()
        assert msg["type"] == "ERROR"
        assert msg["data"]["code"] == "MISSING_ROOM_CODE"

    def test_ws_ready_set_true(self, client):
        token = _guest(client, "ReadyPlayer")
        with client.websocket_connect("/ws") as ws:
            _ws_auth(ws, token)
            ws.send_json({"type": "ROOM_CREATE"})
            ws.receive_json()  # ROOM_STATE from create
            ws.send_json({"type": "READY_SET", "data": {"is_ready": True}})
            msg = ws.receive_json()
        assert msg["type"] == "ROOM_STATE"
        assert msg["data"]["participants"][0]["is_ready"] is True

    def test_ws_ready_set_false(self, client):
        token = _guest(client, "UnreadyPlayer")
        with client.websocket_connect("/ws") as ws:
            _ws_auth(ws, token)
            ws.send_json({"type": "ROOM_CREATE"})
            ws.receive_json()
            ws.send_json({"type": "READY_SET", "data": {"is_ready": True}})
            ws.receive_json()
            ws.send_json({"type": "READY_SET", "data": {"is_ready": False}})
            msg = ws.receive_json()
        assert msg["data"]["participants"][0]["is_ready"] is False

    def test_ws_ready_without_room_returns_error(self, client):
        token = _guest(client, "NoRoom")
        with client.websocket_connect("/ws") as ws:
            _ws_auth(ws, token)
            ws.send_json({"type": "READY_SET", "data": {"is_ready": True}})
            msg = ws.receive_json()
        assert msg["type"] == "ERROR"
        assert msg["data"]["code"] == "NOT_IN_ROOM"

    def test_ws_room_start_fills_ai_bots(self, client):
        """Single human starts → 3 bots fill empty seats."""
        token = _guest(client, "LoneHost")
        with client.websocket_connect("/ws") as ws:
            _ws_auth(ws, token)
            ws.send_json({"type": "ROOM_CREATE"})
            ws.receive_json()  # ROOM_STATE (1 human)
            ws.send_json({"type": "ROOM_START"})
            msg = ws.receive_json()
        assert msg["type"] == "ROOM_STATE"
        data = msg["data"]
        assert data["phase"] == RoomPhase.STARTING
        assert len(data["participants"]) == 4
        bots = [p for p in data["participants"] if p["controller_type"] == SeatControllerType.BOT]
        assert len(bots) == 3

    def test_ws_room_start_bots_marked_correctly(self, client):
        token = _guest(client, "HostOnly")
        with client.websocket_connect("/ws") as ws:
            _ws_auth(ws, token)
            ws.send_json({"type": "ROOM_CREATE"})
            ws.receive_json()
            ws.send_json({"type": "ROOM_START"})
            msg = ws.receive_json()
        for p in msg["data"]["participants"]:
            if p["controller_type"] == SeatControllerType.BOT:
                assert p["is_ready"] is True
                assert p["user_id"] is None

    def test_ws_room_start_without_room_returns_error(self, client):
        token = _guest(client, "StartNoRoom")
        with client.websocket_connect("/ws") as ws:
            _ws_auth(ws, token)
            ws.send_json({"type": "ROOM_START"})
            msg = ws.receive_json()
        assert msg["type"] == "ERROR"
        assert msg["data"]["code"] == "NOT_IN_ROOM"

    def test_ws_room_start_non_host_rejected(self, client, room_service):
        """Non-host member cannot start the room."""
        room_service.create_room("Host", "host-conn")
        # The room code won't be accessible here directly because the host
        # connected via a pre-created room fixture — use the repo.
        existing = room_service.create_room("Host2", "host-conn-2")
        room_code = existing.room_code

        token = _guest(client, "NonHost")
        with client.websocket_connect("/ws") as ws:
            _ws_auth(ws, token)
            ws.send_json({"type": "ROOM_JOIN", "data": {"room_code": room_code}})
            ws.receive_json()  # ROOM_STATE (NonHost at seat 1)
            ws.send_json({"type": "ROOM_START"})
            msg = ws.receive_json()
        assert msg["type"] == "ERROR"
        assert msg["data"]["code"] == "ROOM_ERROR"
        assert "host" in msg["data"]["message"].lower()

    def test_ws_room_leave_without_room_returns_error(self, client):
        token = _guest(client, "LeaveNoRoom")
        with client.websocket_connect("/ws") as ws:
            _ws_auth(ws, token)
            ws.send_json({"type": "ROOM_LEAVE"})
            msg = ws.receive_json()
        assert msg["type"] == "ERROR"
        assert msg["data"]["code"] == "NOT_IN_ROOM"

    def test_ws_room_leave_success(self, client):
        token = _guest(client, "Leaver")
        with client.websocket_connect("/ws") as ws:
            _ws_auth(ws, token)
            ws.send_json({"type": "ROOM_CREATE"})
            ws.receive_json()  # ROOM_STATE
            ws.send_json({"type": "ROOM_LEAVE"})
            # Room destroyed (last member left) — no broadcast expected.
            # Verify we can still send PING without error.
            ws.send_json({"type": "PING"})
            msg = ws.receive_json()
        assert msg["type"] == "PONG"

    def test_ws_already_in_room_create_rejected(self, client):
        token = _guest(client, "DoubleCreate")
        with client.websocket_connect("/ws") as ws:
            _ws_auth(ws, token)
            ws.send_json({"type": "ROOM_CREATE"})
            ws.receive_json()  # ROOM_STATE
            ws.send_json({"type": "ROOM_CREATE"})
            msg = ws.receive_json()
        assert msg["type"] == "ERROR"
        assert msg["data"]["code"] == "ALREADY_IN_ROOM"

    def test_ws_already_in_room_join_rejected(self, client, room_service):
        existing = room_service.create_room("OtherHost", "other-conn")
        token = _guest(client, "DoubleJoin")
        with client.websocket_connect("/ws") as ws:
            _ws_auth(ws, token)
            ws.send_json({"type": "ROOM_CREATE"})
            ws.receive_json()
            ws.send_json({"type": "ROOM_JOIN", "data": {"room_code": existing.room_code}})
            msg = ws.receive_json()
        assert msg["type"] == "ERROR"
        assert msg["data"]["code"] == "ALREADY_IN_ROOM"
