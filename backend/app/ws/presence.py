"""
PresenceManager — heartbeat, reconnect token management, grace-period and
card-selection-timeout coordination.

Responsibilities
----------------
* Issue and revoke reconnect tokens (via the injected ReconnectRepo).
* Start/cancel per-seat grace-period asyncio tasks.
  On expiry → call MatchService.takeover_seat() and broadcast SEAT_BOT_TAKEOVER.
* Start/cancel per-match card-selection-timeout asyncio tasks.
  On expiry → call MatchService.auto_select_timed_out() and broadcast
  SELECTION_TIMEOUT, then resolve the turn if all seats have now selected.

The actual turn-resolution logic lives in handler.py; callers pass it in as
an async callback (``on_turn_ready``) so this module stays free of handler
imports (avoiding circular imports).

Thread safety
-------------
All asyncio.Tasks are created on the running event loop.  reset() cancels
every pending task before clearing state, so test isolation is preserved even
when tasks are still sleeping.
"""

from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Callable, Optional

from app.config import settings
from app.repositories.reconnect_repo import ReconnectEntry


class PresenceManager:
    def __init__(self, reconnect_repo: Any) -> None:
        self._repo = reconnect_repo  # InMemoryReconnectRepo | RedisReconnectRepo
        # f"{match_id}:{seat_index}" -> asyncio.Task
        self._grace_tasks: dict[str, asyncio.Task] = {}
        # match_id -> asyncio.Task
        self._selection_tasks: dict[str, asyncio.Task] = {}

    # ------------------------------------------------------------------
    # Reconnect token management
    # ------------------------------------------------------------------

    def issue_token(
        self,
        match_id: str,
        room_code: str,
        seat_index: int,
        user_id: Optional[str],
        display_name: str,
        account_type: str,
    ) -> str:
        """
        Generate and store a reconnect token for one human seat.

        TTL is 4× the grace period so the token remains valid across several
        reconnect attempts during the grace window.
        """
        return self._repo.create(
            match_id=match_id,
            room_code=room_code,
            seat_index=seat_index,
            user_id=user_id,
            display_name=display_name,
            account_type=account_type,
            ttl_seconds=settings.RECONNECT_GRACE_SECONDS * 4,
        )

    def lookup_token(self, token: str) -> Optional[ReconnectEntry]:
        return self._repo.get(token)

    def revoke_seat_token(self, match_id: str, seat_index: int) -> None:
        self._repo.revoke_by_match_seat(match_id, seat_index)

    def revoke_match_tokens(self, match_id: str) -> None:
        """Invalidate all tokens for a finished match."""
        self._repo.revoke_by_match(match_id)

    # ------------------------------------------------------------------
    # Grace-period timer (disconnect → bot takeover)
    # ------------------------------------------------------------------

    def start_grace_timer(
        self,
        match_id: str,
        seat_index: int,
        match: Any,
        match_service: Any,
        room_service: Any,
        manager: Any,
        room_code: str,
        on_turn_ready: Callable[[str, Any], Awaitable[None]],
    ) -> None:
        """
        Start a RECONNECT_GRACE_SECONDS timer for a disconnected seat.

        If the timer fires without the seat reconnecting, the seat is
        permanently converted to bot control and SEAT_BOT_TAKEOVER is broadcast.
        Both the match seat and the room participant are updated so that
        room-level human-count checks remain accurate.
        If the takeover causes all remaining seats to have selected, the turn
        is resolved via *on_turn_ready*.
        """
        key = f"{match_id}:{seat_index}"
        self._cancel_task(self._grace_tasks, key)
        self._grace_tasks[key] = asyncio.create_task(
            self._grace_timer(
                key,
                match_id,
                seat_index,
                match,
                match_service,
                room_service,
                manager,
                room_code,
                on_turn_ready,
            )
        )

    def cancel_grace_timer(self, match_id: str, seat_index: int) -> None:
        self._cancel_task(self._grace_tasks, f"{match_id}:{seat_index}")

    async def _grace_timer(
        self,
        key: str,
        match_id: str,
        seat_index: int,
        match: Any,
        match_service: Any,
        room_service: Any,
        manager: Any,
        room_code: str,
        on_turn_ready: Callable[[str, Any], Awaitable[None]],
    ) -> None:
        try:
            await asyncio.sleep(settings.RECONNECT_GRACE_SECONDS)

            # Verify match is still active in the repo.
            if match_service.get_match(match_id) is None:
                return

            seat = match.seats.get(seat_index)
            if seat is None or seat.took_over_by_bot or not seat.is_disconnected:
                return  # already reconnected or already taken over

            # Grace expired — permanently convert to bot in both match and room.
            match_service.takeover_seat(match, seat_index)
            # Sync room participant so human-count checks remain correct.
            room_service.mark_participant_bot_takeover(room_code, seat_index)
            self._repo.revoke_by_match_seat(match_id, seat_index)

            await manager.broadcast_to_room(
                room_code,
                {
                    "type": "SEAT_BOT_TAKEOVER",
                    "data": {"seat_index": seat_index},
                },
            )

            # Cancel any outstanding selection timeout; the bot just selected.
            self.cancel_selection_timeout(match_id)

            # If takeover completed the last pending selection, resolve the turn.
            if match_service.all_selected(match):
                await on_turn_ready(room_code, match)
        except asyncio.CancelledError:
            pass
        finally:
            self._grace_tasks.pop(key, None)

    # ------------------------------------------------------------------
    # Card-selection timeout
    # ------------------------------------------------------------------

    def start_selection_timeout(
        self,
        match_id: str,
        match: Any,
        match_service: Any,
        manager: Any,
        room_code: str,
        on_turn_ready: Callable[[str, Any], Awaitable[None]],
    ) -> None:
        """
        Start a CARD_SELECTION_TIMEOUT_SECONDS timer for the current turn.

        On expiry, any non-eliminated REMOTE seat that hasn't selected yet
        has a card chosen for it by bot logic, then the turn is resolved if
        all seats are now ready.
        """
        self._cancel_task(self._selection_tasks, match_id)
        self._selection_tasks[match_id] = asyncio.create_task(
            self._selection_timer(
                match_id,
                match,
                match_service,
                manager,
                room_code,
                on_turn_ready,
            )
        )

    def cancel_selection_timeout(self, match_id: str) -> None:
        self._cancel_task(self._selection_tasks, match_id)

    async def _selection_timer(
        self,
        match_id: str,
        match: Any,
        match_service: Any,
        manager: Any,
        room_code: str,
        on_turn_ready: Callable[[str, Any], Awaitable[None]],
    ) -> None:
        try:
            await asyncio.sleep(settings.CARD_SELECTION_TIMEOUT_SECONDS)

            if match_service.get_match(match_id) is None:
                return

            timed_out = match_service.auto_select_timed_out(match)
            if timed_out:
                await manager.broadcast_to_room(
                    room_code,
                    {
                        "type": "SELECTION_TIMEOUT",
                        "data": {"timed_out_seats": timed_out},
                    },
                )

            if match_service.all_selected(match):
                await on_turn_ready(room_code, match)
        except asyncio.CancelledError:
            pass
        finally:
            self._selection_tasks.pop(match_id, None)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def reset(self) -> None:
        """
        Cancel all pending tasks and clear stored state.

        Called between tests to prevent task leakage.  Also clears the
        underlying token repo so test runs see a fresh store.
        """
        for task in list(self._grace_tasks.values()):
            if not task.done():
                task.cancel()
        for task in list(self._selection_tasks.values()):
            if not task.done():
                task.cancel()
        self._grace_tasks.clear()
        self._selection_tasks.clear()
        self._repo.clear()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _cancel_task(self, tasks: dict, key: str) -> None:
        task = tasks.pop(key, None)
        if task and not task.done():
            task.cancel()


# ---------------------------------------------------------------------------
# Module-level singleton — shared by the WS endpoint and handler.
# Tests override it via the reset_presence_manager fixture.
# ---------------------------------------------------------------------------

from app.config import settings as _settings  # noqa: E402 (already imported above)
from app.repositories.reconnect_repo import make_reconnect_repo  # noqa: E402

_reconnect_repo = make_reconnect_repo(_settings.REDIS_URL)
presence_manager = PresenceManager(_reconnect_repo)
