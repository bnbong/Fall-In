"""
Quick-match matchmaking service (PR-06).

Responsibilities
----------------
* Accept QUICK_MATCH_JOIN requests and place players into per-bucket queues.
* Immediately form a match when a bucket reaches 4 players.
* Start a per-bucket fill timer (QUICK_MATCH_FILL_SECONDS) when the first
  player enters; on expiry, fill remaining seats with AI bots and start the
  match regardless of queue size.
* Remove players from the queue on QUICK_MATCH_LEAVE or WebSocket disconnect.

Match formation
---------------
When 4 players are ready (either 4 humans or humans + AI fill), the service:
  1. Builds an in-memory Room in STARTING phase (no lobby hand-shake needed).
  2. Calls MatchService.create_match() to deal cards and auto-select bots.
  3. Sets match.is_ranked = True (all-human start) or False (AI fill).
  4. Issues a RECONNECT_TOKEN to each human seat via PresenceManager.
  5. Broadcasts MATCH_FOUND + MATCH_START + PHASE_SELECTING to all human
     connections via ConnectionManager.

The ``on_match_formed`` callback is passed by the WS endpoint so that the
actual broadcast work (which requires an async context) happens in the
correct event loop.  This avoids circular imports between handler and service.

Thread safety
-------------
All asyncio.Tasks are created on the running event loop.  reset() cancels
every pending task before clearing state so test isolation is preserved.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from typing import Any, Awaitable, Callable, Optional

from app.config import settings
from app.models.room import Room, RoomParticipant, RoomPhase, SeatControllerType
from app.repositories.queue_repo import QueueEntry

# Callback type: async (human_entries, ai_count, is_ranked) -> None
OnMatchFormed = Callable[[list[QueueEntry], int, bool], Awaitable[None]]


class MatchmakingService:
    def __init__(self, queue_repo: Any) -> None:
        self._repo = queue_repo  # InMemoryQueueRepo | RedisQueueRepo
        # bucket -> fill asyncio.Task
        self._fill_tasks: dict[str, asyncio.Task] = {}

    # ------------------------------------------------------------------
    # MMR → Bucket
    # ------------------------------------------------------------------

    @staticmethod
    def get_bucket(mmr: int) -> str:
        """Map MMR to a bucket name used for queue grouping."""
        from app.services.mmr_service import mmr_to_bucket

        return mmr_to_bucket(mmr)

    # ------------------------------------------------------------------
    # Queue entry / exit
    # ------------------------------------------------------------------

    def join_queue(
        self,
        connection_id: str,
        user_id: Optional[str],
        display_name: str,
        account_type: str,
        mmr: int,
    ) -> QueueEntry:
        """
        Add a player to the appropriate bucket queue.

        Returns the created QueueEntry.  The caller should then call
        try_form_match() to check for an immediate 4-player match, and
        start_fill_timer() if one wasn't formed.
        """
        bucket = self.get_bucket(mmr)
        entry = QueueEntry(
            connection_id=connection_id,
            user_id=user_id,
            display_name=display_name,
            account_type=account_type,
            mmr=mmr,
            bucket=bucket,
            joined_at=time.time(),
        )
        self._repo.add(entry)
        return entry

    def leave_queue(self, connection_id: str) -> Optional[QueueEntry]:
        """
        Remove a player from the queue.

        Returns the removed QueueEntry, or None if the player was not queued.
        Call cancel_fill_timer() afterwards if the bucket is now empty.
        """
        return self._repo.remove(connection_id)

    def get_entry(self, connection_id: str) -> Optional[QueueEntry]:
        return self._repo.get_entry(connection_id)

    def bucket_size(self, bucket: str) -> int:
        return self._repo.bucket_size(bucket)

    # ------------------------------------------------------------------
    # Immediate match formation (4 humans ready)
    # ------------------------------------------------------------------

    def try_form_match(self, bucket: str) -> Optional[list[QueueEntry]]:
        """
        If >= 4 players are in *bucket*, pop the first 4 and return them.

        Returns None if fewer than 4 players are waiting.
        The caller is responsible for cancelling the fill timer for this bucket.
        """
        entries = self._repo.get_bucket(bucket)
        if len(entries) < 4:
            return None
        four = entries[:4]
        for e in four:
            self._repo.remove(e.connection_id)
        return four

    # ------------------------------------------------------------------
    # Fill timer (20-second AI fallback)
    # ------------------------------------------------------------------

    def start_fill_timer(
        self,
        bucket: str,
        on_match_formed: OnMatchFormed,
    ) -> None:
        """
        Start the fill timer for *bucket* if one is not already running.

        On expiry, whatever humans are in the bucket (1–3) are matched with
        AI bots to fill the remaining seats.
        """
        if bucket in self._fill_tasks and not self._fill_tasks[bucket].done():
            return  # timer already running
        self._fill_tasks[bucket] = asyncio.create_task(self._fill_timer(bucket, on_match_formed))

    def cancel_fill_timer(self, bucket: str) -> None:
        task = self._fill_tasks.pop(bucket, None)
        if task and not task.done():
            task.cancel()

    async def _fill_timer(
        self,
        bucket: str,
        on_match_formed: OnMatchFormed,
    ) -> None:
        try:
            await asyncio.sleep(settings.QUICK_MATCH_FILL_SECONDS)

            entries = self._repo.get_bucket(bucket)
            if not entries:
                return  # everyone left before timer fired

            # Pop all waiting players (1–3); fill rest with AI.
            human_entries = entries[:4]
            for e in human_entries:
                self._repo.remove(e.connection_id)

            ai_count = 4 - len(human_entries)
            # AI-fill match: not ranked (MMR not updated).
            is_ranked = False
            await on_match_formed(human_entries, ai_count, is_ranked)
        except asyncio.CancelledError:
            pass
        finally:
            self._fill_tasks.pop(bucket, None)

    # ------------------------------------------------------------------
    # Room / Match scaffolding helpers
    # ------------------------------------------------------------------

    @staticmethod
    def build_quick_match_room(
        human_entries: list[QueueEntry],
        ai_count: int,
    ) -> Room:
        """
        Build an in-memory Room in STARTING phase from queue entries.

        Human entries occupy the first N seats (0…N-1).
        AI bots fill the remaining seats.
        """
        room_code = f"QM-{uuid.uuid4().hex[:8].upper()}"
        participants: dict[int, RoomParticipant] = {}

        for seat_idx, entry in enumerate(human_entries):
            participants[seat_idx] = RoomParticipant(
                seat_index=seat_idx,
                display_name=entry.display_name,
                controller_type=SeatControllerType.REMOTE,
                is_ready=True,
                account_type=entry.account_type,
                user_id=entry.user_id,
                connection_id=entry.connection_id,
            )

        for i in range(ai_count):
            seat_idx = len(human_entries) + i
            participants[seat_idx] = RoomParticipant(
                seat_index=seat_idx,
                display_name=f"AI Bot {seat_idx + 1}",
                controller_type=SeatControllerType.BOT,
                is_ready=True,
                account_type="bot",
                user_id=None,
                connection_id=None,
            )

        return Room(
            room_code=room_code,
            host_seat_index=0,
            phase=RoomPhase.STARTING,
            participants=participants,
        )

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def reset(self) -> None:
        """Cancel all pending tasks and clear queue state.  Called between tests."""
        for task in list(self._fill_tasks.values()):
            if not task.done():
                task.cancel()
        self._fill_tasks.clear()
        self._repo.clear()


# ---------------------------------------------------------------------------
# Module-level singleton — shared by the WS endpoint and handler.
# Tests override it via the reset_matchmaking_service fixture.
# ---------------------------------------------------------------------------

from app.config import settings as _settings  # noqa: E402
from app.repositories.queue_repo import make_queue_repo  # noqa: E402

_queue_repo = make_queue_repo(_settings.REDIS_URL)
matchmaking_service = MatchmakingService(_queue_repo)
