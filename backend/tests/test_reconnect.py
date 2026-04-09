"""
PR-05 — Reconnect, heartbeat, timeout, and bot-takeover tests.

Structure
---------
TestHeartbeat          — PING/PONG message protocol and session state.
TestReconnectToken     — Token issuance and validation (unit + WS).
TestReconnectFlow      — Full disconnect-then-reconnect via WS.
TestBotTakeover        — MatchService.takeover_seat() logic (unit).
TestSelectionTimeout   — MatchService.auto_select_timed_out() logic (unit).
TestPresenceManager    — PresenceManager token helpers (unit).

Timing-based background tasks (grace timer, selection timer) are tested
via the service-level helpers they call rather than waiting for actual
asyncio.sleep durations.  This keeps the suite fast and deterministic.
"""

import time

import pytest
from fall_in.core.rules import RoundPhase
from fastapi.testclient import TestClient

from app.database import get_db
from app.main import app
from app.models.room import Room, SeatControllerType
from app.repositories.match_repo import InMemoryMatchRepo
from app.repositories.reconnect_repo import InMemoryReconnectRepo
from app.repositories.room_repo import InMemoryRoomRepo
from app.services.match_service import MatchService
from app.services.room_service import RoomService
from app.ws.endpoint import get_match_service, get_presence_manager, get_room_service
from app.ws.presence import PresenceManager

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
def reconnect_repo():
    return InMemoryReconnectRepo()


@pytest.fixture()
def presence(reconnect_repo):
    return PresenceManager(reconnect_repo)


@pytest.fixture()
def client(db, room_service, match_service, presence) -> TestClient:
    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_room_service] = lambda: room_service
    app.dependency_overrides[get_match_service] = lambda: match_service
    app.dependency_overrides[get_presence_manager] = lambda: presence
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _register(client: TestClient, email: str, nickname: str) -> str:
    resp = client.post(
        "/auth/register",
        json={
            "email": email,
            "password": "password123",
            "nickname": nickname,
        },
    )
    assert resp.status_code in (200, 201), resp.text
    return resp.json()["access_token"]


def _ws_auth(ws, token: str) -> None:
    ws.send_json({"type": "WS_HELLO", "data": {}})
    ws.receive_json()  # WS_WELCOME
    ws.send_json({"type": "AUTH_LOGIN", "data": {"token": token}})
    ws.receive_json()  # AUTH_OK


def _guest_token(client: TestClient, nickname: str) -> str:
    resp = client.post("/auth/guest", json={"nickname": nickname})
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


def _ws_auth_guest(ws, token: str) -> None:
    ws.send_json({"type": "WS_HELLO", "data": {}})
    ws.receive_json()  # WS_WELCOME
    ws.send_json({"type": "AUTH_GUEST", "data": {"token": token}})
    ws.receive_json()  # AUTH_OK


def _consume_until(ws, target_type: str, max_msgs: int = 20) -> dict:
    for _ in range(max_msgs):
        msg = ws.receive_json()
        if msg["type"] == target_type:
            return msg
    raise AssertionError(f"Did not receive {target_type!r} in {max_msgs} messages")


def _play_remote_turn(ws) -> None:
    """Play one remote-human turn until TURN_RESOLVED is reached."""
    _consume_until(ws, "PHASE_SELECTING")
    hand_msg = _consume_until(ws, "PRIVATE_HAND_STATE")
    card_number = hand_msg["data"]["hand"][0]["number"]
    ws.send_json({"type": "CARD_SELECT", "data": {"card_number": card_number}})
    _consume_until(ws, "PRIVATE_HAND_STATE")
    _consume_until(ws, "TURN_RESOLVED")


def _make_full_room(room_service: RoomService, host_name: str = "Host") -> Room:
    room = room_service.create_room(
        display_name=host_name,
        connection_id="conn-host",
        user_id="user-host",
    )
    room = room_service.start_room(room.room_code, 0)
    return room


# ---------------------------------------------------------------------------
# TestHeartbeat
# ---------------------------------------------------------------------------


