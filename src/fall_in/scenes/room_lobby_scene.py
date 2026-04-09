"""
Room Lobby Scene (PR-09).

Displays the current room state (seats, ready status) received via ROOM_STATE
messages.  Players can toggle ready and the room owner can start the match.

On MATCH_START the scene constructs a multiplayer GameScene, wires the
RemoteGameAdapter and network-tick callback, then transitions through the
loading screen.

Server messages handled here
-----------------------------
ROOM_STATE       — update seat list and room code display
MATCH_FOUND      — brief "상대를 찾았습니다!" banner (quick-match path)
MATCH_START      — build GameScene and transition
PLAYER_PRESENCE  — show which seats are connected
ERROR            — display inline error and stay in lobby
PING             — respond with PONG
"""

from __future__ import annotations

from typing import Optional

import pygame

from fall_in.config import (
    AIR_FORCE_BLUE,
    LIGHT_BLUE,
    WHITE,
    SCREEN_WIDTH,
    SCREEN_HEIGHT,
    SAND_BEIGE,
)
from fall_in.multiplayer.bootstrap import build_remote_match_loading_scene
from fall_in.scenes.base_scene import Scene
from fall_in.ui.button import Button
from fall_in.utils.asset_loader import get_font


class RoomLobbyScene(Scene):
    """
    Room lobby — shows seats, ready status, and start controls.

    Parameters
    ----------
    ws:        Active WsClient singleton.
    room_data: The ``data`` dict from the first ROOM_STATE message.
    """

    def __init__(self, ws, room_data: dict, my_display_name: str = "") -> None:
        super().__init__()
        self._ws = ws
        self._room_data = room_data
        self._my_display_name = my_display_name
        self._pending_game_messages: list[tuple[str, dict]] = []
        self._error_msg = ""
        self._info_msg = ""
        self._info_timer = 0.0
        self._match_starting = False

        cx = SCREEN_WIDTH // 2
        self._btn_ready = Button(cx - 110, SCREEN_HEIGHT - 130, 220, 50, "준비", self._on_ready)
        self._btn_start = Button(cx - 110, SCREEN_HEIGHT - 70, 220, 50, "게임 시작", self._on_start)
        self._btn_leave = Button(20, 20, 100, 40, "← 나가기", self._on_leave)

        self._is_ready = False
        self._my_seat: Optional[int] = None
        self._am_owner = False
        self._update_from_room_data(room_data)

    # ------------------------------------------------------------------
    # Room-data helpers
    # ------------------------------------------------------------------

    def _update_from_room_data(self, data: dict) -> None:
        self._room_data = data
        # Server key is "participants", not "seats"
        participants = data.get("participants") or []
        # Find my seat by matching display_name
        for p in participants:
            if p.get("display_name") == self._my_display_name:
                self._my_seat = p.get("seat_index")
                self._is_ready = p.get("is_ready", False)
                break
        # Server key is "host_seat_index", not "owner_seat_index"
        host_seat = data.get("host_seat_index")
        self._am_owner = (
            self._my_seat is not None and self._my_seat == host_seat
        )
        self._btn_ready.text = "준비 취소" if self._is_ready else "준비"

    # ------------------------------------------------------------------
    # Button callbacks
    # ------------------------------------------------------------------

    def _on_ready(self) -> None:
        new_ready = not self._is_ready
        # Server reads "is_ready", not "ready"
        self._ws.send("READY_SET", {"is_ready": new_ready})

    def _on_start(self) -> None:
        self._ws.send("ROOM_START")

    def _on_leave(self) -> None:
        self._ws.send("ROOM_LEAVE")
        from fall_in.core.game_manager import GameManager
        from fall_in.scenes.multiplayer_menu_scene import MultiplayerMenuScene
        from fall_in.net.ws_client import WsClient

        WsClient.reset()
        GameManager().change_scene(MultiplayerMenuScene())

    # ------------------------------------------------------------------
    # WS message routing
    # ------------------------------------------------------------------

    def _handle_ws_messages(self) -> None:
        messages = self._ws.pump()
        idx = 0
        while idx < len(messages):
            msg_type, data = messages[idx]
            if msg_type == "ROOM_STATE":
                self._update_from_room_data(data)
                self._error_msg = ""
            elif msg_type == "MATCH_FOUND":
                if "seat_index" in data:
                    self._my_seat = data.get("seat_index")
                self._show_info("상대를 찾았습니다! 잠시 후 게임이 시작됩니다.")
            elif msg_type == "MATCH_START":
                if not self._match_starting:
                    self._match_starting = True
                    self._pending_game_messages = list(messages[idx + 1 :])
                    self._launch_game(data)
                    break
            elif msg_type == "PLAYER_PRESENCE":
                pass  # handled via ROOM_STATE
            elif msg_type == "ERROR":
                code = data.get("code", "")
                msg = data.get("message", "오류가 발생했습니다.")
                self._error_msg = f"[{code}] {msg}" if code else msg
            elif msg_type == "PING":
                self._ws.send("PONG")
            idx += 1

    def _show_info(self, msg: str, duration: float = 3.0) -> None:
        self._info_msg = msg
        self._info_timer = duration

    # ------------------------------------------------------------------
    # Multiplayer GameScene bootstrap
    # ------------------------------------------------------------------

    def _launch_game(self, match_start_data: dict) -> None:
        """
        Build a GameScene wired for multiplayer and transition to it via the
        loading screen (hangar-door animation).

        match_start_data contains ``my_seat`` (server-assigned seat index).
        """
        my_seat = match_start_data.get("my_seat")
        if my_seat is None:
            my_seat = match_start_data.get("seat_index")
        if my_seat is None:
            my_seat = self._my_seat if self._my_seat is not None else 0
        from fall_in.core.game_manager import GameManager

        bootstrap_messages = list(self._pending_game_messages)
        self._pending_game_messages.clear()
        GameManager().change_scene(
            build_remote_match_loading_scene(
                ws=self._ws,
                my_seat=int(my_seat),
                bootstrap_messages=bootstrap_messages,
            )
        )

    # ------------------------------------------------------------------
    # Scene interface
    # ------------------------------------------------------------------

    def handle_event(self, event: pygame.event.Event) -> None:
        self._btn_leave.handle_event(event)
        self._btn_ready.handle_event(event)
        if self._am_owner:
            self._btn_start.handle_event(event)

    def update(self, dt: float) -> None:
        self._handle_ws_messages()
        if self._info_timer > 0:
            self._info_timer -= dt
            if self._info_timer <= 0:
                self._info_msg = ""
        self._btn_ready.update(dt)
        self._btn_start.update(dt)
        self._btn_leave.update(dt)

    def render(self, screen: pygame.Surface) -> None:
        screen.fill(SAND_BEIGE)

        font_title = get_font(32, "bold")
        room_code = self._room_data.get("room_code", "----")
        title = font_title.render(f"대기실  [{room_code}]", True, AIR_FORCE_BLUE)
        screen.blit(title, title.get_rect(center=(SCREEN_WIDTH // 2, 70)))

        # Seat list
        self._render_seats(screen)

        # Info / error messages
        if self._info_msg:
            info_surf = get_font(18).render(self._info_msg, True, (30, 130, 30))
            screen.blit(info_surf, info_surf.get_rect(center=(SCREEN_WIDTH // 2, SCREEN_HEIGHT - 175)))
        if self._error_msg:
            err_surf = get_font(16).render(self._error_msg, True, (180, 40, 40))
            screen.blit(err_surf, err_surf.get_rect(center=(SCREEN_WIDTH // 2, SCREEN_HEIGHT - 155)))

        # Buttons
        self._btn_leave.render(screen)
        self._btn_ready.render(screen)
        if self._am_owner:
            self._btn_start.render(screen)
        elif not self._am_owner:
            # Non-owner: show hint that only owner can start
            hint = get_font(14).render("방장이 게임을 시작하면 자동으로 입장됩니다.", True, (120, 120, 140))
            screen.blit(hint, hint.get_rect(center=(SCREEN_WIDTH // 2, SCREEN_HEIGHT - 55)))

        # Waiting / starting overlay
        if self._match_starting:
            overlay = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
            overlay.fill((0, 0, 0, 120))
            screen.blit(overlay, (0, 0))
            dots = "." * (int(pygame.time.get_ticks() / 400) % 4)
            msg = get_font(30).render(f"게임 시작 중{dots}", True, WHITE)
            screen.blit(msg, msg.get_rect(center=(SCREEN_WIDTH // 2, SCREEN_HEIGHT // 2)))

    def _render_seats(self, screen: pygame.Surface) -> None:
        # Build a seat_index → participant dict from "participants" list
        participants = self._room_data.get("participants") or []
        by_seat: dict[int, dict] = {p["seat_index"]: p for p in participants}
        host_seat = self._room_data.get("host_seat_index")

        font = get_font(18)
        font_small = get_font(14)
        card_w, card_h = 260, 70
        gap = 20
        num_slots = 4
        total_w = num_slots * card_w + (num_slots - 1) * gap
        start_x = SCREEN_WIDTH // 2 - total_w // 2
        y = 160

        for slot in range(num_slots):
            x = start_x + slot * (card_w + gap)
            rect = pygame.Rect(x, y, card_w, card_h)
            seat = by_seat.get(slot)

            if seat is None:
                # Empty slot
                pygame.draw.rect(screen, (230, 230, 235), rect, border_radius=10)
                pygame.draw.rect(screen, (180, 180, 190), rect, 2, border_radius=10)
                placeholder = font.render("(빈 자리)", True, (160, 160, 170))
                screen.blit(placeholder, placeholder.get_rect(center=rect.center))
            else:
                is_ready = seat.get("is_ready", False)
                is_me = seat.get("display_name") == self._my_display_name
                bg = (220, 245, 220) if is_ready else (230, 240, 255) if is_me else (240, 240, 252)
                border_color = (60, 180, 60) if is_ready else LIGHT_BLUE
                pygame.draw.rect(screen, bg, rect, border_radius=10)
                pygame.draw.rect(screen, border_color, rect, 2, border_radius=10)

                name = seat.get("display_name", f"플레이어 {slot + 1}")
                label = f"{name[:16]}  ◀ 나" if is_me else name[:18]
                name_surf = font.render(label, True, AIR_FORCE_BLUE)
                screen.blit(name_surf, (rect.x + 14, rect.y + 12))

                status = "준비 완료" if is_ready else "대기 중"
                status_color = (40, 150, 40) if is_ready else (120, 120, 140)
                status_surf = font_small.render(status, True, status_color)
                screen.blit(status_surf, (rect.x + 14, rect.y + 40))

                if slot == host_seat:
                    crown = font_small.render("♛ 방장", True, (190, 140, 20))
                    screen.blit(crown, (rect.right - crown.get_width() - 12, rect.y + 12))
