"""
Multiplayer Menu Scene (PR-09).

Flow
----
1. CONNECTING    — WS is being established; shows spinner.
2. AUTH          — Player enters credentials (login / guest).
3. AUTH_REST     — REST /auth/guest or /auth/login call in progress.
4. AUTH_WS_WAIT  — JWT token sent over WS; waiting for AUTH_OK.
5. MODE_SELECT   — Choose: quick match, create room, or join room.
6. QM_QUEUE      — In quick-match queue; waiting for MATCH_FOUND / ROOM_STATE.
7. ROOM_CREATE_WAIT — Waiting for ROOM_STATE after ROOM_CREATE.
8. ROOM_CODE_INPUT  — Player is typing a room code to join.
9. ROOM_JOIN_WAIT   — Waiting for ROOM_STATE after ROOM_JOIN.

Authentication design
---------------------
The WS _auth handler only accepts { "token": <jwt_access_token> }.
It does NOT accept credentials directly over the socket.

Correct flow:
  1. Call REST API in a background thread (non-blocking for pygame):
       POST /auth/guest   {"nickname": "..."}
       POST /auth/login   {"email": "...", "password": "..."}
       POST /auth/register {"email": "...", "password": "...", "nickname": "..."}
  2. Receive access_token from REST response.
  3. Send over WS: AUTH_LOGIN or AUTH_GUEST with {"token": access_token}.
  4. Server validates JWT and responds with AUTH_OK.
"""

from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from enum import Enum, auto
from typing import Optional

import pygame

from fall_in.config import (
    AIR_FORCE_BLUE,
    LIGHT_BLUE,
    BLACK,
    SCREEN_WIDTH,
    SCREEN_HEIGHT,
    SAND_BEIGE,
)
from fall_in.multiplayer.bootstrap import build_remote_match_loading_scene
from fall_in.scenes.base_scene import Scene
from fall_in.ui.button import Button
from fall_in.utils.asset_loader import get_font

_WS_URL = "ws://localhost:8000/ws"
_REST_BASE = "http://localhost:8000"


class _State(Enum):
    CONNECTING = auto()
    RECONNECT_WAIT = auto()
    AUTH = auto()
    AUTH_REST = auto()    # REST token request in-flight
    AUTH_WS_WAIT = auto() # JWT sent over WS, awaiting AUTH_OK
    MODE_SELECT = auto()
    QM_QUEUE = auto()
    ROOM_CREATE_WAIT = auto()
    ROOM_CODE_INPUT = auto()
    ROOM_JOIN_WAIT = auto()
    ERROR = auto()


# ---------------------------------------------------------------------------
# Minimal text-input widget
# ---------------------------------------------------------------------------