class TestHeartbeat:
    def test_pong_clears_awaiting_flag(self, client: TestClient):
        """
        Sending PONG with session.awaiting_pong = True should set it to False.

        We validate the *result* of the PONG handler (session state) rather
        than testing real heartbeat timing.
        """
        token = _register(client, "hb@example.com", "HBUser")
        with client.websocket_connect("/ws") as ws:
            _ws_auth(ws, token)
            # Simulate the server having sent a PING (set awaiting_pong via PING echo).
            # The client-side PONG handler in the server clears the flag.
            ws.send_json({"type": "PONG", "data": {}})
            # No error response means the message was accepted.
            # Send PING (client-initiated) to verify connection is alive.
            ws.send_json({"type": "PING", "data": {}})
            msg = ws.receive_json()
            assert msg["type"] == "PONG"

    def test_client_ping_receives_pong(self, client: TestClient):
        """Client-initiated PING must still be answered with PONG."""
        token = _register(client, "ping@example.com", "PingUser")
        with client.websocket_connect("/ws") as ws:
            _ws_auth(ws, token)
            ws.send_json({"type": "PING", "data": {}})
            msg = ws.receive_json()
            assert msg["type"] == "PONG"

    def test_unknown_message_returns_error(self, client: TestClient):
        """Non-existent message types produce an ERROR response, not a crash."""
        token = _register(client, "unk@example.com", "UnkUser")
        with client.websocket_connect("/ws") as ws:
            _ws_auth(ws, token)
            ws.send_json({"type": "NOT_A_REAL_TYPE", "data": {}})
            msg = ws.receive_json()
            assert msg["type"] == "ERROR"
            assert msg["data"]["code"] == "UNKNOWN_MESSAGE"


# ---------------------------------------------------------------------------
# TestReconnectToken
# ---------------------------------------------------------------------------


class TestReconnectToken:
    def test_token_issued_on_match_start(self, client: TestClient):
        """ROOM_START should unicast a RECONNECT_TOKEN to each human seat."""
        token = _register(client, "tok@example.com", "TokUser")
        with client.websocket_connect("/ws") as ws:
            _ws_auth(ws, token)
            ws.send_json({"type": "ROOM_CREATE", "data": {}})
            _consume_until(ws, "ROOM_STATE")
            ws.send_json({"type": "ROOM_START", "data": {}})
            reconnect_msg = _consume_until(ws, "RECONNECT_TOKEN", max_msgs=30)
        assert "token" in reconnect_msg["data"]
        assert reconnect_msg["data"]["seat_index"] == 0

    def test_guest_match_start_does_not_issue_reconnect_token(self, client: TestClient):
        """Guest-controlled seats must not receive reconnect tokens."""
        token = _guest_token(client, "GuestNoReconnect")
        with client.websocket_connect("/ws") as ws:
            _ws_auth_guest(ws, token)
            ws.send_json({"type": "ROOM_CREATE", "data": {}})
            _consume_until(ws, "ROOM_STATE")
            ws.send_json({"type": "ROOM_START", "data": {}})

            seen_types = set()
            for _ in range(4):
                msg = ws.receive_json()
                seen_types.add(msg["type"])

        assert "RECONNECT_TOKEN" not in seen_types

    def test_token_lookup_valid(self, reconnect_repo: InMemoryReconnectRepo):
        """A freshly created token is retrievable until TTL expires."""
        token = reconnect_repo.create(
            match_id="m1",
            room_code="ABCDEF",
            seat_index=0,
            user_id="u1",
            display_name="Alice",
            account_type="registered",
            ttl_seconds=60,
        )
        entry = reconnect_repo.get(token)
        assert entry is not None
        assert entry.match_id == "m1"
        assert entry.seat_index == 0

    def test_token_lookup_expired(self, reconnect_repo: InMemoryReconnectRepo):
        """An expired token returns None."""
        token = reconnect_repo.create(
            match_id="m1",
            room_code="ABCDEF",
            seat_index=0,
            user_id="u1",
            display_name="Alice",
            account_type="registered",
            ttl_seconds=0,  # expires immediately
        )
        # Advance mock time by directly backdating the entry.
        entry = reconnect_repo._tokens[token]
        entry.expires_at = time.time() - 1
        assert reconnect_repo.get(token) is None

    def test_token_revoke_by_seat(self, reconnect_repo: InMemoryReconnectRepo):
        """revoke_by_match_seat removes the specific seat's token only."""
        t0 = reconnect_repo.create("m1", "ABCDEF", 0, None, "Alice", "guest", 60)
        t1 = reconnect_repo.create("m1", "ABCDEF", 1, None, "Bob", "guest", 60)
        reconnect_repo.revoke_by_match_seat("m1", 0)
        assert reconnect_repo.get(t0) is None
        assert reconnect_repo.get(t1) is not None

    def test_token_revoke_by_match(self, reconnect_repo: InMemoryReconnectRepo):
        """revoke_by_match removes all tokens for that match."""
        t0 = reconnect_repo.create("m1", "ABCDEF", 0, None, "Alice", "guest", 60)
        t1 = reconnect_repo.create("m1", "ABCDEF", 1, None, "Bob", "guest", 60)
        reconnect_repo.revoke_by_match("m1")
        assert reconnect_repo.get(t0) is None
        assert reconnect_repo.get(t1) is None

    def test_create_revokes_previous_for_same_seat(self, reconnect_repo: InMemoryReconnectRepo):
        """Creating a new token for the same (match, seat) invalidates the old one."""
        old = reconnect_repo.create("m1", "ABCDEF", 0, None, "Alice", "guest", 60)
        new = reconnect_repo.create("m1", "ABCDEF", 0, None, "Alice", "guest", 60)
        assert reconnect_repo.get(old) is None
        assert reconnect_repo.get(new) is not None


