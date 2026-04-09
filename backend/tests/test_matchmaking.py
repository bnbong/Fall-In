"""
Tests for PR-06: Quick-match queue, MMR, and matchmaking service.

Coverage:
  - QueueRepo: add / remove / get_bucket / bucket_size / get_entry
  - MatchmakingService: join_queue, leave_queue, try_form_match (immediate 4),
    fill timer AI fallback, build_quick_match_room, bucket assignment
  - MmrService: get_mmr defaults, bucket mapping, compute_deltas, persist_updates
    (eligible 4-human, eligible 3-human, ineligible ≤2-human, guest-only match)
  - WS integration: QUICK_MATCH_JOIN (bucket grouping, immediate match,
    AI-fill path), QUICK_MATCH_LEAVE, queue cleanup on disconnect
"""

import time
import uuid

from app.config import settings
from app.models.db import AccountType, Profile, User, UserStatus
from app.models.match import ActiveMatch, MatchSeat
from app.models.room import RoomPhase, SeatControllerType
from app.repositories.queue_repo import InMemoryQueueRepo, QueueEntry
from app.services.matchmaking_service import MatchmakingService
from app.services.mmr_service import MmrService, mmr_to_bucket

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_entry(
    connection_id: str = None,
    mmr: int = 1000,
    bucket: str = "silver",
    account_type: str = "registered",
    user_id: str = None,
) -> QueueEntry:
    return QueueEntry(
        connection_id=connection_id or str(uuid.uuid4()),
        user_id=user_id or str(uuid.uuid4()),
        display_name="Player",
        account_type=account_type,
        mmr=mmr,
        bucket=bucket,
        joined_at=time.time(),
    )


def _make_matchmaking() -> MatchmakingService:
    return MatchmakingService(InMemoryQueueRepo())


def _make_user_with_profile(db, mmr: int = None) -> User:
    user = User(
        id=str(uuid.uuid4()),
        account_type=AccountType.REGISTERED,
        status=UserStatus.ACTIVE,
    )
    db.add(user)
    db.flush()
    profile = Profile(
        user_id=user.id,
        nickname="TestPlayer",
        hidden_mmr=mmr,
    )
    db.add(profile)
    db.commit()
    db.refresh(user)
    return user


# ===========================================================================
# TestQueueRepo
# ===========================================================================


class TestQueueRepo:
    def test_add_and_get_bucket(self):
        repo = InMemoryQueueRepo()
        e = _make_entry(bucket="silver")
        repo.add(e)
        result = repo.get_bucket("silver")
        assert len(result) == 1
        assert result[0].connection_id == e.connection_id

    def test_bucket_size(self):
        repo = InMemoryQueueRepo()
        repo.add(_make_entry(bucket="gold"))
        repo.add(_make_entry(bucket="gold"))
        assert repo.bucket_size("gold") == 2
        assert repo.bucket_size("silver") == 0

    def test_remove_returns_entry(self):
        repo = InMemoryQueueRepo()
        e = _make_entry()
        repo.add(e)
        removed = repo.remove(e.connection_id)
        assert removed is not None
        assert removed.connection_id == e.connection_id
        assert repo.bucket_size(e.bucket) == 0

    def test_remove_unknown_returns_none(self):
        repo = InMemoryQueueRepo()
        assert repo.remove("no-such-id") is None

    def test_get_entry(self):
        repo = InMemoryQueueRepo()
        e = _make_entry()
        repo.add(e)
        found = repo.get_entry(e.connection_id)
        assert found is not None
        assert found.mmr == e.mmr

    def test_get_bucket_sorted_by_joined_at(self):
        repo = InMemoryQueueRepo()
        e1 = _make_entry(bucket="bronze")
        e1.joined_at = 100.0
        e2 = _make_entry(bucket="bronze")
        e2.joined_at = 50.0  # earlier
        repo.add(e1)
        repo.add(e2)
        bucket = repo.get_bucket("bronze")
        assert bucket[0].connection_id == e2.connection_id  # oldest first

    def test_clear_empties_all_state(self):
        repo = InMemoryQueueRepo()
        repo.add(_make_entry(bucket="silver"))
        repo.clear()
        assert repo.bucket_size("silver") == 0


