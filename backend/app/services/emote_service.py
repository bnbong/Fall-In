"""
Emote broadcast service (PR-07).

Responsibilities
----------------
* Validate that an emote_id belongs to the fixed permitted catalog.
* Enforce per-connection rate limits (all values from settings):
    - Cooldown: EMOTE_COOLDOWN_SECONDS (1.5 s) between any two emotes.
    - Burst cap: at most EMOTE_BURST_CAP (3) emotes within
      EMOTE_BURST_WINDOW_SECONDS (10 s) sliding window.
    - Same-emote soft block: more than EMOTE_SAME_REPEAT_CAP (2) consecutive
      sends of the identical slug are denied until a different emote is sent.
* Provide reset() for test isolation.

No broadcast or session logic lives here — the WS handler is responsible
for fanout and mute filtering.

Emote catalog
-------------
Emotes are identified by a short ASCII slug.  The client maps these to
emoji / images.  The server only validates the slug — it never stores or
renders it.

Permitted slugs:
  thumbsup   👍   좋아요
  thumbsdown 👎   별로
  smile      😄   웃음
  sweat      😅   땀
  thinking   🤔   생각
  fire       🔥   열정
  cry        😭   눈물
  clap       👏   박수
"""

from __future__ import annotations

import time

from app.config import settings

# ---------------------------------------------------------------------------
# Catalog
# ---------------------------------------------------------------------------

VALID_EMOTE_IDS: frozenset[str] = frozenset(
    {
        "thumbsup",
        "thumbsdown",
        "smile",
        "sweat",
        "thinking",
        "fire",
        "cry",
        "clap",
    }
)


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class EmoteService:
    """
    Stateful rate-limit tracker for emote broadcasts.

    One instance is shared for the entire server process.  All state is
    keyed by connection_id so there is no per-user persistence.
    State is cleared between tests via reset().
    """

    def __init__(self) -> None:
        # connection_id -> timestamp of the most recent allowed emote
        self._last_sent: dict[str, float] = {}
        # connection_id -> list of timestamps within the current burst window
        self._window_history: dict[str, list[float]] = {}
        # connection_id -> (last_emote_id, consecutive_count)
        # Tracks same-emote repetitions for soft-block enforcement.
        self._same_emote: dict[str, tuple[str, int]] = {}
        # connection_id -> reason string for the most recent denial
        # One of: "cooldown", "burst", "same_emote"
        self._last_deny_reason: dict[str, str] = {}

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def is_valid_emote(self, emote_id: str) -> bool:
        """Return True if emote_id is in the permitted catalog."""
        return emote_id in VALID_EMOTE_IDS

    # ------------------------------------------------------------------
    # Rate limiting
    # ------------------------------------------------------------------

    def check_and_record(self, conn_id: str, emote_id: str) -> bool:
        """
        Check whether conn_id may send *emote_id* right now.

        Returns True and records the emission if allowed.
        Returns False (without recording) if any limit would be violated.

        Rules applied in order:
          1. Cooldown: now − last_sent < EMOTE_COOLDOWN_SECONDS → deny.
          2. Burst cap: entries_in_window >= EMOTE_BURST_CAP → deny.
          3. Same-emote soft block: consecutive_same > EMOTE_SAME_REPEAT_CAP
             → deny until a different emote is used.
        """
        now = time.time()

        # 1. Cooldown check
        last = self._last_sent.get(conn_id, 0.0)
        if now - last < settings.EMOTE_COOLDOWN_SECONDS:
            self._last_deny_reason[conn_id] = "cooldown"
            return False

        # 2. Burst window — prune expired entries then count
        window = self._window_history.get(conn_id, [])
        window = [t for t in window if now - t < settings.EMOTE_BURST_WINDOW_SECONDS]
        if len(window) >= settings.EMOTE_BURST_CAP:
            self._last_deny_reason[conn_id] = "burst"
            return False

        # 3. Same-emote soft block
        prev_id, streak = self._same_emote.get(conn_id, ("", 0))
        if emote_id == prev_id and streak >= settings.EMOTE_SAME_REPEAT_CAP:
            self._last_deny_reason[conn_id] = "same_emote"
            return False

        # Allowed — record
        window.append(now)
        self._last_sent[conn_id] = now
        self._window_history[conn_id] = window

        # Update same-emote streak counter
        if emote_id == prev_id:
            self._same_emote[conn_id] = (emote_id, streak + 1)
        else:
            self._same_emote[conn_id] = (emote_id, 1)

        return True

    def last_deny_reason(self, conn_id: str) -> str:
        """
        Return the reason for the most recent rate-limit denial for conn_id.

        Returns one of: ``"cooldown"``, ``"burst"``, ``"same_emote"``.
        Returns ``""`` if conn_id has never been denied.
        """
        return self._last_deny_reason.get(conn_id, "")

    def remaining_cooldown(self, conn_id: str) -> float:
        """
        Return seconds until the cooldown expires for conn_id.

        Returns 0.0 if the connection is not rate-limited.
        Useful for generating informative error messages.
        """
        last = self._last_sent.get(conn_id, 0.0)
        remaining = settings.EMOTE_COOLDOWN_SECONDS - (time.time() - last)
        return max(0.0, remaining)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def reset(self) -> None:
        """Clear all rate-limit state.  Called between tests."""
        self._last_sent.clear()
        self._window_history.clear()
        self._same_emote.clear()
        self._last_deny_reason.clear()


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

emote_service = EmoteService()
