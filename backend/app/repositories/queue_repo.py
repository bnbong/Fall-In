"""
Quick-match queue storage.

Two implementations are provided:

  InMemoryQueueRepo  — default, single-process, no external deps.
                       Used automatically when REDIS_URL is not set.

  RedisQueueRepo     — production-grade, survives worker restarts.
                       Requires ``redis[hiredis]`` package.
                       Activated when REDIS_URL is set in config.

The public factory ``make_queue_repo(redis_url)`` selects the right
implementation and falls back to in-memory if Redis is unreachable.

Queue entry lifecycle:
  1. Added when a player sends QUICK_MATCH_JOIN.
  2. Removed when 4 entries accumulate (match formed), the fill timer fires,
     or the player sends QUICK_MATCH_LEAVE / disconnects.

Entries are ordered by ``joined_at`` so that the longest-waiting players
are matched first.
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class QueueEntry:
    """All fields needed to seat a queued player in a quick-match lobby."""

    connection_id: str
    user_id: Optional[str]  # None for guests
    display_name: str
    account_type: str  # "registered" | "guest"
    mmr: int  # hidden MMR (DEFAULT_MMR for guests)
    bucket: str  # MMR bucket name used for grouping
    joined_at: float  # time.time() when the player entered the queue


# ---------------------------------------------------------------------------
# In-memory implementation
# ---------------------------------------------------------------------------


class InMemoryQueueRepo:
    def __init__(self) -> None:
        # bucket -> list[QueueEntry], insertion-ordered
        self._buckets: dict[str, list[QueueEntry]] = {}
        # connection_id -> bucket  (reverse index for O(1) removal)
        self._conn_bucket: dict[str, str] = {}

    def add(self, entry: QueueEntry) -> None:
        bucket = entry.bucket
        if bucket not in self._buckets:
            self._buckets[bucket] = []
        self._buckets[bucket].append(entry)
        self._conn_bucket[entry.connection_id] = bucket

    def remove(self, connection_id: str) -> Optional[QueueEntry]:
        """Remove and return the entry for *connection_id*, or None if absent."""
        bucket = self._conn_bucket.pop(connection_id, None)
        if bucket is None:
            return None
        entries = self._buckets.get(bucket, [])
        for i, e in enumerate(entries):
            if e.connection_id == connection_id:
                entries.pop(i)
                if not entries:
                    self._buckets.pop(bucket, None)
                return e
        return None

    def get_bucket(self, bucket: str) -> list[QueueEntry]:
        """Return all entries in *bucket* sorted by joined_at (oldest first)."""
        return sorted(self._buckets.get(bucket, []), key=lambda e: e.joined_at)

    def bucket_size(self, bucket: str) -> int:
        return len(self._buckets.get(bucket, []))

    def get_entry(self, connection_id: str) -> Optional[QueueEntry]:
        bucket = self._conn_bucket.get(connection_id)
        if bucket is None:
            return None
        for e in self._buckets.get(bucket, []):
            if e.connection_id == connection_id:
                return e
        return None

    def clear(self) -> None:
        self._buckets.clear()
        self._conn_bucket.clear()


# ---------------------------------------------------------------------------
# Redis implementation (optional)
# ---------------------------------------------------------------------------


class RedisQueueRepo:
    """
    Redis-backed queue store.  Requires ``redis[hiredis]``.

    Per-bucket sorted set: ``fall_in:queue:{bucket}``  (score = joined_at)
    Per-entry hash:        ``fall_in:queue:entry:{connection_id}``

    SINGLE-WORKER ONLY
    ------------------
    This implementation shares the queue across processes, but the rest of the
    match-formation stack (ConnectionManager, InMemoryRoomRepo, InMemoryMatchRepo)
    is process-local.  Running multiple workers with REDIS_URL set will cause
    workers to dequeue connections they do not own, so those players will never
    receive MATCH_FOUND.

    Do NOT use REDIS_URL in a multi-worker deployment until ConnectionManager,
    room_repo, and match_repo are also backed by a shared store with atomic
    match-formation operations.  Single-worker deployments (single uvicorn
    process or single Gunicorn worker) are safe.
    """

    _PREFIX = "fall_in:queue:"
    # Entries expire automatically after 10 min so stale data does not
    # accumulate when a worker crashes mid-queue.
    _ENTRY_TTL = 600

    def __init__(self, redis_url: str) -> None:
        import redis as _redis

        self._r = _redis.from_url(redis_url, decode_responses=True)

    def ping(self) -> None:
        self._r.ping()

    def _bucket_key(self, bucket: str) -> str:
        return f"{self._PREFIX}{bucket}"

    def _entry_key(self, connection_id: str) -> str:
        return f"{self._PREFIX}entry:{connection_id}"

    def add(self, entry: QueueEntry) -> None:
        pipe = self._r.pipeline()
        pipe.zadd(self._bucket_key(entry.bucket), {entry.connection_id: entry.joined_at})
        mapping = {
            "connection_id": entry.connection_id,
            "user_id": entry.user_id or "",
            "display_name": entry.display_name,
            "account_type": entry.account_type,
            "mmr": str(entry.mmr),
            "bucket": entry.bucket,
            "joined_at": str(entry.joined_at),
        }
        pipe.hset(self._entry_key(entry.connection_id), mapping=mapping)
        pipe.expire(self._entry_key(entry.connection_id), self._ENTRY_TTL)
        pipe.execute()

    def remove(self, connection_id: str) -> Optional[QueueEntry]:
        entry = self.get_entry(connection_id)
        if entry is None:
            return None
        pipe = self._r.pipeline()
        pipe.zrem(self._bucket_key(entry.bucket), connection_id)
        pipe.delete(self._entry_key(connection_id))
        pipe.execute()
        return entry

    def get_bucket(self, bucket: str) -> list[QueueEntry]:
        # ZRANGEBYSCORE -inf +inf WITHSCORES; sorted by score (joined_at)
        members = self._r.zrange(self._bucket_key(bucket), 0, -1)
        entries = []
        for conn_id in members:
            e = self.get_entry(conn_id)
            if e is not None:
                entries.append(e)
        return sorted(entries, key=lambda e: e.joined_at)

    def bucket_size(self, bucket: str) -> int:
        return self._r.zcard(self._bucket_key(bucket))

    def get_entry(self, connection_id: str) -> Optional[QueueEntry]:
        data = self._r.hgetall(self._entry_key(connection_id))
        if not data:
            return None
        return QueueEntry(
            connection_id=data["connection_id"],
            user_id=data["user_id"] or None,
            display_name=data["display_name"],
            account_type=data["account_type"],
            mmr=int(data["mmr"]),
            bucket=data["bucket"],
            joined_at=float(data["joined_at"]),
        )

    def clear(self) -> None:
        """Flush all queue keys.  Use only in tests."""
        keys = self._r.keys(f"{self._PREFIX}*")
        if keys:
            self._r.delete(*keys)


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def make_queue_repo(
    redis_url: Optional[str] = None,
) -> InMemoryQueueRepo:
    """
    Return a Redis-backed repo if redis_url is set and reachable,
    otherwise fall back to the in-memory implementation.

    WARNING: RedisQueueRepo is only safe with a *single* uvicorn/Gunicorn
    worker process.  See the RedisQueueRepo docstring for details.
    """
    if redis_url:
        try:
            repo = RedisQueueRepo(redis_url)
            repo.ping()
            return repo  # type: ignore[return-value]
        except Exception as exc:
            import warnings

            warnings.warn(
                f"Redis connection failed ({exc}); falling back to in-memory quick-match queue.",
                stacklevel=2,
            )
    return InMemoryQueueRepo()