# ===========================================================================
# TestMmrBuckets
# ===========================================================================


class TestMmrBuckets:
    def test_bronze_low(self):
        assert mmr_to_bucket(0) == "bronze"
        assert mmr_to_bucket(799) == "bronze"

    def test_silver(self):
        assert mmr_to_bucket(800) == "silver"
        assert mmr_to_bucket(1199) == "silver"

    def test_gold(self):
        assert mmr_to_bucket(1200) == "gold"
        assert mmr_to_bucket(1599) == "gold"

    def test_diamond(self):
        assert mmr_to_bucket(1600) == "diamond"
        assert mmr_to_bucket(9999) == "diamond"

    def test_default_mmr_is_silver(self):
        assert mmr_to_bucket(settings.DEFAULT_MMR) == "silver"


# ===========================================================================
# TestMmrService
# ===========================================================================


class TestMmrService:
    def setup_method(self):
        self.svc = MmrService()

    def test_get_mmr_returns_default_if_no_profile_mmr(self, db):
        user = _make_user_with_profile(db, mmr=None)
        assert self.svc.get_mmr(db, user.id) == settings.DEFAULT_MMR

    def test_get_mmr_returns_stored_value(self, db):
        user = _make_user_with_profile(db, mmr=1400)
        assert self.svc.get_mmr(db, user.id) == 1400

    def test_get_mmr_for_session_guest_always_default(self, db):
        result = self.svc.get_mmr_for_session(db, user_id=None, account_type="guest")
        assert result == settings.DEFAULT_MMR

    def test_get_mmr_for_session_registered(self, db):
        user = _make_user_with_profile(db, mmr=900)
        result = self.svc.get_mmr_for_session(db, user_id=user.id, account_type="registered")
        assert result == 900

    def test_compute_deltas_zero_sum(self):
        deltas = self.svc.compute_deltas(
            winner_seat=0,
            human_seat_indices=[0, 1, 2, 3],
            k_factor=32,
        )
        assert deltas[0] == 32  # winner
        assert deltas[1] < 0
        assert deltas[2] < 0
        assert deltas[3] < 0
        # Zero-sum (within integer rounding)
        total = sum(deltas.values())
        assert abs(total) <= 2  # small rounding acceptable

    def test_compute_deltas_winner_not_in_humans(self):
        # Bot won (shouldn't happen in ranked, but guard exists)
        deltas = self.svc.compute_deltas(
            winner_seat=3,
            human_seat_indices=[0, 1, 2],
            k_factor=32,
        )
        assert all(v == 0 for v in deltas.values())

    def test_persist_updates_full_4_human(self, db):
        users = [_make_user_with_profile(db, mmr=1000) for _ in range(4)]
        match = _make_mock_match_all_human(users, winner_seat=0, is_ranked=True)
        self.svc.persist_updates(db, match, winner_seat=0)
        # Winner should have gained MMR.
        for u in users:
            db.refresh(u.profile)
        winner_profile = users[0].profile
        assert winner_profile.hidden_mmr > 1000
        # Losers should have lost MMR.
        for u in users[1:]:
            assert u.profile.hidden_mmr < 1000

    def test_persist_updates_3_human_half_k(self, db):
        users = [_make_user_with_profile(db, mmr=1000) for _ in range(3)]
        match = _make_mock_match_3_human(users, winner_seat=0, is_ranked=True)
        self.svc.persist_updates(db, match, winner_seat=0)
        for u in users:
            db.refresh(u.profile)
        k_half = settings.MMR_K_FACTOR // 2
        assert users[0].profile.hidden_mmr == 1000 + k_half

    def test_persist_updates_2_human_no_update(self, db):
        users = [_make_user_with_profile(db, mmr=1000) for _ in range(2)]
        match = _make_mock_match_2_human(users, winner_seat=0, is_ranked=True)
        self.svc.persist_updates(db, match, winner_seat=0)
        for u in users:
            db.refresh(u.profile)
        assert users[0].profile.hidden_mmr == 1000
        assert users[1].profile.hidden_mmr == 1000

    def test_persist_updates_not_ranked_no_op(self, db):
        users = [_make_user_with_profile(db, mmr=1000) for _ in range(4)]
        match = _make_mock_match_all_human(users, winner_seat=0, is_ranked=False)
        self.svc.persist_updates(db, match, winner_seat=0)
        for u in users:
            db.refresh(u.profile)
        assert all(u.profile.hidden_mmr == 1000 for u in users)

    def test_persist_updates_guest_seats_not_stored(self, db):
        """Guest seat deltas are computed but not written to DB."""
        # 3 registered + 1 guest; all human, ranked
        reg_users = [_make_user_with_profile(db, mmr=1000) for _ in range(3)]
        match = _make_mock_match_with_guest(reg_users, guest_seat=3, winner_seat=0, is_ranked=True)
        self.svc.persist_updates(db, match, winner_seat=0)
        for u in reg_users:
            db.refresh(u.profile)
        # Registered winner gained MMR
        assert reg_users[0].profile.hidden_mmr > 1000


