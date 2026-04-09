"""
Structured logging configuration for the Fall-In backend (PR-08).

Uses Python's built-in logging module with a JSON-style formatter so
that log lines are easily grep-able during beta and parsable by log
aggregators (e.g. Loki, CloudWatch) in production.

Call ``configure_logging()`` once at application startup (in main.py
lifespan) before any other module emits log records.

Log levels
----------
DEBUG   internal state useful for stepping through WS flows locally
INFO    normal lifecycle events (connect, auth, match start/end, reports)
WARNING unexpected but recoverable situations (rate-limit hits, bad msgs)
ERROR   unhandled exceptions that degrade a connection or request

Root logger level defaults to INFO.  Set LOG_LEVEL=DEBUG in .env for
local debugging.

Log format (one JSON object per line)::

    {"ts": "2026-04-06T12:00:00.123Z", "level": "INFO",
     "logger": "fall_in.ws", "msg": "ws_connect", "conn_id": "..."}
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any


class _JsonFormatter(logging.Formatter):
    """
    Format log records as single-line JSON objects.

    Extra fields attached via ``logger.info(msg, extra={...})`` are merged
    into the top-level JSON object for easy querying.
    """

    # Fields present on every LogRecord that we do NOT want to repeat.
    _SKIP = frozenset(
        {
            "args",
            "created",
            "exc_info",
            "exc_text",
            "filename",
            "funcName",
            "levelno",
            "lineno",
            "message",
            "module",
            "msecs",
            "msg",
            "name",
            "pathname",
            "process",
            "processName",
            "relativeCreated",
            "stack_info",
            "taskName",
            "thread",
            "threadName",
        }
    )

    def format(self, record: logging.LogRecord) -> str:
        record.message = record.getMessage()
        ts = (
            datetime.fromtimestamp(record.created, tz=timezone.utc).strftime(
                "%Y-%m-%dT%H:%M:%S.%f"
            )[:-3]
            + "Z"
        )

        payload: dict[str, Any] = {
            "ts": ts,
            "level": record.levelname,
            "logger": record.name,
            "msg": record.message,
        }

        # Merge any extra fields supplied by the caller.
        for key, value in record.__dict__.items():
            if key not in self._SKIP and not key.startswith("_"):
                payload[key] = value

        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)

        return json.dumps(payload, ensure_ascii=False, default=str)


def configure_logging(level: str = "INFO") -> None:
    """
    Set up the root logger and the fall_in namespace logger.

    Safe to call multiple times (idempotent — handlers are added only once).
    """
    root = logging.getLogger()
    if root.handlers:
        # Already configured — skip to avoid duplicate output.
        return

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(_JsonFormatter())

    root.addHandler(handler)
    root.setLevel(getattr(logging, level.upper(), logging.INFO))

    # Suppress noisy third-party loggers at WARNING+ only.
    for noisy in ("uvicorn.access", "sqlalchemy.engine"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