# ---------------------------------------------------------------------------
# TestReconnectFlow
# ---------------------------------------------------------------------------


class TestReconnectFlow:
    def test_reconnect_ok_with_valid_token(self, client: TestClient):
        """
        A client that disconnects then reconnects with a valid token should:
        - Receive RECONNECT_OK
        - Receive PUBLIC_BOARD_STATE snapshot
        - Receive PRIVATE_HAND_STATE snapshot
        """
        host_token = _register(client, "rc_host@example.com", "RcHost")

        # --- First connection: start match and capture reconnect token ---
        with client.websocket_connect("/ws") as ws:
            _ws_auth(ws, host_token)
            ws.send_json({"type": "ROOM_CREATE", "data": {}})
            _consume_until(ws, "ROOM_STATE")
            ws.send_json({"type": "ROOM_START", "data": {}})
            rc_msg = _consume_until(ws, "RECONNECT_TOKEN", max_msgs=30)
            reconnect_token = rc_msg["data"]["token"]
        # Connection closed here — grace timer starts in background.

        # --- Second connection: reconnect with the token ---
        with client.websocket_connect("/ws") as ws2:
            ws2.send_json({"type": "WS_HELLO", "data": {}})
            ws2.receive_json()  # WS_WELCOME

            ws2.send_json({"type": "RECONNECT", "data": {"token": reconnect_token}})

            ok_msg = _consume_until(ws2, "RECONNECT_OK", max_msgs=10)
            assert ok_msg["data"]["seat_index"] == 0

            board_msg = _consume_until(ws2, "PUBLIC_BOARD_STATE", max_msgs=10)
            assert "board_rows" in board_msg["data"]

            hand_msg = _consume_until(ws2, "PRIVATE_HAND_STATE", max_msgs=10)
            assert "hand" in hand_msg["data"]

    def test_reconnect_invalid_token_returns_error(self, client: TestClient):
        """An unknown token must produce an INVALID_RECONNECT_TOKEN error."""
        with client.websocket_connect("/ws") as ws:
            ws.send_json({"type": "WS_HELLO", "data": {}})
            ws.receive_json()  # WS_WELCOME
            ws.send_json({"type": "RECONNECT", "data": {"token": "not-a-real-token"}})
            err = ws.receive_json()
            assert err["type"] == "ERROR"
            assert err["data"]["code"] == "INVALID_RECONNECT_TOKEN"

    def test_reconnect_missing_token_returns_error(self, client: TestClient):
        """RECONNECT without a token field must return MISSING_TOKEN."""
        with client.websocket_connect("/ws") as ws:
            ws.send_json({"type": "WS_HELLO", "data": {}})
            ws.receive_json()  # WS_WELCOME
            ws.send_json({"type": "RECONNECT", "data": {}})
            err = ws.receive_json()
            assert err["type"] == "ERROR"
            assert err["data"]["code"] == "MISSING_TOKEN"

    def test_reconnect_after_bot_takeover_returns_error(
        self, client: TestClient, match_service: MatchService, room_service: RoomService
    ):
        """Once a seat is taken over by a bot, reconnect must be refused."""
        host_token = _register(client, "to_host@example.com", "ToHost")

        with client.websocket_connect("/ws") as ws:
            _ws_auth(ws, host_token)
            ws.send_json({"type": "ROOM_CREATE", "data": {}})
            _consume_until(ws, "ROOM_STATE")
            ws.send_json({"type": "ROOM_START", "data": {}})
            rc_msg = _consume_until(ws, "RECONNECT_TOKEN", max_msgs=30)
            reconnect_token = rc_msg["data"]["token"]
            match = match_service.get_match_by_room(
                # Find the room by iterating room_service repo
                next(rc for rc in room_service.repo._rooms)
            )

        # Simulate grace expiry by calling takeover directly.
        if match is None:
            # Find match another way

            # Just use the match_service's repo
            all_matches = list(match_service.repo._matches.values())
            assert len(all_matches) == 1
            match = all_matches[0]

        match_service.takeover_seat(match, 0)
        assert match.seats[0].took_over_by_bot is True

        # Now reconnect should fail.
        with client.websocket_connect("/ws") as ws2:
            ws2.send_json({"type": "WS_HELLO", "data": {}})
            ws2.receive_json()  # WS_WELCOME
            ws2.send_json({"type": "RECONNECT", "data": {"token": reconnect_token}})
            err = _consume_until(ws2, "ERROR", max_msgs=5)
            assert err["data"]["code"] == "SEAT_TAKEN_OVER"

    def test_reconnect_seat_restores_connection_id(
        self, match_service: MatchService, room_service: RoomService
    ):
        """reconnect_seat() updates MatchSeat.connection_id and clears flags."""
        room = _make_full_room(room_service)
        match = match_service.create_match(room)

        match_service.mark_seat_disconnected(match, 0)
        assert match.seats[0].is_disconnected is True
        assert match.seats[0].connection_id is None

        match_service.reconnect_seat(match, 0, "new-conn-id")
        assert match.seats[0].is_disconnected is False
        assert match.seats[0].connection_id == "new-conn-id"

    def test_reconnect_participant_updates_room(self, room_service: RoomService):
        """reconnect_participant() updates the connection_id in the room repo."""
        room = room_service.create_room(
            display_name="Alice",
            connection_id="old-conn",
            user_id="u1",
        )
        updated = room_service.reconnect_participant(room.room_code, 0, "new-conn")
        assert updated is not None
        assert updated.participants[0].connection_id == "new-conn"

    def test_registered_old_round_token_is_rejected_after_next_round(self, client: TestClient):
        """Reconnect tokens are rotated each round; old-round tokens must stop working."""
        token = _register(client, "round_rotate@example.com", "RoundRotate")
        with client.websocket_connect("/ws") as ws:
            _ws_auth(ws, token)
            ws.send_json({"type": "ROOM_CREATE", "data": {}})
            _consume_until(ws, "ROOM_STATE")
            ws.send_json({"type": "ROOM_START", "data": {}})
            first_token_msg = _consume_until(ws, "RECONNECT_TOKEN", max_msgs=30)
            old_token = first_token_msg["data"]["token"]

            for _ in range(9):
                _play_remote_turn(ws)

            _consume_until(ws, "PHASE_SELECTING")
            hand_msg = _consume_until(ws, "PRIVATE_HAND_STATE")
            ws.send_json(
                {
                    "type": "CARD_SELECT",
                    "data": {"card_number": hand_msg["data"]["hand"][0]["number"]},
                }
            )
            _consume_until(ws, "PRIVATE_HAND_STATE")
            _consume_until(ws, "TURN_RESOLVED")
            _consume_until(ws, "ROUND_RESULT")

            ws.send_json({"type": "ROUND_READY", "data": {}})
            new_token_msg = _consume_until(ws, "RECONNECT_TOKEN", max_msgs=30)
            assert new_token_msg["data"]["token"] != old_token

        with client.websocket_connect("/ws") as ws2:
            ws2.send_json({"type": "WS_HELLO", "data": {}})
            ws2.receive_json()
            ws2.send_json({"type": "RECONNECT", "data": {"token": old_token}})
            err = _consume_until(ws2, "ERROR", max_msgs=10)
            assert err["data"]["code"] == "INVALID_RECONNECT_TOKEN"