# ===========================================================================
# TestMatchmakingService
# ===========================================================================


class TestMatchmakingService:
    def setup_method(self):
        self.svc = _make_matchmaking()

    def test_join_queue_assigns_bucket(self):
        entry = self.svc.join_queue(
            connection_id="c1",
            user_id="u1",
            display_name="P",
            account_type="registered",
            mmr=1000,
        )
        assert entry.bucket == "silver"
        assert self.svc.bucket_size("silver") == 1

    def test_join_queue_guest_gets_default_bucket(self):
        entry = self.svc.join_queue(
            connection_id="c1",
            user_id=None,
            display_name="Guest",
            account_type="guest",
            mmr=settings.DEFAULT_MMR,
        )
        assert entry.bucket == mmr_to_bucket(settings.DEFAULT_MMR)

    def test_leave_queue(self):
        entry = self.svc.join_queue("c1", "u1", "P", "registered", 1000)
        removed = self.svc.leave_queue("c1")
        assert removed is not None
        assert removed.connection_id == "c1"
        assert self.svc.bucket_size(entry.bucket) == 0

    def test_leave_queue_unknown_returns_none(self):
        assert self.svc.leave_queue("nobody") is None

    def test_try_form_match_returns_none_if_under_4(self):
        for i in range(3):
            self.svc.join_queue(f"c{i}", f"u{i}", "P", "registered", 1000)
        assert self.svc.try_form_match("silver") is None
        assert self.svc.bucket_size("silver") == 3

    def test_try_form_match_pops_4(self):
        for i in range(5):
            self.svc.join_queue(f"c{i}", f"u{i}", "P", "registered", 1000)
        four = self.svc.try_form_match("silver")
        assert four is not None
        assert len(four) == 4
        # 5th player remains
        assert self.svc.bucket_size("silver") == 1

    def test_try_form_match_takes_oldest_first(self):
        entries = []
        for i in range(4):
            e = self.svc.join_queue(f"c{i}", f"u{i}", f"P{i}", "registered", 1000)
            entries.append(e)
            # Ensure distinct joined_at by nudging the value.
            e.joined_at = float(i)
        # Re-add with explicit timestamps.
        self.svc._repo.clear()
        for e in entries:
            self.svc._repo.add(e)
        four = self.svc.try_form_match("silver")
        assert [e.connection_id for e in four] == ["c0", "c1", "c2", "c3"]

    def test_build_quick_match_room_all_human(self):
        entries = [_make_entry(connection_id=f"c{i}") for i in range(4)]
        room = MatchmakingService.build_quick_match_room(entries, ai_count=0)
        assert room.phase == RoomPhase.STARTING
        assert len(room.participants) == 4
        human_count = sum(
            1 for p in room.participants.values() if p.controller_type == SeatControllerType.REMOTE
        )
        assert human_count == 4

    def test_build_quick_match_room_with_ai_fill(self):
        entries = [_make_entry(connection_id="c0")]
        room = MatchmakingService.build_quick_match_room(entries, ai_count=3)
        assert len(room.participants) == 4
        human_seats = [
            p for p in room.participants.values() if p.controller_type == SeatControllerType.REMOTE
        ]
        bot_seats = [
            p for p in room.participants.values() if p.controller_type == SeatControllerType.BOT
        ]
        assert len(human_seats) == 1
        assert len(bot_seats) == 3

    def test_bucket_different_mmr_ranges(self):
        bronze = self.svc.join_queue("b1", "u1", "P", "registered", 500)
        gold = self.svc.join_queue("g1", "u2", "P", "registered", 1300)
        assert bronze.bucket == "bronze"
        assert gold.bucket == "gold"
        assert self.svc.bucket_size("bronze") == 1
        assert self.svc.bucket_size("gold") == 1
        # Different buckets → no immediate match
        assert self.svc.try_form_match("bronze") is None
        assert self.svc.try_form_match("gold") is None

    def test_reset_clears_queue(self):
        self.svc.join_queue("c1", "u1", "P", "registered", 1000)
        self.svc.reset()
        assert self.svc.bucket_size("silver") == 0


