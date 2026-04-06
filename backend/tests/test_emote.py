"""
Tests for the PR-07 emote system.

Coverage:
  - EmoteService: catalog validation, cooldown, burst cap, reset
  - WS protocol: EMOTE_SEND happy path, invalid emote_id, not-in-room guard,
    not-authenticated guard, rate-limit rejection
  - EMOTE_BROADCAST fanout: all room members receive, sender receives
  - Mute: EMOTE_MUTE sets flag; muted connection does not receive broadcasts
"""

import time
import uuid

import pytest

from app.config import settings
from app.services.emote_service import VALID_EMOTE_IDS, EmoteService

# ===========================================================================
# Helpers
# ===========================================================================


def _register_and_get_token(client, email: str = None, nickname: str = None) -> str:
    email = email or f"u{uuid.uuid4().hex[:8]}@test.com"
    nickname = nickname or f"P{uuid.uuid4().hex[:6]}"
    resp = client.post(
        "/auth/register",
        json={"email": email, "password": "Test1234!", "nickname": nickname},
    )
    assert resp.status_code in (200, 201)
    return resp.json()["access_token"]


def _ws_auth(ws, token: str) -> None:
    """Send WS_HELLO + AUTH_LOGIN and consume their responses."""
    ws.send_json({"type": "WS_HELLO", "data": {}})
    ws.receive_json()  # WS_WELCOME
    ws.send_json({"type": "AUTH_LOGIN", "data": {"token": token}})
    ws.receive_json()  # AUTH_OK


def _ws_create_room(ws) -> str:
    """Create a room and return room_code."""
    ws.send_json({"type": "ROOM_CREATE", "data": {}})
    msg = ws.receive_json()  # ROOM_STATE
    assert msg["type"] == "ROOM_STATE"
    return msg["data"]["room_code"]


def _ws_join_room(ws, room_code: str) -> None:
    ws.send_json({"type": "ROOM_JOIN", "data": {"room_code": room_code}})
    ws.receive_json()  # ROOM_STATE (host sees it too)


# ===========================================================================
# TestEmoteService — unit tests, no WS
# ===========================================================================