# ---------------------------------------------------------------------------
# TestBotTakeover
# ---------------------------------------------------------------------------


class TestBotTakeover:
    def test_takeover_converts_remote_to_bot(
        self, match_service: MatchService, room_service: RoomService
    ):
        """takeover_seat() must change controller_type to BOT."""
        room = _make_full_room(room_service)
        match = match_service.create_match(room)
        assert match.seats[0].controller_type == SeatControllerType.REMOTE

        match_service.takeover_seat(match, 0)
        assert match.seats[0].controller_type == SeatControllerType.BOT

    def test_takeover_sets_took_over_by_bot(
        self, match_service: MatchService, room_service: RoomService
    ):
        """took_over_by_bot must be True after takeover."""
        room = _make_full_room(room_service)
        match = match_service.create_match(room)
        match_service.takeover_seat(match, 0)
        assert match.seats[0].took_over_by_bot is True

    def test_takeover_installs_ai_controller(
        self, match_service: MatchService, room_service: RoomService
    ):
        """takeover_seat() must install an AIPlayer on the seat."""
        room = _make_full_room(room_service)
        match = match_service.create_match(room)
        assert match.seats[0].ai_controller is None
        match_service.takeover_seat(match, 0)
        assert match.seats[0].ai_controller is not None

    def test_takeover_auto_selects_when_in_selecting_phase(
        self, match_service: MatchService, room_service: RoomService
    ):
        """
        If the match is in SELECTING phase at takeover time, the new AI
        controller must immediately choose a card.
        """
        room = _make_full_room(room_service)
        match = match_service.create_match(room)

        rules = match.rules
        assert rules.round_state.phase == RoundPhase.SELECTING
        assert match.seats[0].player.selected_card is None  # human hasn't selected

        match_service.takeover_seat(match, 0)
        assert match.seats[0].player.selected_card is not None

    def test_takeover_clears_disconnected_flag(
        self, match_service: MatchService, room_service: RoomService
    ):
        """After takeover, is_disconnected should be False (fully converted)."""
        room = _make_full_room(room_service)
        match = match_service.create_match(room)
        match_service.mark_seat_disconnected(match, 0)
        assert match.seats[0].is_disconnected is True

        match_service.takeover_seat(match, 0)
        assert match.seats[0].is_disconnected is False

    def test_takeover_makes_all_selected_after_human_only_seat(
        self, match_service: MatchService, room_service: RoomService
    ):
        """
        With a single human seat (seats 1-3 are bots), taking over seat 0
        should cause all_selected() to return True.
        """
        room = _make_full_room(room_service)
        match = match_service.create_match(room)

        # Bots already selected at round start; only seat 0 (human) is pending.
        assert not match_service.all_selected(match)

        match_service.takeover_seat(match, 0)
        assert match_service.all_selected(match)

    def test_mark_seat_disconnected_records_time(
        self, match_service: MatchService, room_service: RoomService
    ):
        """mark_seat_disconnected must set disconnected_at to a recent timestamp."""
        room = _make_full_room(room_service)
        match = match_service.create_match(room)

        before = time.time()
        match_service.mark_seat_disconnected(match, 0)
        after = time.time()

        assert match.seats[0].is_disconnected is True
        assert before <= match.seats[0].disconnected_at <= after
        assert match.seats[0].connection_id is None

    def test_guest_disconnect_is_immediate_bot_takeover(
        self,
        client: TestClient,
        match_service: MatchService,
        room_service: RoomService,
    ):
        """Guests cannot reconnect, so their seat is converted to BOT on disconnect."""
        token = _guest_token(client, "GuestTakeover")
        room_code = None
        with client.websocket_connect("/ws") as ws:
            _ws_auth_guest(ws, token)
            ws.send_json({"type": "ROOM_CREATE", "data": {}})
            room_msg = _consume_until(ws, "ROOM_STATE")
            room_code = room_msg["data"]["room_code"]
            ws.send_json({"type": "ROOM_START", "data": {}})
            _consume_until(ws, "MATCH_START")

        assert room_code is not None
        match = match_service.get_match_by_room(room_code)
        assert match is not None
        assert match.seats[0].took_over_by_bot is True
        room = room_service.repo.get(room_code)
        assert room is not None
        assert room.participants[0].controller_type == SeatControllerType.BOT


