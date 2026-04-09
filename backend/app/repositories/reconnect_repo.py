"""
Reconnect token storage.

Two implementations are provided:

  InMemoryReconnectRepo  — default, single-process, no external deps.
                           Used automatically when REDIS_URL is not set.

  RedisReconnectRepo     — production-grade, TTL expiry handled by Redis.
                           Requires ``redis[hiredis]`` package.
                           Activated when REDIS_URL is set in config.

The public factory ``make_reconnect_repo(redis_url)`` selects the right
implementation and falls back to the in-memory version if the Redis
connection fails, so the server remains functional without Redis in local
development.

Token lifecycle:
  1. Created at match start (one per human seat).
  2. Looked up on RECONNECT; expired/missing tokens are rejected.
  3. Revoked on: bot takeover, match end, or explicit invalidation.

TTL = RECONNECT_GRACE_SECONDS * 4  so the token outlives the grace window
even if the client takes a few reconnect attempts.
"""

import time
import uuid
from dataclasses import dataclass
from typing import Optional


@dataclass
class ReconnectEntry:
    """All fields needed to restore a WsSession on reconnect."""

    token: str
    match_id: str
    room_code: str
    seat_index: int
    user_id: Optional[str]
    display_name: str
    account_type: str  # "registered" | "guest"
    expires_at: float  # absolute time.time() deadline


# ---------------------------------------------------------------------------
# In-memory implementation
# ---------------------------------------------------------------------------


class InMemoryReconnectRepo:
    def __init__(self) -> None:
        self._tokens: dict[str, ReconnectEntry] = {}

    def create(
        self,
        match_id: str,
        room_code: str,
        seat_index: int,
        user_id: Optional[str],
        display_name: str,
        account_type: str,
        ttl_seconds: int,
    ) -> str:
        # Invalidate any existing token for this (match, seat) pair first.
        self.revoke_by_match_seat(match_id, seat_index)
        token = str(uuid.uuid4())
        self._tokens[token] = ReconnectEntry(
            token=token,
            match_id=match_id,
            room_code=room_code,
            seat_index=seat_index,
            user_id=user_id,
            display_name=display_name,
            account_type=account_type,
            expires_at=time.time() + ttl_seconds,
        )
        return token

    def get(self, token: str) -> Optional[ReconnectEntry]:
        entry = self._tokens.get(token)
        if entry is None:
            return None
        if time.time() > entry.expires_at:
            self._tokens.pop(token, None)
            return None
        return entry

    def revoke_by_match_seat(self, match_id: str, seat_index: int) -> None:
        to_delete = [
            t
            for t, e in self._tokens.items()
            if e.match_id == match_id and e.seat_index == seat_index
        ]
        for t in to_delete:
            self._tokens.pop(t, None)

    def revoke_by_match(self, match_id: str) -> None:
        to_delete = [t for t, e in self._tokens.items() if e.match_id == match_id]
        for t in to_delete:
            self._tokens.pop(t, None)

    def clear(self) -> None:
        self._tokens.clear()


# ---------------------------------------------------------------------------
# Redis implementation (optional)
# ---------------------------------------------------------------------------


class RedisReconnectRepo:
    """
    Redis-backed token store.  Requires ``redis[hiredis]``.

    Tokens are stored as Redis hashes under ``fall_in:reconnect:<token>``.
    A reverse index at ``fall_in:reconnect:seat:<match_id>:<seat>`` maps a
    seat back to its current token so revoke_by_match_seat is O(1).
    """

    _PREFIX = "fall_in:reconnect:"

    def __init__(self, redis_url: str) -> None:
        import redis as _redis  # optional dependency

        self._r = _redis.from_url(redis_url, decode_responses=True)

    def ping(self) -> None:
        """Raise if Redis is unreachable (used by factory for health check)."""
        self._r.ping()

    def _token_key(self, token: str) -> str:
        return f"{self._PREFIX}{token}"

    def _seat_key(self, match_id: str, seat_index: int) -> str:
        return f"{self._PREFIX}seat:{match_id}:{seat_index}"

    def create(
        self,
        match_id: str,
        room_code: str,
        seat_index: int,
        user_id: Optional[str],
        display_name: str,
        account_type: str,
        ttl_seconds: int,
    ) -> str:
        self.revoke_by_match_seat(match_id, seat_index)
        token = str(uuid.uuid4())
        expires_at = time.time() + ttl_seconds
        mapping = {
            "token": token,
            "match_id": match_id,
            "room_code": room_code,
            "seat_index": str(seat_index),
            "user_id": user_id or "",
            "display_name": display_name,
            "account_type": account_type,
            "expires_at": str(expires_at),
        }
        pipe = self._r.pipeline()
        pipe.hset(self._token_key(token), mapping=mapping)
        pipe.expire(self._token_key(token), ttl_seconds + 60)
        pipe.setex(self._seat_key(match_id, seat_index), ttl_seconds + 60, token)
        pipe.execute()
        return token

    def get(self, token: str) -> Optional[ReconnectEntry]:
        data = self._r.hgetall(self._token_key(token))
        if not data:
            return None
        expires_at = float(data["expires_at"])
        if time.time() > expires_at:
            self._r.delete(self._token_key(token))
            return None
        return ReconnectEntry(
            token=token,
            match_id=data["match_id"],
            room_code=data["room_code"],
            seat_index=int(data["seat_index"]),
            user_id=data["user_id"] or None,
            display_name=data["display_name"],
            account_type=data["account_type"],
            expires_at=expires_at,
        )

    def revoke_by_match_seat(self, match_id: str, seat_index: int) -> None:
        seat_key = self._seat_key(match_id, seat_index)
        old_token = self._r.get(seat_key)
        if old_token:
            self._r.delete(self._token_key(old_token))
            self._r.delete(seat_key)

    def revoke_by_match(self, match_id: str) -> None:
        for seat_idx in range(4):
            self.revoke_by_match_seat(match_id, seat_idx)

    def clear(self) -> None:
        """Flush all keys with our prefix.  Use only in tests."""
        keys = self._r.keys(f"{self._PREFIX}*")
        if keys:
            self._r.delete(*keys)


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def make_reconnect_repo(
    redis_url: Optional[str] = None,
) -> InMemoryReconnectRepo:  # return type is the base duck-type
    """
    Return a Redis-backed repo if redis_url is set and reachable,
    otherwise fall back to the in-memory implementation.
    """
    if redis_url:
        try:
            repo = RedisReconnectRepo(redis_url)
            repo.ping()
            return repo  # type: ignore[return-value]
        except Exception as exc:
            import warnings

            warnings.warn(
                f"Redis connection failed ({exc}); "
                "falling back to in-memory reconnect token store.",
                stacklevel=2,
            )
    return InMemoryReconnectRepo()