class TestEmoteService:
    def setup_method(self):
        self.svc = EmoteService()

    # ------------------------------------------------------------------
    # Catalog
    # ------------------------------------------------------------------

    def test_valid_emote_ids_are_non_empty(self):
        assert len(VALID_EMOTE_IDS) > 0

    def test_is_valid_emote_known(self):
        for emote_id in VALID_EMOTE_IDS:
            assert self.svc.is_valid_emote(emote_id)

    def test_is_valid_emote_unknown(self):
        assert not self.svc.is_valid_emote("free_text_lol")
        assert not self.svc.is_valid_emote("")
        assert not self.svc.is_valid_emote("THUMBSUP")  # case-sensitive

    # ------------------------------------------------------------------
    # Cooldown
    # ------------------------------------------------------------------

    def test_first_emote_is_allowed(self):
        assert self.svc.check_and_record("conn1", "smile") is True

    def test_second_emote_within_cooldown_denied(self):
        self.svc.check_and_record("conn1", "smile")
        assert self.svc.check_and_record("conn1", "fire") is False

    def test_different_connections_independent_cooldowns(self):
        assert self.svc.check_and_record("conn1", "smile") is True
        assert self.svc.check_and_record("conn2", "smile") is True

    def test_remaining_cooldown_after_send(self):
        self.svc.check_and_record("conn1", "smile")
        remaining = self.svc.remaining_cooldown("conn1")
        assert 0.0 < remaining <= settings.EMOTE_COOLDOWN_SECONDS

    def test_remaining_cooldown_before_first_send_is_zero(self):
        assert self.svc.remaining_cooldown("never_sent") == 0.0

    # ------------------------------------------------------------------
    # Burst cap
    # ------------------------------------------------------------------

    def test_burst_cap_enforced(self):
        """
        After EMOTE_BURST_CAP allowed emotes within the burst window, the
        next attempt is denied — even if the per-send cooldown has elapsed.

        We fake elapsed time by manipulating _last_sent so the cooldown
        check passes but the window accumulates.  Different emote IDs are
        used on each send to avoid triggering the same-emote soft block.
        """
        svc = EmoteService()
        conn = "burst_test"
        cap = settings.EMOTE_BURST_CAP
        emotes = list(VALID_EMOTE_IDS)

        for i in range(cap):
            # Advance last_sent far enough back to pass cooldown
            svc._last_sent[conn] = time.time() - settings.EMOTE_COOLDOWN_SECONDS - 0.1
            result = svc.check_and_record(conn, emotes[i % len(emotes)])
            assert result is True, f"Should be allowed on attempt {i + 1}"

        # Now all cap slots are used — deny even after cooldown
        svc._last_sent[conn] = time.time() - settings.EMOTE_COOLDOWN_SECONDS - 0.1
        assert svc.check_and_record(conn, "clap") is False

    def test_burst_window_expires(self):
        """
        Entries older than EMOTE_BURST_WINDOW_SECONDS are pruned, freeing
        the burst cap.
        """
        svc = EmoteService()
        conn = "window_test"
        cap = settings.EMOTE_BURST_CAP

        # Fill the window with old timestamps
        old_ts = time.time() - settings.EMOTE_BURST_WINDOW_SECONDS - 1.0
        svc._window_history[conn] = [old_ts] * cap

        # Cooldown has also elapsed
        svc._last_sent[conn] = time.time() - settings.EMOTE_COOLDOWN_SECONDS - 0.1

        # Should be allowed — old entries pruned
        assert svc.check_and_record(conn, "thumbsup") is True

    # ------------------------------------------------------------------
    # Same-emote soft block
    # ------------------------------------------------------------------

    def test_same_emote_soft_block_after_cap(self):
        """
        Sending the same emote more than EMOTE_SAME_REPEAT_CAP times in
        a row is denied even after the cooldown passes.
        """
        svc = EmoteService()
        conn = "spam_test"
        cap = settings.EMOTE_SAME_REPEAT_CAP

        for i in range(cap):
            svc._last_sent[conn] = time.time() - settings.EMOTE_COOLDOWN_SECONDS - 0.1
            result = svc.check_and_record(conn, "fire")
            assert result is True, f"Should be allowed on attempt {i + 1}"

        # cap+1 consecutive same emote → denied
        svc._last_sent[conn] = time.time() - settings.EMOTE_COOLDOWN_SECONDS - 0.1
        assert svc.check_and_record(conn, "fire") is False

    def test_different_emote_resets_same_emote_streak(self):
        """
        Switching to a different emote resets the same-emote streak counter,
        allowing the original emote to be sent again.

        We use cap-1 repeated sends to fill the streak without exhausting the
        burst window (BURST_CAP > SAME_REPEAT_CAP in the spec values).
        """
        svc = EmoteService()
        conn = "streak_test"
        cap = settings.EMOTE_SAME_REPEAT_CAP

        # Build up cap-1 "fire" sends (streak below block threshold)
        for _ in range(cap - 1):
            svc._last_sent[conn] = time.time() - settings.EMOTE_COOLDOWN_SECONDS - 0.1
            svc.check_and_record(conn, "fire")

        # Sending a different emote should be allowed and reset the streak
        svc._last_sent[conn] = time.time() - settings.EMOTE_COOLDOWN_SECONDS - 0.1
        assert svc.check_and_record(conn, "smile") is True

        # "fire" is allowed again — streak was reset by "smile"
        svc._last_sent[conn] = time.time() - settings.EMOTE_COOLDOWN_SECONDS - 0.1
        assert svc.check_and_record(conn, "fire") is True

    # ------------------------------------------------------------------
    # Reset
    # ------------------------------------------------------------------

    def test_reset_clears_all_state(self):
        self.svc.check_and_record("conn1", "smile")
        self.svc.reset()
        # After reset the connection should be allowed again
        assert self.svc.check_and_record("conn1", "smile") is True


# ===========================================================================
# TestEmoteWsProtocol — WS integration tests
# ===========================================================================