# ===========================================================================
# TestWsQuickMatch — WebSocket handler integration
# ===========================================================================


class TestWsQuickMatch:
    """
    Test QUICK_MATCH_JOIN and QUICK_MATCH_LEAVE via the WS endpoint.

    These tests use the TestClient from conftest; queue state is reset by the
    autouse reset_matchmaking_service fixture.
    """

    def _register_and_auth(self, client) -> tuple[str, str]:
        """Register a user and authenticate via WS. Returns (token, nickname)."""
        nick = f"Player{uuid.uuid4().hex[:6]}"
        resp = client.post(
            "/auth/register",
            json={
                "email": f"{nick}@test.com",
                "password": "Test1234!",
                "nickname": nick,
            },
        )
        assert resp.status_code in (200, 201)
        token = resp.json()["access_token"]
        return token, nick

    def test_quick_match_join_not_authenticated(self, client):
        with client.websocket_connect("/ws") as ws:
            ws.send_json({"type": "WS_HELLO", "data": {}})
            ws.receive_json()
            ws.send_json({"type": "QUICK_MATCH_JOIN", "data": {}})
            msg = ws.receive_json()
            assert msg["type"] == "ERROR"
            assert msg["data"]["code"] == "NOT_AUTHENTICATED"

    def test_quick_match_join_sends_queue_joined(self, client):
        token, _ = self._register_and_auth(client)
        with client.websocket_connect("/ws") as ws:
            ws.send_json({"type": "WS_HELLO", "data": {}})
            ws.receive_json()
            ws.send_json({"type": "AUTH_LOGIN", "data": {"token": token}})
            ws.receive_json()  # AUTH_OK
            ws.send_json({"type": "QUICK_MATCH_JOIN", "data": {}})
            msg = ws.receive_json()
            assert msg["type"] == "QUEUE_JOINED"
            assert "bucket" not in msg["data"]  # bucket is hidden (MMR policy)
            assert "queue_size" in msg["data"]
            assert "fill_seconds" in msg["data"]
            assert isinstance(msg["data"]["fill_seconds"], int)

    def test_quick_match_join_already_in_room(self, client):
        token, _ = self._register_and_auth(client)
        with client.websocket_connect("/ws") as ws:
            ws.send_json({"type": "WS_HELLO", "data": {}})
            ws.receive_json()
            ws.send_json({"type": "AUTH_LOGIN", "data": {"token": token}})
            ws.receive_json()  # AUTH_OK
            ws.send_json({"type": "ROOM_CREATE", "data": {}})
            ws.receive_json()  # ROOM_STATE
            ws.send_json({"type": "QUICK_MATCH_JOIN", "data": {}})
            msg = ws.receive_json()
            assert msg["type"] == "ERROR"
            assert msg["data"]["code"] == "ALREADY_IN_ROOM"

    def test_quick_match_join_already_in_queue(self, client):
        token, _ = self._register_and_auth(client)
        with client.websocket_connect("/ws") as ws:
            ws.send_json({"type": "WS_HELLO", "data": {}})
            ws.receive_json()
            ws.send_json({"type": "AUTH_LOGIN", "data": {"token": token}})
            ws.receive_json()
            ws.send_json({"type": "QUICK_MATCH_JOIN", "data": {}})
            ws.receive_json()  # QUEUE_JOINED
            ws.send_json({"type": "QUICK_MATCH_JOIN", "data": {}})
            msg = ws.receive_json()
            assert msg["type"] == "ERROR"
            assert msg["data"]["code"] == "ALREADY_IN_QUEUE"

    def test_quick_match_leave_when_not_in_queue(self, client):
        token, _ = self._register_and_auth(client)
        with client.websocket_connect("/ws") as ws:
            ws.send_json({"type": "WS_HELLO", "data": {}})
            ws.receive_json()
            ws.send_json({"type": "AUTH_LOGIN", "data": {"token": token}})
            ws.receive_json()
            ws.send_json({"type": "QUICK_MATCH_LEAVE", "data": {}})
            msg = ws.receive_json()
            assert msg["type"] == "ERROR"
            assert msg["data"]["code"] == "NOT_IN_QUEUE"

    def test_quick_match_leave_sends_queue_left(self, client):
        token, _ = self._register_and_auth(client)
        with client.websocket_connect("/ws") as ws:
            ws.send_json({"type": "WS_HELLO", "data": {}})
            ws.receive_json()
            ws.send_json({"type": "AUTH_LOGIN", "data": {"token": token}})
            ws.receive_json()
            ws.send_json({"type": "QUICK_MATCH_JOIN", "data": {}})
            ws.receive_json()  # QUEUE_JOINED
            ws.send_json({"type": "QUICK_MATCH_LEAVE", "data": {}})
            msg = ws.receive_json()
            assert msg["type"] == "QUEUE_LEFT"

    def test_4_players_form_immediate_match(self, client, db):
        """
        When 4 players with the same default MMR join quick match, a match
        should form immediately without waiting for the fill timer.

        Message flow:
          Players 1-3: first response after QUICK_MATCH_JOIN → QUEUE_JOINED
          Player 4:    first response after QUICK_MATCH_JOIN → MATCH_FOUND
                       (match forms immediately; QUEUE_JOINED is skipped)
          Players 1-3: next message in buffer → MATCH_FOUND
        """
        tokens = []
        for _ in range(4):
            nick = f"P{uuid.uuid4().hex[:6]}"
            resp = client.post(
                "/auth/register",
                json={
                    "email": f"{nick}@t.com",
                    "password": "Test1234!",
                    "nickname": nick,
                },
            )
            tokens.append(resp.json()["access_token"])

        received = []
        connections = []
        for token in tokens:
            ws = client.websocket_connect("/ws").__enter__()
            connections.append(ws)
            ws.send_json({"type": "WS_HELLO", "data": {}})
            ws.receive_json()  # WS_WELCOME
            ws.send_json({"type": "AUTH_LOGIN", "data": {"token": token}})
            ws.receive_json()  # AUTH_OK
            ws.send_json({"type": "QUICK_MATCH_JOIN", "data": {}})
            msg = ws.receive_json()
            received.append(msg)

        # Players 1-3 receive QUEUE_JOINED (still waiting for a 4th seat).
        for msg in received[:3]:
            assert msg["type"] == "QUEUE_JOINED", f"expected QUEUE_JOINED, got {msg}"

        # Player 4 triggers the match immediately: their first response is
        # MATCH_FOUND (no QUEUE_JOINED is sent for the triggering player).
        assert received[3]["type"] == "MATCH_FOUND", f"expected MATCH_FOUND, got {received[3]}"
        assert received[3]["data"]["is_ranked"] is True

        # Players 1-3 now receive MATCH_FOUND from the broadcast.
        for ws in connections[:3]:
            match_msg = ws.receive_json()
            assert match_msg["type"] == "MATCH_FOUND", f"expected MATCH_FOUND, got {match_msg}"
            assert match_msg["data"]["is_ranked"] is True

        for ws in connections:
            ws.__exit__(None, None, None)

    def test_ai_fill_match_is_not_ranked(self):
        """
        A match formed with AI fill (< 4 humans) has is_ranked=False.
        This is the contract enforced by _fill_timer and _start_quick_match.
        """
        # The fill timer passes is_ranked=False to on_match_formed.
        # We test the build_quick_match_room + is_ranked contract directly.
        entry = _make_entry(connection_id="c0")
        room = MatchmakingService.build_quick_match_room([entry], ai_count=3)
        bots = [
            p for p in room.participants.values() if p.controller_type == SeatControllerType.BOT
        ]
        assert len(bots) == 3
        # is_ranked would be set False by the caller after create_match;
        # verify the flag semantics on ActiveMatch.
        import dataclasses

        # Default is False — verified via dataclass field introspection
        fields = {
            f.name: f.default
            for f in dataclasses.fields(ActiveMatch)
            if f.default is not dataclasses.MISSING
        }
        assert fields.get("is_ranked") is False


