"""
WebSocket client for Fall-In multiplayer (PR-09).

Runs the asyncio send/receive loop in a background daemon thread so the
synchronous pygame main loop is never blocked by network I/O.

Thread-safety contract
----------------------
* _recv_queue (stdlib queue.Queue) — bg thread writes, main thread reads.
* _send_queue (asyncio.Queue)      — main thread enqueues via
  loop.call_soon_threadsafe(); bg thread dequeues and sends.

Usage::

    client = WsClient.get()          # singleton
    client.connect()
    if not client.wait_connected(3.0):
        print("connection failed:", client.connect_error)

    # Each pygame frame:
    for msg_type, data in client.pump():
        handle_server_message(msg_type, data)

    # Sending:
    client.send("AUTH_LOGIN", {"token": "..."})
    client.send("WS_HELLO")

    # Disconnect:
    WsClient.reset()
"""

from __future__ import annotations

import asyncio
import json
import logging
import queue
import threading
from typing import Optional

logger = logging.getLogger("fall_in.net.ws_client")

_DEFAULT_WS_URL = "ws://localhost:8000/ws"


class WsClient:
    """
    Thread-safe singleton WebSocket client.

    The asyncio event loop runs in a dedicated daemon thread.  The pygame
    main thread interacts exclusively through:
      - send()          — enqueue a message to transmit
      - pump()          — drain all messages received since last call
      - is_connected    — read-only property
      - connect_error   — set if the connection attempt failed
    """

    _instance: Optional["WsClient"] = None

    # ------------------------------------------------------------------
    # Singleton management
    # ------------------------------------------------------------------

    @classmethod
    def get(cls, url: str = _DEFAULT_WS_URL) -> "WsClient":
        """Return the shared WsClient instance, creating it if needed."""
        if cls._instance is None:
            cls._instance = cls(url)
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        """Disconnect and discard the singleton so a fresh one can be created."""
        if cls._instance is not None:
            cls._instance.disconnect()
            cls._instance = None

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    def __init__(self, url: str = _DEFAULT_WS_URL) -> None:
        self._url = url
        self._thread: Optional[threading.Thread] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._send_queue: Optional[asyncio.Queue] = None
        # Thread-safe inbox: bg thread writes, main thread reads
        self._recv_queue: queue.Queue = queue.Queue()
        self._connected = False
        self._connect_error: Optional[str] = None
        # Signalled (from bg thread) once the connection attempt completes
        self._connect_event = threading.Event()

    # ------------------------------------------------------------------
    # Connection management (called from main thread)
    # ------------------------------------------------------------------

    def connect(self) -> None:
        """Start the background thread and connect to the WS server."""
        if self._thread and self._thread.is_alive():
            return
        self._connect_event.clear()
        self._connect_error = None
        self._connected = False
        self._thread = threading.Thread(target=self._run, daemon=True, name="ws-client")
        self._thread.start()

    def wait_connected(self, timeout: float = 5.0) -> bool:
        """
        Block the calling thread until the connection succeeds or fails.

        Returns True only if the connection was established without error.
        Typically called right after connect() from the scene's on_enter()
        while showing a "연결 중..." spinner.
        """
        ok = self._connect_event.wait(timeout)
        return ok and self._connect_error is None

    def disconnect(self) -> None:
        """Send a sentinel to the bg thread, causing it to close the socket."""
        if self._loop is not None and self._send_queue is not None:
            try:
                self._loop.call_soon_threadsafe(self._send_queue.put_nowait, None)
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Main-thread API
    # ------------------------------------------------------------------

    def send(self, msg_type: str, data: Optional[dict] = None) -> None:
        """
        Enqueue a message to be sent to the server.

        Safe to call from the pygame main thread at any time after connect().
        """
        if not self._connected or self._loop is None or self._send_queue is None:
            return
        msg = {"type": msg_type, "data": data or {}}
        try:
            self._loop.call_soon_threadsafe(self._send_queue.put_nowait, msg)
        except Exception:
            pass

    def pump(self) -> list[tuple[str, dict]]:
        """
        Drain and return all messages received since the last call.

        Call once per pygame frame.  Returns a list of (msg_type, data) tuples.
        Never blocks.
        """
        messages: list[tuple[str, dict]] = []
        while True:
            try:
                messages.append(self._recv_queue.get_nowait())
            except queue.Empty:
                break
        return messages

    @property
    def is_connected(self) -> bool:
        return self._connected

    @property
    def connect_error(self) -> Optional[str]:
        return self._connect_error

    # ------------------------------------------------------------------
    # Background-thread implementation
    # ------------------------------------------------------------------

    def _run(self) -> None:
        """Entry point for the background thread."""
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self._async_run())
        except Exception as e:
            logger.error("ws_client_loop_error", extra={"error": str(e)})
        finally:
            self._connected = False
            # Signal main thread if it's still waiting (e.g. on error before connect)
            self._connect_event.set()
            try:
                self._loop.close()
            except Exception:
                pass

    async def _async_run(self) -> None:
        import websockets

        self._send_queue = asyncio.Queue()
        try:
            async with websockets.connect(self._url) as ws:
                self._connected = True
                self._connect_event.set()
                logger.info("ws_client_connected", extra={"url": self._url})
                await asyncio.gather(
                    self._recv_loop(ws),
                    self._send_loop(ws),
                    return_exceptions=True,
                )
        except Exception as e:
            self._connect_error = str(e)
            self._connect_event.set()
            logger.warning("ws_client_connect_failed", extra={"url": self._url, "error": str(e)})
        finally:
            self._connected = False

    async def _recv_loop(self, ws) -> None:
        try:
            async for raw in ws:
                try:
                    msg = json.loads(raw)
                    msg_type = msg.get("type", "")
                    data = msg.get("data") or {}
                    if not isinstance(data, dict):
                        data = {}
                    self._recv_queue.put((msg_type, data))
                except Exception as e:
                    logger.warning("ws_client_parse_error", extra={"error": str(e)})
        except Exception:
            pass

    async def _send_loop(self, ws) -> None:
        try:
            while True:
                msg = await self._send_queue.get()
                if msg is None:  # disconnect sentinel
                    await ws.close()
                    break
                await ws.send(json.dumps(msg))
        except Exception:
            pass
