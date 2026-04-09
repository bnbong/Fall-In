"""
Account gate scene shown immediately after the intro cutscene.

Players choose login, register, or guest play before reaching the title
screen so single-player progress can be reconciled early.
"""

from __future__ import annotations

import threading
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
from fall_in.scenes.base_scene import Scene
from fall_in.ui.button import Button
from fall_in.utils.asset_loader import get_font


class _State(Enum):
    AUTH = auto()
    AUTH_REST = auto()


class _TextInput:
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


class AccountGateScene(Scene):
    def __init__(self) -> None:
        super().__init__()
        self._state = _State.AUTH
        self._error_msg = ""
        self._spinner_timer = 0.0
        self._auth_done = False
        self._auth_error: Optional[str] = None

        input_w = 320
        cx = SCREEN_WIDTH // 2

        self._login_email = _TextInput(cx - input_w // 2, 295, input_w, 44, "이메일")
        self._login_pw = _TextInput(cx - input_w // 2, 355, input_w, 44, "비밀번호", password=True)
        self._reg_nick = _TextInput(cx - input_w // 2, 285, input_w, 44, "닉네임 (2~20자)")
        self._reg_email = _TextInput(cx - input_w // 2, 340, input_w, 44, "이메일")
        self._reg_pw = _TextInput(cx - input_w // 2, 395, input_w, 44, "비밀번호", password=True)
        self._guest_nick = _TextInput(cx - input_w // 2, 350, input_w, 44, "닉네임 (2~20자)")

        self._auth_tab = "guest"
        self._btn_tab_login = Button(cx - 175, 225, 110, 40, "로그인", self._on_tab_login)
        self._btn_tab_register = Button(cx - 55, 225, 110, 40, "회원가입", self._on_tab_register)
        self._btn_tab_guest = Button(cx + 65, 225, 110, 40, "게스트", self._on_tab_guest)
        self._btn_auth_submit = Button(cx - 100, 415, 200, 44, "계속", self._on_auth_submit)

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
            self._state = _State.AUTH_REST
            threading.Thread(target=self._do_auth_guest, args=(nick,), daemon=True).start()
            return

        if self._auth_tab == "login":
            email = self._login_email.text.strip()
            pw = self._login_pw.text
            if not email or not pw:
                self._error_msg = "이메일과 비밀번호를 입력하세요."
                return
            self._state = _State.AUTH_REST
            threading.Thread(target=self._do_auth_login, args=(email, pw), daemon=True).start()
            return

        nick = self._reg_nick.text.strip()
        email = self._reg_email.text.strip()
        pw = self._reg_pw.text
        if not nick or not email or not pw:
            self._error_msg = "모든 필드를 입력하세요."
            return
        self._state = _State.AUTH_REST
        threading.Thread(
            target=self._do_auth_register,
            args=(email, pw, nick),
            daemon=True,
        ).start()

    def _finish_auth(self, response: dict) -> None:
        from fall_in.core.game_manager import GameManager

        game = GameManager()
        game.apply_auth_session(
            access_token=response["access_token"],
            refresh_token=response.get("refresh_token"),
            account_type=response.get("account_type", "guest"),
        )
        game.bootstrap_authenticated_account(sync_local_progress=game.account_type == "registered")
        self._auth_done = True

    def _do_auth_guest(self, nickname: str) -> None:
        try:
            from fall_in.net.backend_api import post_json

            self._finish_auth(post_json("/auth/guest", {"nickname": nickname}))
        except Exception as exc:
            self._auth_error = str(exc)

    def _do_auth_login(self, email: str, password: str) -> None:
        try:
            from fall_in.net.backend_api import post_json

            self._finish_auth(post_json("/auth/login", {"email": email, "password": password}))
        except Exception as exc:
            self._auth_error = str(exc)

    def _do_auth_register(self, email: str, password: str, nickname: str) -> None:
        try:
            from fall_in.net.backend_api import post_json

            self._finish_auth(
                post_json(
                    "/auth/register",
                    {"email": email, "password": password, "nickname": nickname},
                )
            )
        except Exception as exc:
            self._auth_error = str(exc)

    def handle_event(self, event: pygame.event.Event) -> None:
        if self._state != _State.AUTH:
            return
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
        else:
            self._guest_nick.handle_event(event)

    def update(self, dt: float) -> None:
        self._spinner_timer += dt

        if self._auth_error is not None:
            self._error_msg = self._auth_error
            self._auth_error = None
            self._state = _State.AUTH

        if self._auth_done:
            from fall_in.core.game_manager import GameManager, GameState
            from fall_in.scenes.title_scene import TitleScene

            game = GameManager()
            game.state = GameState.TITLE
            game.change_scene(TitleScene())
            return

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
            else:
                self._guest_nick.update(dt)

    def render(self, screen: pygame.Surface) -> None:
        screen.fill(SAND_BEIGE)

        title_font = get_font(36, "bold")
        title = title_font.render("계정 선택", True, AIR_FORCE_BLUE)
        screen.blit(title, title.get_rect(center=(SCREEN_WIDTH // 2, 80)))

        sub_font = get_font(18)
        sub = sub_font.render(
            "싱글플레이 진행도와 멀티플레이 데이터를 맞추기 위해 먼저 계정을 선택해 주세요.",
            True,
            AIR_FORCE_BLUE,
        )
        screen.blit(sub, sub.get_rect(center=(SCREEN_WIDTH // 2, 130)))

        if self._state == _State.AUTH:
            self._render_auth(screen)
        else:
            dots = "." * (int(self._spinner_timer * 3) % 4)
            msg = sub_font.render(f"계정 동기화 중{dots}", True, AIR_FORCE_BLUE)
            screen.blit(msg, msg.get_rect(center=(SCREEN_WIDTH // 2, SCREEN_HEIGHT // 2)))

        if self._error_msg:
            err_surf = get_font(16).render(self._error_msg, True, (180, 40, 40))
            screen.blit(
                err_surf,
                err_surf.get_rect(center=(SCREEN_WIDTH // 2, SCREEN_HEIGHT - 60)),
            )

    def _render_auth(self, screen: pygame.Surface) -> None:
        cx = SCREEN_WIDTH // 2

        self._btn_tab_login.render(screen)
        self._btn_tab_register.render(screen)
        self._btn_tab_guest.render(screen)

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
        if self._auth_tab == "login":
            self._login_email.render(screen)
            self._login_pw.render(screen)
            hint = lbl_font.render("기존 계정으로 이어서 플레이", True, AIR_FORCE_BLUE)
            screen.blit(hint, hint.get_rect(center=(cx, 260)))
        elif self._auth_tab == "register":
            self._reg_nick.render(screen)
            self._reg_email.render(screen)
            self._reg_pw.render(screen)
            hint = lbl_font.render("새 계정을 만들고 진행도를 서버와 연결", True, AIR_FORCE_BLUE)
            screen.blit(hint, hint.get_rect(center=(cx, 260)))
        else:
            self._guest_nick.render(screen)
            hint = lbl_font.render("게스트로 시작하며 로컬 진행도를 그대로 사용", True, AIR_FORCE_BLUE)
            screen.blit(hint, hint.get_rect(center=(cx, 315)))

        self._btn_auth_submit.render(screen)