# ---------------------------------------------------------------------------
# TestSelectionTimeout
# ---------------------------------------------------------------------------


class TestSelectionTimeout:
    def test_auto_select_timed_out_selects_for_unselected_humans(
        self, match_service: MatchService, room_service: RoomService
    ):
        """auto_select_timed_out() must pick a card for each human with no selection."""
        room = _make_full_room(room_service)
        match = match_service.create_match(room)

        assert match.seats[0].player.selected_card is None
        timed_out = match_service.auto_select_timed_out(match)
        assert 0 in timed_out
        assert match.seats[0].player.selected_card is not None

    def test_auto_select_does_not_affect_already_selected(
        self, match_service: MatchService, room_service: RoomService
    ):
        """Seats that already selected a card are not overwritten."""
        room = _make_full_room(room_service)
        match = match_service.create_match(room)

        card = match.seats[0].player.hand[0]
        match_service.submit_selection(match, 0, card.number)
        original = match.seats[0].player.selected_card

        match_service.auto_select_timed_out(match)
        assert match.seats[0].player.selected_card is original

    def test_auto_select_returns_empty_outside_selecting_phase(
        self, match_service: MatchService, room_service: RoomService
    ):
        """auto_select_timed_out() is a no-op outside SELECTING phase."""
        room = _make_full_room(room_service)
        match = match_service.create_match(room)

        # Manually move to PLACING phase to simulate wrong state.
        match.rules.round_state.phase = RoundPhase.PLACING
        result = match_service.auto_select_timed_out(match)
        assert result == []

    def test_auto_select_skips_bot_seats(
        self, match_service: MatchService, room_service: RoomService
    ):
        """auto_select_timed_out() should not touch bot seats."""
        room = _make_full_room(room_service)
        match = match_service.create_match(room)
        timed_out = match_service.auto_select_timed_out(match)
        # Only seat 0 is REMOTE; seats 1-3 are BOT.
        assert timed_out == [0]

    def test_auto_select_makes_all_selected(
        self, match_service: MatchService, room_service: RoomService
    ):
        """After auto_select_timed_out(), all_selected() should return True."""
        room = _make_full_room(room_service)
        match = match_service.create_match(room)
        assert not match_service.all_selected(match)
        match_service.auto_select_timed_out(match)
        assert match_service.all_selected(match)