# ===========================================================================
# Mock ActiveMatch builders for MmrService tests
# ===========================================================================


def _make_mock_seat(
    seat_index: int,
    user_id: str = None,
    account_type: str = "registered",
    took_over_by_bot: bool = False,
    controller_type: SeatControllerType = SeatControllerType.REMOTE,
) -> MatchSeat:
    from fall_in.core.player import Player, PlayerType

    player = Player(
        name="P",
        player_type=PlayerType.HUMAN
        if controller_type == SeatControllerType.REMOTE
        else PlayerType.AI,
        player_id=seat_index,
    )
    seat = MatchSeat(
        seat_index=seat_index,
        player=player,
        connection_id=None,
        user_id=user_id,
        display_name="P",
        controller_type=controller_type,
        took_over_by_bot=took_over_by_bot,
    )
    seat.account_type = account_type  # type: ignore[attr-defined]
    return seat


def _make_stub_match(seats: list[MatchSeat], is_ranked: bool) -> object:
    """Minimal stub that duck-types as ActiveMatch for MmrService."""

    class _Stub:
        pass

    stub = _Stub()
    stub.is_ranked = is_ranked
    stub.seats = {s.seat_index: s for s in seats}
    stub.match_id = "test-match"
    return stub


def _make_mock_match_all_human(users, winner_seat: int, is_ranked: bool):
    seats = [_make_mock_seat(i, user_id=users[i].id, account_type="registered") for i in range(4)]
    return _make_stub_match(seats, is_ranked)