class _TextInput:
    """Single-line text input box for the multiplayer scenes."""

    CURSOR_BLINK_RATE = 0.5

    def __init__(
        self,
        x: int,
        y: int,
        width: int,
        height: int,
        placeholder: str = "",
        password: bool = False,
    ) -> None:
        self.rect = pygame.Rect(x, y, width, height)
        self.placeholder = placeholder
        self.password = password
        self.text = ""
        self.focused = False
        self._cursor_timer = 0.0
        self._cursor_visible = True

    def handle_event(self, event: pygame.event.Event) -> None:
        if event.type == pygame.MOUSEBUTTONDOWN:
            self.focused = self.rect.collidepoint(event.pos)
        if not self.focused:
            return
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_BACKSPACE:
                self.text = self.text[:-1]
            elif event.key == pygame.K_v and (event.mod & pygame.KMOD_CTRL):
                try:
                    clip = pygame.scrap.get(pygame.SCRAP_TEXT)
                    if clip:
                        self.text += clip.decode("utf-8", errors="ignore").strip("\x00")
                except Exception:
                    pass
            elif event.unicode and event.unicode.isprintable():
                self.text += event.unicode

    def update(self, dt: float) -> None:
        if self.focused:
            self._cursor_timer += dt
            if self._cursor_timer >= self.CURSOR_BLINK_RATE:
                self._cursor_timer = 0.0
                self._cursor_visible = not self._cursor_visible
        else:
            self._cursor_visible = False

    def render(self, screen: pygame.Surface) -> None:
        bg = (255, 255, 255) if self.focused else (240, 240, 248)
        border = LIGHT_BLUE if self.focused else (160, 170, 190)
        pygame.draw.rect(screen, bg, self.rect, border_radius=6)
        pygame.draw.rect(screen, border, self.rect, 2, border_radius=6)

        font = get_font(18)
        if self.text:
            display = ("*" * len(self.text)) if self.password else self.text
            surf = font.render(display, True, BLACK)
        else:
            surf = font.render(self.placeholder, True, (180, 180, 190))

        clip_rect = self.rect.inflate(-16, -8)
        screen.set_clip(clip_rect)
        screen.blit(surf, (self.rect.x + 10, self.rect.centery - surf.get_height() // 2))
        screen.set_clip(None)

        if self.focused and self._cursor_visible and self.text:
            cursor_x = self.rect.x + 10 + surf.get_width() + 2
            cursor_y = self.rect.y + 8
            pygame.draw.line(
                screen,
                BLACK,
                (cursor_x, cursor_y),
                (cursor_x, self.rect.bottom - 8),
                1,
            )


# ---------------------------------------------------------------------------
# REST helper (called from background threads)
# ---------------------------------------------------------------------------


def _rest_post(path: str, payload: dict) -> dict:
    """
    Synchronous POST to the backend REST API.  Run in a background thread.

    Returns the parsed JSON response dict on HTTP 200/201.
    Raises RuntimeError with a user-friendly Korean message on failure.
    """
    url = _REST_BASE + path
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        try:
            detail = json.loads(e.read()).get("detail", str(e))
        except Exception:
            detail = str(e)
        raise RuntimeError(detail)
    except OSError as e:
        raise RuntimeError(f"서버에 연결할 수 없습니다: {e}")


# ---------------------------------------------------------------------------
# MultiplayerMenuScene
# ---------------------------------------------------------------------------


class MultiplayerMenuScene(Scene):
    """
    Auth and multiplayer-mode selection scene.

    After authentication and mode selection, transitions to RoomLobbyScene.
    """

    def __init__(self) -> None:
        super().__init__()
        self._state = _State.CONNECTING
        self._error_msg = ""
        self._spinner_timer = 0.0

        from fall_in.core.game_manager import GameManager
        from fall_in.net.ws_client import WsClient

        self._ws = WsClient.get(url=_WS_URL)
        game = GameManager()
        self._auto_access_token = game.access_token
        self._auto_auth_type = (
            "AUTH_LOGIN" if game.account_type == "registered" else "AUTH_GUEST"
        )
        self._pending_reconnect: Optional[dict] = game.get_pending_match_reconnect()

        # REST call result: written by bg thread, read by main thread
        self._rest_token: Optional[str] = None
        self._rest_error: Optional[str] = None
        # WS message type to use after token arrives ("AUTH_LOGIN" or "AUTH_GUEST")
        self._ws_auth_type: str = "AUTH_LOGIN"
        # display_name received in AUTH_OK — passed to RoomLobbyScene
        self._my_display_name: str = game.nickname or ""

        # AUTH form fields — separate instances per tab to avoid y-position juggling
        input_w = 320
        cx = SCREEN_WIDTH // 2
        # Login tab
        self._login_email = _TextInput(cx - input_w // 2, 295, input_w, 44, "이메일")
        self._login_pw = _TextInput(cx - input_w // 2, 355, input_w, 44, "비밀번호", password=True)
        # Register tab (nick on top)
        self._reg_nick = _TextInput(cx - input_w // 2, 285, input_w, 44, "닉네임 (2~20자)")
        self._reg_email = _TextInput(cx - input_w // 2, 340, input_w, 44, "이메일")
        self._reg_pw = _TextInput(cx - input_w // 2, 395, input_w, 44, "비밀번호", password=True)
        # Guest tab
        self._guest_nick = _TextInput(cx - input_w // 2, 350, input_w, 44, "닉네임 (2~20자)")

        self._room_code_input = _TextInput(cx - input_w // 2, 280, input_w, 44, "방 코드 (예: ABCD12)")

        # Quick-match seat index (set by MATCH_FOUND, consumed by MATCH_START)
        self._qm_seat_index: Optional[int] = None

        # "login" | "register" | "guest"
        self._auth_tab = "guest"

        # AUTH tab buttons
        self._btn_tab_login = Button(cx - 175, 225, 110, 40, "로그인", self._on_tab_login)
        self._btn_tab_register = Button(cx - 55, 225, 110, 40, "회원가입", self._on_tab_register)
        self._btn_tab_guest = Button(cx + 65, 225, 110, 40, "게스트", self._on_tab_guest)

        # AUTH submit
        self._btn_auth_submit = Button(cx - 100, 415, 200, 44, "접속", self._on_auth_submit)

        # MODE_SELECT buttons
        self._btn_quick = Button(cx - 110, 280, 220, 50, "빠른 대전", self._on_quick_match)
        self._btn_create = Button(cx - 110, 345, 220, 50, "방 만들기", self._on_create_room)
        self._btn_join = Button(cx - 110, 410, 220, 50, "방 참가", self._on_join_room)

        # ROOM_CODE_INPUT buttons
        self._btn_join_confirm = Button(cx - 110, 340, 220, 50, "입장", self._on_join_confirm)
        self._btn_join_cancel = Button(cx - 110, 405, 220, 50, "취소", self._on_mode_cancel)

        self._btn_back = Button(20, 20, 100, 40, "← 뒤로", self._on_back)

        # Start WS connection
        self._connect_thread = threading.Thread(target=self._do_connect, daemon=True)
        self._connect_thread.start()

    # ------------------------------------------------------------------
    # Connection bootstrap
    # ------------------------------------------------------------------

    def _do_connect(self) -> None:
        self._ws.connect()
        ok = self._ws.wait_connected(timeout=6.0)
        if not ok:
            self._state = _State.ERROR
            self._error_msg = f"서버 연결 실패: {self._ws.connect_error or '시간 초과'}"
            return
        self._ws.send("WS_HELLO")

    # ------------------------------------------------------------------
    # Button callbacks — AUTH tabs
    # ------------------------------------------------------------------

    def _on_tab_login(self) -> None:
        self._auth_tab = "login"
        self._error_msg = ""

    def _on_tab_register(self) -> None:
        self._auth_tab = "register"
        self._error_msg = ""

    def _on_tab_guest(self) -> None:
        self._auth_tab = "guest"
        self._error_msg = ""

    def _on_auth_submit(self) -> None:
        if self._state != _State.AUTH:
            return
        self._error_msg = ""

        if self._auth_tab == "guest":
            nick = self._guest_nick.text.strip()
            if not nick:
                self._error_msg = "닉네임을 입력하세요."
                return
            self._ws_auth_type = "AUTH_GUEST"
            self._state = _State.AUTH_REST
            threading.Thread(
                target=self._do_rest_guest, args=(nick,), daemon=True
            ).start()

        elif self._auth_tab == "login":
            email = self._login_email.text.strip()
            pw = self._login_pw.text
            if not email or not pw:
                self._error_msg = "이메일과 비밀번호를 입력하세요."
                return
            self._ws_auth_type = "AUTH_LOGIN"
            self._state = _State.AUTH_REST
            threading.Thread(
                target=self._do_rest_login, args=(email, pw), daemon=True
            ).start()

        elif self._auth_tab == "register":
            nick = self._reg_nick.text.strip()
            email = self._reg_email.text.strip()
            pw = self._reg_pw.text
            if not nick or not email or not pw:
                self._error_msg = "모든 필드를 입력하세요."
                return
            self._ws_auth_type = "AUTH_LOGIN"
            self._state = _State.AUTH_REST
            threading.Thread(
                target=self._do_rest_register, args=(email, pw, nick), daemon=True
            ).start()

    # ------------------------------------------------------------------
    # REST calls (run in background threads)
    # ------------------------------------------------------------------

    def _do_rest_guest(self, nickname: str) -> None:
        try:
            resp = _rest_post("/auth/guest", {"nickname": nickname})
            self._rest_token = resp["access_token"]
        except RuntimeError as e:
            self._rest_error = str(e)

    def _do_rest_login(self, email: str, password: str) -> None:
        try:
            resp = _rest_post("/auth/login", {"email": email, "password": password})
            self._rest_token = resp["access_token"]
        except RuntimeError as e:
            self._rest_error = str(e)

    def _do_rest_register(self, email: str, password: str, nickname: str) -> None:
        try:
            resp = _rest_post(
                "/auth/register",
                {"email": email, "password": password, "nickname": nickname},
            )
            self._rest_token = resp["access_token"]
        except RuntimeError as e:
            self._rest_error = str(e)

    # ------------------------------------------------------------------
    # Button callbacks — mode select
    # ------------------------------------------------------------------

    def _on_quick_match(self) -> None:
        if self._state != _State.MODE_SELECT:
            return
        self._ws.send("QUICK_MATCH_JOIN")
        self._state = _State.QM_QUEUE
        self._error_msg = ""

    def _on_create_room(self) -> None:
        if self._state != _State.MODE_SELECT:
            return
        self._ws.send("ROOM_CREATE")
        self._state = _State.ROOM_CREATE_WAIT
        self._error_msg = ""

    def _on_join_room(self) -> None:
        if self._state != _State.MODE_SELECT:
            return
        self._room_code_input.text = ""
        self._state = _State.ROOM_CODE_INPUT
        self._error_msg = ""

    def _on_join_confirm(self) -> None:
        code = self._room_code_input.text.strip().upper()
        if not code:
            self._error_msg = "방 코드를 입력하세요."
            return
        self._ws.send("ROOM_JOIN", {"room_code": code})
        self._state = _State.ROOM_JOIN_WAIT
        self._error_msg = ""

    def _on_mode_cancel(self) -> None:
        self._state = _State.MODE_SELECT
        self._error_msg = ""

    def _on_back(self) -> None:
        from fall_in.core.game_manager import GameManager
        from fall_in.scenes.title_scene import TitleScene
        from fall_in.net.ws_client import WsClient

        WsClient.reset()
        GameManager().change_scene(TitleScene())

    # ------------------------------------------------------------------
    # WS + REST result polling
    # ------------------------------------------------------------------

    def _handle_ws_messages(self) -> None:
        # Poll REST result when waiting for token
        if self._state == _State.AUTH_REST:
            if self._rest_error is not None:
                self._error_msg = self._rest_error
                self._rest_error = None
                self._rest_token = None
                self._state = _State.AUTH
                return
            if self._rest_token is not None:
                token = self._rest_token
                self._rest_token = None
                self._ws.send(self._ws_auth_type, {"token": token})
                self._state = _State.AUTH_WS_WAIT
                return

        messages = self._ws.pump()
        idx = 0
        while idx < len(messages):
            msg_type, data = messages[idx]
            if msg_type == "WS_WELCOME":
                if self._state == _State.CONNECTING:
                    if self._try_pending_reconnect():
                        pass
                    elif self._auto_access_token:
                        self._ws.send(
                            self._auto_auth_type,
                            {"token": self._auto_access_token},
                        )
                        self._state = _State.AUTH_WS_WAIT
                    else:
                        self._state = _State.AUTH
            elif msg_type == "RECONNECT_OK":
                bootstrap_messages = list(messages[idx + 1 :])
                self._go_to_reconnected_match(data, bootstrap_messages)
                break
            elif msg_type == "AUTH_OK":
                self._my_display_name = data.get("display_name", "")
                self._state = _State.MODE_SELECT
                self._error_msg = ""
            elif msg_type == "ROOM_STATE":
                self._go_to_lobby(data)
            elif msg_type == "MATCH_FOUND":
                self._qm_seat_index = int(data.get("seat_index", 0))
                self._state = _State.QM_QUEUE
            elif msg_type == "MATCH_START":
                # Quick-match: transition to game scene.
                # Any remaining messages (PHASE_SELECTING, PRIVATE_HAND_STATE)
                # are forwarded as bootstrap messages.
                bootstrap_messages = list(messages[idx + 1 :])
                my_seat = self._qm_seat_index if self._qm_seat_index is not None else 0
                self._go_to_quick_match(my_seat, bootstrap_messages)
                break
            elif msg_type == "QUEUE_JOINED":
                self._state = _State.QM_QUEUE
            elif msg_type == "ERROR":
                code = data.get("code", "")
                msg = data.get("message", "오류가 발생했습니다.")
                self._error_msg = f"[{code}] {msg}" if code else msg
                if self._state == _State.RECONNECT_WAIT:
                    self._fallback_from_reconnect_error()
                elif self._state == _State.AUTH_WS_WAIT:
                    self._state = _State.AUTH
                elif self._state in (
                    _State.ROOM_CREATE_WAIT,
                    _State.ROOM_JOIN_WAIT,
                    _State.QM_QUEUE,
                ):
                    self._state = _State.MODE_SELECT
            elif msg_type == "PING":
                self._ws.send("PONG")
            idx += 1

    def _try_pending_reconnect(self) -> bool:
        pending = self._pending_reconnect or {}
        token = pending.get("token")
        if not token:
            return False
        self._ws.send("RECONNECT", {"token": token})
        self._state = _State.RECONNECT_WAIT
        return True

    def _fallback_from_reconnect_error(self) -> None:
        from fall_in.core.game_manager import GameManager

        GameManager().clear_pending_match_reconnect()
        self._pending_reconnect = None
        if self._auto_access_token:
            self._ws.send(
                self._auto_auth_type,
                {"token": self._auto_access_token},
            )
            self._state = _State.AUTH_WS_WAIT
        else:
            self._state = _State.AUTH

    def _go_to_reconnected_match(
        self,
        reconnect_data: dict,
        bootstrap_messages: list[tuple[str, dict]],
    ) -> None:
        from fall_in.core.game_manager import GameManager

        my_seat = reconnect_data.get("seat_index", 0)
        GameManager().change_scene(
            build_remote_match_loading_scene(
                ws=self._ws,
                my_seat=int(my_seat),
                bootstrap_messages=bootstrap_messages,
            )
        )

    def _go_to_quick_match(
        self,
        my_seat: int,
        bootstrap_messages: list[tuple[str, dict]],
    ) -> None:
        from fall_in.core.game_manager import GameManager

        GameManager().change_scene(
            build_remote_match_loading_scene(
                ws=self._ws,
                my_seat=my_seat,
                bootstrap_messages=bootstrap_messages,
            )
        )

    def _go_to_lobby(self, room_data: dict) -> None:
        from fall_in.core.game_manager import GameManager
        from fall_in.scenes.room_lobby_scene import RoomLobbyScene

        GameManager().change_scene(
            RoomLobbyScene(
                ws=self._ws,
                room_data=room_data,
                my_display_name=self._my_display_name,
            )
        )

    # ------------------------------------------------------------------
    # Scene interface
    # ------------------------------------------------------------------

    def handle_event(self, event: pygame.event.Event) -> None:
        self._btn_back.handle_event(event)

        if self._state == _State.AUTH:
            self._btn_tab_login.handle_event(event)
            self._btn_tab_register.handle_event(event)
            self._btn_tab_guest.handle_event(event)
            self._btn_auth_submit.handle_event(event)
            if self._auth_tab == "login":
                self._login_email.handle_event(event)
                self._login_pw.handle_event(event)
            elif self._auth_tab == "register":
                self._reg_nick.handle_event(event)
                self._reg_email.handle_event(event)
                self._reg_pw.handle_event(event)
            elif self._auth_tab == "guest":
                self._guest_nick.handle_event(event)

        elif self._state == _State.MODE_SELECT:
            self._btn_quick.handle_event(event)
            self._btn_create.handle_event(event)
            self._btn_join.handle_event(event)

        elif self._state == _State.ROOM_CODE_INPUT:
            self._room_code_input.handle_event(event)
            self._btn_join_confirm.handle_event(event)
            self._btn_join_cancel.handle_event(event)

    def update(self, dt: float) -> None:
        self._spinner_timer += dt
        self._handle_ws_messages()

        if self._state == _State.AUTH:
            self._btn_tab_login.update(dt)
            self._btn_tab_register.update(dt)
            self._btn_tab_guest.update(dt)
            self._btn_auth_submit.update(dt)
            if self._auth_tab == "login":
                self._login_email.update(dt)
                self._login_pw.update(dt)
            elif self._auth_tab == "register":
                self._reg_nick.update(dt)
                self._reg_email.update(dt)
                self._reg_pw.update(dt)
            elif self._auth_tab == "guest":
                self._guest_nick.update(dt)

        elif self._state == _State.MODE_SELECT:
            self._btn_quick.update(dt)
            self._btn_create.update(dt)
            self._btn_join.update(dt)

        elif self._state == _State.ROOM_CODE_INPUT:
            self._room_code_input.update(dt)
            self._btn_join_confirm.update(dt)
            self._btn_join_cancel.update(dt)

    def render(self, screen: pygame.Surface) -> None:
        screen.fill(SAND_BEIGE)

        font_title = get_font(36, "bold")
        title = font_title.render("멀티플레이", True, AIR_FORCE_BLUE)
        screen.blit(title, title.get_rect(center=(SCREEN_WIDTH // 2, 80)))

        font_sub = get_font(20)

        if self._state == _State.CONNECTING:
            dots = "." * (int(self._spinner_timer * 3) % 4)
            msg = font_sub.render(f"서버에 연결 중{dots}", True, AIR_FORCE_BLUE)
            screen.blit(msg, msg.get_rect(center=(SCREEN_WIDTH // 2, SCREEN_HEIGHT // 2)))

        elif self._state == _State.AUTH:
            self._render_auth(screen)

        elif self._state in (_State.RECONNECT_WAIT, _State.AUTH_REST, _State.AUTH_WS_WAIT):
            dots = "." * (int(self._spinner_timer * 3) % 4)
            label = "대전 복귀 중" if self._state == _State.RECONNECT_WAIT else "인증 중"
            msg = font_sub.render(f"{label}{dots}", True, AIR_FORCE_BLUE)
            screen.blit(msg, msg.get_rect(center=(SCREEN_WIDTH // 2, SCREEN_HEIGHT // 2)))

        elif self._state == _State.MODE_SELECT:
            lbl = font_sub.render("게임 방식을 선택하세요", True, AIR_FORCE_BLUE)
            screen.blit(lbl, lbl.get_rect(center=(SCREEN_WIDTH // 2, 230)))
            self._btn_quick.render(screen)
            self._btn_create.render(screen)
            self._btn_join.render(screen)

        elif self._state == _State.QM_QUEUE:
            dots = "." * (int(self._spinner_timer * 3) % 4)
            msg = font_sub.render(f"상대방을 찾는 중{dots}", True, AIR_FORCE_BLUE)
            screen.blit(msg, msg.get_rect(center=(SCREEN_WIDTH // 2, SCREEN_HEIGHT // 2)))
            hint = get_font(14).render("잠시 기다려 주세요...", True, (100, 100, 120))
            screen.blit(hint, hint.get_rect(center=(SCREEN_WIDTH // 2, SCREEN_HEIGHT // 2 + 40)))

        elif self._state in (_State.ROOM_CREATE_WAIT, _State.ROOM_JOIN_WAIT):
            dots = "." * (int(self._spinner_timer * 3) % 4)
            msg = font_sub.render(f"방 정보를 불러오는 중{dots}", True, AIR_FORCE_BLUE)
            screen.blit(msg, msg.get_rect(center=(SCREEN_WIDTH // 2, SCREEN_HEIGHT // 2)))

        elif self._state == _State.ROOM_CODE_INPUT:
            cx = SCREEN_WIDTH // 2
            lbl = font_sub.render("방 코드 입력", True, AIR_FORCE_BLUE)
            screen.blit(lbl, lbl.get_rect(center=(cx, 230)))
            self._room_code_input.render(screen)
            self._btn_join_confirm.render(screen)
            self._btn_join_cancel.render(screen)

        elif self._state == _State.ERROR:
            err = font_sub.render("연결 오류", True, (180, 40, 40))
            screen.blit(err, err.get_rect(center=(SCREEN_WIDTH // 2, SCREEN_HEIGHT // 2 - 30)))
            detail = get_font(16).render(self._error_msg, True, (140, 40, 40))
            screen.blit(detail, detail.get_rect(center=(SCREEN_WIDTH // 2, SCREEN_HEIGHT // 2 + 10)))

        # Inline error banner (non-fatal errors in other states)
        if self._error_msg and self._state not in (_State.ERROR, _State.AUTH):
            err_surf = get_font(16).render(self._error_msg, True, (180, 40, 40))
            screen.blit(
                err_surf,
                err_surf.get_rect(center=(SCREEN_WIDTH // 2, SCREEN_HEIGHT - 60)),
            )

        if self._state != _State.CONNECTING:
            self._btn_back.render(screen)

    # ------------------------------------------------------------------
    # AUTH rendering
    # ------------------------------------------------------------------

    def _render_auth(self, screen: pygame.Surface) -> None:
        cx = SCREEN_WIDTH // 2

        # Tab buttons
        self._btn_tab_login.render(screen)
        self._btn_tab_register.render(screen)
        self._btn_tab_guest.render(screen)

        # Active tab underline
        active_map = {
            "login": self._btn_tab_login,
            "register": self._btn_tab_register,
            "guest": self._btn_tab_guest,
        }
        active_btn = active_map[self._auth_tab]
        pygame.draw.line(
            screen,
            LIGHT_BLUE,
            (active_btn.rect.left, active_btn.rect.bottom + 3),
            (active_btn.rect.right, active_btn.rect.bottom + 3),
            3,
        )

        lbl_font = get_font(16)

        if self._auth_tab == "guest":
            screen.blit(lbl_font.render("닉네임", True, AIR_FORCE_BLUE), (cx - 160, 332))
            self._guest_nick.render(screen)

        elif self._auth_tab == "login":
            screen.blit(lbl_font.render("이메일", True, AIR_FORCE_BLUE), (cx - 160, 277))
            screen.blit(lbl_font.render("비밀번호", True, AIR_FORCE_BLUE), (cx - 160, 337))
            self._login_email.render(screen)
            self._login_pw.render(screen)

        elif self._auth_tab == "register":
            screen.blit(lbl_font.render("닉네임", True, AIR_FORCE_BLUE), (cx - 160, 267))
            screen.blit(lbl_font.render("이메일", True, AIR_FORCE_BLUE), (cx - 160, 322))
            screen.blit(lbl_font.render("비밀번호", True, AIR_FORCE_BLUE), (cx - 160, 377))
            self._reg_nick.render(screen)
            self._reg_email.render(screen)
            self._reg_pw.render(screen)

        # Error under form
        if self._error_msg:
            err = get_font(15).render(self._error_msg, True, (180, 40, 40))
            screen.blit(err, err.get_rect(center=(cx, 470)))

        self._btn_auth_submit.render(screen)