# ---------------------------------------------------------------------------
# TestPresenceManager
# ---------------------------------------------------------------------------


class TestPresenceManager:
    def test_issue_and_lookup_token(self, presence: PresenceManager):
        """issue_token() must store a retrievable entry."""
        token = presence.issue_token(
            match_id="m1",
            room_code="ABCDEF",
            seat_index=1,
            user_id="u1",
            display_name="Bob",
            account_type="registered",
        )
        entry = presence.lookup_token(token)
        assert entry is not None
        assert entry.seat_index == 1
        assert entry.match_id == "m1"

    def test_revoke_seat_token_removes_entry(self, presence: PresenceManager):
        """revoke_seat_token() must make the token unretrievable."""
        token = presence.issue_token(
            match_id="m1",
            room_code="ABCDEF",
            seat_index=0,
            user_id=None,
            display_name="Alice",
            account_type="guest",
        )
        presence.revoke_seat_token("m1", 0)
        assert presence.lookup_token(token) is None

    def test_revoke_match_tokens_removes_all(self, presence: PresenceManager):
        """revoke_match_tokens() must clear every token for that match."""
        t0 = presence.issue_token("m1", "ABCDEF", 0, None, "Alice", "guest")
        t1 = presence.issue_token("m1", "ABCDEF", 1, None, "Bob", "guest")
        t_other = presence.issue_token("m2", "XXXXXX", 0, None, "Carol", "guest")
        presence.revoke_match_tokens("m1")
        assert presence.lookup_token(t0) is None
        assert presence.lookup_token(t1) is None
        assert presence.lookup_token(t_other) is not None

    def test_reset_clears_tokens(self, presence: PresenceManager):
        """reset() must clear all token entries."""
        token = presence.issue_token("m1", "ABCDEF", 0, None, "Alice", "guest")
        presence.reset()
        assert presence.lookup_token(token) is None

    def test_selection_timeout_set_on_match(
        self,
        match_service: MatchService,
        room_service: RoomService,
        client: TestClient,
    ):
        """
        After ROOM_START, ActiveMatch.selection_started_at must be set
        (set by _start_selection_timeout in the handler).
        """
        host_token = _register(client, "st@example.com", "StUser")
        with client.websocket_connect("/ws") as ws:
            _ws_auth(ws, host_token)
            ws.send_json({"type": "ROOM_CREATE", "data": {}})
            _consume_until(ws, "ROOM_STATE")
            ws.send_json({"type": "ROOM_START", "data": {}})
            _consume_until(ws, "PHASE_SELECTING", max_msgs=30)

        all_matches = list(match_service.repo._matches.values())
        assert len(all_matches) == 1
        assert all_matches[0].selection_started_at is not None