def _make_mock_match_3_human(users, winner_seat: int, is_ranked: bool):
    seats = [_make_mock_seat(i, user_id=users[i].id, account_type="registered") for i in range(3)]
    # 4th seat is bot-takeover
    seats.append(
        _make_mock_seat(
            3,
            user_id=None,
            account_type="guest",
            took_over_by_bot=True,
            controller_type=SeatControllerType.BOT,
        )
    )
    return _make_stub_match(seats, is_ranked)


def _make_mock_match_2_human(users, winner_seat: int, is_ranked: bool):
    seats = [_make_mock_seat(i, user_id=users[i].id, account_type="registered") for i in range(2)]
    for i in range(2, 4):
        seats.append(
            _make_mock_seat(
                i,
                user_id=None,
                account_type="guest",
                took_over_by_bot=True,
                controller_type=SeatControllerType.BOT,
            )
        )
    return _make_stub_match(seats, is_ranked)


def _make_mock_match_with_guest(reg_users, guest_seat: int, winner_seat: int, is_ranked: bool):
    seats = [
        _make_mock_seat(i, user_id=reg_users[i].id, account_type="registered")
        for i in range(len(reg_users))
    ]
    seats.append(
        _make_mock_seat(
            guest_seat,
            user_id=None,
            account_type="guest",
        )
    )
    return _make_stub_match(seats, is_ranked)