class TestEmoteWsProtocol:
    """
    Integration tests for EMOTE_SEND and EMOTE_MUTE over the WS endpoint.

    Each test uses the `client` fixture which provides a fresh in-memory DB.
    The autouse reset_emote_service fixture (defined in conftest.py below)
    clears rate-limit state between tests.
    """

    # ------------------------------------------------------------------
    # Guard conditions
    # ------------------------------------------------------------------

    def test_emote_send_not_authenticated(self, client):
        with client.websocket_connect("/ws") as ws:
            ws.send_json({"type": "WS_HELLO", "data": {}})
            ws.receive_json()
            ws.send_json({"type": "EMOTE_SEND", "data": {"emote_id": "smile"}})
            msg = ws.receive_json()
            assert msg["type"] == "ERROR"
            assert msg["data"]["code"] == "NOT_AUTHENTICATED"

    def test_emote_send_not_in_room(self, client):
        token = _register_and_get_token(client)
        with client.websocket_connect("/ws") as ws:
            _ws_auth(ws, token)
            ws.send_json({"type": "EMOTE_SEND", "data": {"emote_id": "smile"}})
            msg = ws.receive_json()
            assert msg["type"] == "ERROR"
            assert msg["data"]["code"] == "NOT_IN_ROOM"

    def test_emote_send_invalid_emote_id(self, client):
        token = _register_and_get_token(client)
        with client.websocket_connect("/ws") as ws:
            _ws_auth(ws, token)
            _ws_create_room(ws)
            ws.send_json({"type": "EMOTE_SEND", "data": {"emote_id": "freetext_attack"}})
            msg = ws.receive_json()
            assert msg["type"] == "ERROR"
            assert msg["data"]["code"] == "INVALID_EMOTE"

    # ------------------------------------------------------------------
    # Happy path — sender receives own broadcast
    # ------------------------------------------------------------------

    def test_emote_send_happy_path(self, client):
        token = _register_and_get_token(client)
        with client.websocket_connect("/ws") as ws:
            _ws_auth(ws, token)
            _ws_create_room(ws)
            ws.send_json({"type": "EMOTE_SEND", "data": {"emote_id": "thumbsup"}})
            msg = ws.receive_json()
            assert msg["type"] == "EMOTE_BROADCAST"
            assert msg["data"]["emote_id"] == "thumbsup"
            assert msg["data"]["seat_index"] == 0  # host is seat 0

    def test_emote_broadcast_delivered_to_all_room_members(self, client):
        """Both the sender and a second room member receive the broadcast."""
        token_a = _register_and_get_token(client)
        token_b = _register_and_get_token(client)

        with (
            client.websocket_connect("/ws") as ws_a,
            client.websocket_connect("/ws") as ws_b,
        ):
            _ws_auth(ws_a, token_a)
            room_code = _ws_create_room(ws_a)

            _ws_auth(ws_b, token_b)
            ws_b.send_json({"type": "ROOM_JOIN", "data": {"room_code": room_code}})
            # ws_a receives ROOM_STATE from ws_b joining
            ws_a.receive_json()
            # ws_b receives ROOM_STATE
            ws_b.receive_json()

            # ws_a sends emote
            ws_a.send_json({"type": "EMOTE_SEND", "data": {"emote_id": "clap"}})

            # Both should receive EMOTE_BROADCAST
            msg_a = ws_a.receive_json()
            msg_b = ws_b.receive_json()

            assert msg_a["type"] == "EMOTE_BROADCAST"
            assert msg_a["data"]["emote_id"] == "clap"
            assert msg_b["type"] == "EMOTE_BROADCAST"
            assert msg_b["data"]["emote_id"] == "clap"
            # seat_index must match the sender's seat (0 = host)
            assert msg_a["data"]["seat_index"] == msg_b["data"]["seat_index"]

    # ------------------------------------------------------------------
    # Rate limiting via WS
    # ------------------------------------------------------------------

    def test_emote_rate_limited_on_second_immediate_send(self, client):
        token = _register_and_get_token(client)
        with client.websocket_connect("/ws") as ws:
            _ws_auth(ws, token)
            _ws_create_room(ws)

            # First emote is allowed
            ws.send_json({"type": "EMOTE_SEND", "data": {"emote_id": "fire"}})
            msg1 = ws.receive_json()
            assert msg1["type"] == "EMOTE_BROADCAST"

            # Immediate second emote: rate-limited
            ws.send_json({"type": "EMOTE_SEND", "data": {"emote_id": "fire"}})
            msg2 = ws.receive_json()
            assert msg2["type"] == "ERROR"
            assert msg2["data"]["code"] == "EMOTE_RATE_LIMITED"

    # ------------------------------------------------------------------
    # Mute
    # ------------------------------------------------------------------

    def test_emote_mute_ack_returned(self, client):
        token = _register_and_get_token(client)
        with client.websocket_connect("/ws") as ws:
            _ws_auth(ws, token)
            ws.send_json({"type": "EMOTE_MUTE", "data": {"muted": True}})
            msg = ws.receive_json()
            assert msg["type"] == "EMOTE_MUTE_ACK"
            assert msg["data"]["muted"] is True

    def test_emote_mute_unmute_ack(self, client):
        token = _register_and_get_token(client)
        with client.websocket_connect("/ws") as ws:
            _ws_auth(ws, token)
            ws.send_json({"type": "EMOTE_MUTE", "data": {"muted": False}})
            msg = ws.receive_json()
            assert msg["type"] == "EMOTE_MUTE_ACK"
            assert msg["data"]["muted"] is False

    def test_muted_member_does_not_receive_emote_broadcast(self, client):
        """
        ws_b mutes emotes → when ws_a sends an emote, ws_b does not receive
        EMOTE_BROADCAST.  ws_a (sender) still receives it.
        """
        token_a = _register_and_get_token(client)
        token_b = _register_and_get_token(client)

        with (
            client.websocket_connect("/ws") as ws_a,
            client.websocket_connect("/ws") as ws_b,
        ):
            _ws_auth(ws_a, token_a)
            room_code = _ws_create_room(ws_a)

            _ws_auth(ws_b, token_b)
            ws_b.send_json({"type": "ROOM_JOIN", "data": {"room_code": room_code}})
            ws_a.receive_json()  # ROOM_STATE from b joining
            ws_b.receive_json()  # ROOM_STATE

            # ws_b mutes emotes
            ws_b.send_json({"type": "EMOTE_MUTE", "data": {"muted": True}})
            ack = ws_b.receive_json()
            assert ack["type"] == "EMOTE_MUTE_ACK"

            # ws_a sends emote
            ws_a.send_json({"type": "EMOTE_SEND", "data": {"emote_id": "cry"}})

            # ws_a receives its own broadcast
            msg_a = ws_a.receive_json()
            assert msg_a["type"] == "EMOTE_BROADCAST"

            # ws_b should not receive anything (no message queued)
            # Use timeout to confirm no message arrives.
            import pytest

            with pytest.raises(Exception):
                # TestClient websocket receive will raise on timeout/disconnect
                ws_b.receive_json(timeout=0.05)

    def test_muted_sender_still_broadcasts_to_unmuted_peers(self, client):
        """
        Muting only affects *reception*.  A muted connection can still send
        emotes, and unmuted peers receive the broadcast.
        """
        token_a = _register_and_get_token(client)
        token_b = _register_and_get_token(client)

        with (
            client.websocket_connect("/ws") as ws_a,
            client.websocket_connect("/ws") as ws_b,
        ):
            _ws_auth(ws_a, token_a)
            room_code = _ws_create_room(ws_a)

            _ws_auth(ws_b, token_b)
            ws_b.send_json({"type": "ROOM_JOIN", "data": {"room_code": room_code}})
            ws_a.receive_json()  # ROOM_STATE
            ws_b.receive_json()  # ROOM_STATE

            # ws_a mutes itself (affects only its reception)
            ws_a.send_json({"type": "EMOTE_MUTE", "data": {"muted": True}})
            ws_a.receive_json()  # EMOTE_MUTE_ACK

            # ws_a sends emote — ws_b (unmuted) should receive
            ws_a.send_json({"type": "EMOTE_SEND", "data": {"emote_id": "thinking"}})

            # ws_b receives broadcast
            msg_b = ws_b.receive_json()
            assert msg_b["type"] == "EMOTE_BROADCAST"
            assert msg_b["data"]["emote_id"] == "thinking"

    # ------------------------------------------------------------------
    # Catalog completeness
    # ------------------------------------------------------------------

    @pytest.mark.parametrize("emote_id", sorted(VALID_EMOTE_IDS))
    def test_every_valid_emote_sends_successfully(self, client, emote_id):
        token = _register_and_get_token(client)
        with client.websocket_connect("/ws") as ws:
            _ws_auth(ws, token)
            _ws_create_room(ws)
            ws.send_json({"type": "EMOTE_SEND", "data": {"emote_id": emote_id}})
            msg = ws.receive_json()
            assert msg["type"] == "EMOTE_BROADCAST", (
                f"Expected EMOTE_BROADCAST for {emote_id!r}, got {msg!r}"
            )
            assert msg["data"]["emote_id"] == emote_id
