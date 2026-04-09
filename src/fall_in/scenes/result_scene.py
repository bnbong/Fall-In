"""
Result Scene - Round settlement screen showing penalties and scores.
"""

from dataclasses import dataclass
from typing import Callable, Optional

import pygame

from fall_in.scenes.base_scene import Scene
from fall_in.ui.button import Button
from fall_in.utils.asset_loader import AssetLoader, get_font
from fall_in.utils.danger_utils import get_danger_color
from fall_in.core.card import Card
from fall_in.core.player import Player, PlayerType
from fall_in.core.rules import GameRules
from fall_in.config import (
    SCREEN_WIDTH,
    SCREEN_HEIGHT,
    WHITE,
    DANGER_SAFE,
    DANGER_WARNING,
    DANGER_DANGER,
    GAME_OVER_SCORE,
    DANGER_SCORE_THRESHOLDS,
    SCENE_BUTTON_WIDTH,
    SCENE_BUTTON_HEIGHT,
    RESULT_TABLE_ROW_HEIGHT,
    RESULT_TABLE_GAUGE_WIDTH,
    RESULT_TABLE_GAUGE_HEIGHT,
    RESULT_TABLE_BADGE_ICON_SIZE,
    RESULT_TABLE_START_Y,
)


@dataclass
class RemoteResultContext:
    round_result: dict
    public_state: object
    remote_adapter: object
    resume_scene: object
    network_tick_callback: Optional[Callable[[], None]]
    round_ready_callback: Optional[Callable[[], None]]


class ResultScene(Scene):
    """
    Round result/settlement scene.
    Shows penalties earned this round and cumulative scores.
    """

    def __init__(
        self,
        rules: Optional[GameRules] = None,
        players: Optional[list[Player]] = None,
        *,
        remote_context: Optional[RemoteResultContext] = None,
    ):
        super().__init__()
        self.rules = rules
        self.players = players or []
        self._remote_context = remote_context
        self._remote_timeout_remaining = 0.0
        self._remote_acknowledged = False

        if self._remote_context is None:
            if self.rules is None or not self.players:
                raise ValueError("Local ResultScene requires rules and players")
            self.round_number = self.rules.round_state.round_number

            # Track human player's penalty cards for smuggling
            self.human_player = next(
                (p for p in self.players if p.player_type == PlayerType.HUMAN), None
            )

            # Get penalty cards before committing scores
            self.human_penalty_cards: list[Card] = []
            if self.human_player:
                round_penalties = self.rules.get_round_penalties()
                human_penalty = round_penalties.get(self.human_player.player_id)
                if human_penalty:
                    self.human_penalty_cards = list(human_penalty.cards_taken)

            # Calculate scores (this commits the penalties)
            self.round_results = self.rules.commit_round_scores()

            # Check for eliminations
            self.eliminated_players = [p for p in self.players if p.is_eliminated]
            self.game_over = self.rules.game_over
            self.winner = self.rules.winner
        else:
            self._init_remote_result()

        # Buttons
        self.buttons: list[Button] = []
        self._setup_buttons()

        # UI images — pull from pre-loaded manifest cache
        from fall_in.utils.asset_manifest import AssetManifest

        self._ui_images: dict[str, pygame.Surface] = {}
        for category in ("panels", "icons"):
            self._ui_images.update(AssetManifest.get_loaded(category))

        # Load result background image directly
        loader = AssetLoader()
        raw_bg = loader.load_image("ui/backgrounds/result.png")
        self._result_bg = pygame.transform.smoothscale(
            raw_bg, (SCREEN_WIDTH, SCREEN_HEIGHT)
        )

        # Stop game BGM (result scene may use its own BGM later)
        from fall_in.core.audio_manager import AudioManager

        AudioManager().stop_bgm()

    @classmethod
    def from_remote(
        cls,
        *,
        round_result: dict,
        public_state: object,
        remote_adapter: object,
        resume_scene: object,
        network_tick_callback: Optional[Callable[[], None]],
        round_ready_callback: Optional[Callable[[], None]],
    ) -> "ResultScene":
        return cls(
            remote_context=RemoteResultContext(
                round_result=dict(round_result),
                public_state=public_state,
                remote_adapter=remote_adapter,
                resume_scene=resume_scene,
                network_tick_callback=network_tick_callback,
                round_ready_callback=round_ready_callback,
            )
        )

    def _init_remote_result(self) -> None:
        """Populate scene state from server-authoritative multiplayer data."""
        assert self._remote_context is not None

        public = self._remote_context.public_state
        data = dict(self._remote_context.round_result)
        my_seat = self._remote_context.remote_adapter.my_seat
        self.round_number = int(data.get("round_number", public.round_number))
        self.human_penalty_cards = []
        self.round_results = {
            int(seat_index): (
                int(value),
                int(
                    data.get("total_scores", {}).get(
                        str(seat_index), data.get("total_scores", {}).get(seat_index, 0)
                    )
                ),
            )
            for seat_index, value in (data.get("round_danger") or {}).items()
        }

        # Ensure every visible seat has a score tuple, even if round_danger omitted it.
        for seat in public.seats:
            current = self.round_results.get(seat.seat_index)
            if current is None:
                total = int(
                    (data.get("total_scores") or {}).get(
                        seat.seat_index,
                        (data.get("total_scores") or {}).get(str(seat.seat_index), 0),
                    )
                )
                self.round_results[seat.seat_index] = (0, total)

        self.players = []
        for seat in sorted(public.seats, key=lambda item: item.seat_index):
            player = Player(
                name="나" if seat.seat_index == my_seat else seat.display_name,
                player_type=PlayerType.HUMAN
                if seat.seat_index == my_seat
                else PlayerType.AI,
                player_id=seat.seat_index,
            )
            _, total = self.round_results.get(seat.seat_index, (0, 0))
            player.penalty_score = total
            player.is_eliminated = seat.seat_index in {
                int(value) for value in data.get("eliminated_seats", [])
            }
            self.players.append(player)

        self.human_player = next(
            (player for player in self.players if player.player_id == my_seat),
            None,
        )
        self.eliminated_players = [p for p in self.players if p.is_eliminated]
        self.game_over = bool(data.get("game_over", False))
        winner_seat = data.get("winner_seat")
        if winner_seat is not None:
            winner_seat = int(winner_seat)
        self.winner = next(
            (player for player in self.players if player.player_id == winner_seat),
            None,
        )
        self._remote_timeout_remaining = float(data.get("timeout_seconds", 0.0))

    def _setup_buttons(self) -> None:
        """Setup continue/title buttons."""
        button_width = SCENE_BUTTON_WIDTH
        button_height = SCENE_BUTTON_HEIGHT
        button_x = SCREEN_WIDTH // 2 - button_width // 2
        button_y = SCREEN_HEIGHT - 80

        if self._remote_context is not None:
            self.buttons.append(
                Button(
                    x=button_x,
                    y=button_y,
                    width=button_width,
                    height=button_height,
                    text="확인",
                    callback=self._confirm_remote_continue,
                )
            )
            return

        if self.game_over:
            self.buttons.append(
                Button(
                    x=button_x,
                    y=button_y,
                    width=button_width,
                    height=button_height,
                    text="결과 확인",
                    callback=self._go_to_game_over,
                )
            )
        else:
            self.buttons.append(
                Button(
                    x=button_x,
                    y=button_y,
                    width=button_width,
                    height=button_height,
                    text="다음 라운드",
                    callback=self._continue_game,
                )
            )

    # ------------------------------------------------------------------
    # Navigation helpers (shared smuggling check logic)
    # ------------------------------------------------------------------

    def _get_collected_penalty_cards(self) -> list[Card]:
        """Filter penalty cards to only collected (interviewed) soldiers."""
        from fall_in.core.smuggling_manager import SmugglingManager

        smuggling = SmugglingManager()
        smuggling.update_max_count()
        return [
            card
            for card in self.human_penalty_cards
            if smuggling.is_soldier_collected(card.number)
        ]

    def _navigate_via_smuggling_or_direct(self, *, is_game_over: bool) -> None:
        """
        Navigate to smuggling scene if there are collected penalty cards,
        otherwise go directly to the next scene.

        Args:
            is_game_over: If True, the destination after smuggling is GameOverScene.
        """
        from fall_in.core.game_manager import GameManager

        collected_penalty_cards = self._get_collected_penalty_cards()

        if collected_penalty_cards:
            from fall_in.scenes.smuggling_scene import SmugglingScene

            round_penalty = (
                self.round_results.get(self.human_player.player_id, (0, 0))[0]
                if self.human_player
                else 0
            )
            smuggling_scene = SmugglingScene(
                rules=self.rules,
                penalty_cards=collected_penalty_cards,
                round_penalty=round_penalty,
                is_game_over=is_game_over,
            )
            GameManager().change_scene(smuggling_scene)
        elif is_game_over:
            from fall_in.scenes.game_over_scene import GameOverScene

            GameManager().change_scene(
                GameOverScene(
                    winner=self.winner,
                    players=self.players,
                    round_number=self.round_number,
                )
            )
        else:
            from fall_in.scenes.game_scene import GameScene

            GameManager().change_scene(GameScene(rules=self.rules))

    def _continue_game(self) -> None:
        """Continue to next round (optionally via smuggling)."""
        self._navigate_via_smuggling_or_direct(is_game_over=False)

    def _go_to_game_over(self) -> None:
        """Go to game over scene (optionally via smuggling)."""
        self._navigate_via_smuggling_or_direct(is_game_over=True)

    def _confirm_remote_continue(self) -> None:
        """Acknowledge the multiplayer settlement screen once per client."""
        if self._remote_context is None or self._remote_acknowledged:
            return
        self._remote_acknowledged = True
        if self.buttons:
            self.buttons[0].text = "확인 완료"
        callback = self._remote_context.round_ready_callback
        if callback is not None:
            callback()

    # ------------------------------------------------------------------
    # Event / Update / Render
    # ------------------------------------------------------------------

    def handle_event(self, event: pygame.event.Event) -> None:
        """Handle events."""
        for button in self.buttons:
            button.handle_event(event)

        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_SPACE or event.key == pygame.K_RETURN:
                if self._remote_context is not None:
                    self._confirm_remote_continue()
                elif self.game_over:
                    self._go_to_game_over()
                else:
                    self._continue_game()

    def update(self, dt: float) -> None:
        """Update scene."""
        for button in self.buttons:
            button.update(dt)

        if self._remote_context is None:
            return

        if self._remote_context.network_tick_callback is not None:
            self._remote_context.network_tick_callback()

        self._remote_timeout_remaining = max(0.0, self._remote_timeout_remaining - dt)
        if self._remote_timeout_remaining <= 0.0 and not self._remote_acknowledged:
            self._confirm_remote_continue()

        pop_match_result = getattr(
            self._remote_context.remote_adapter, "pop_match_result", None
        )
        if callable(pop_match_result):
            match_result = pop_match_result()
            if match_result is not None:
                self._remote_context.resume_scene._go_to_remote_game_over(match_result)
                return

        consume_selecting = getattr(
            self._remote_context.remote_adapter,
            "consume_selecting_phase_started",
            None,
        )
        if callable(consume_selecting):
            remaining = consume_selecting()
            if remaining is not None:
                self._remote_context.resume_scene._reset_remote_selecting_phase(
                    remaining
                )
                from fall_in.core.audio_manager import AudioManager
                from fall_in.core.game_manager import GameManager, GameState
                from fall_in.config import GAME_BGM_PATH

                AudioManager().play_bgm(GAME_BGM_PATH)
                gm = GameManager()
                gm.state = GameState.PLAYING
                gm.change_scene(self._remote_context.resume_scene)

    def render(self, screen: pygame.Surface) -> None:
        """Render result screen."""
        title_font = get_font(36, "bold")
        header_font = get_font(24, "bold")
        font = get_font(20)
        small_font = get_font(16)

        # Full-screen result background
        screen.blit(self._result_bg, (0, 0))

        # Title
        title = title_font.render(f"라운드 {self.round_number} 정산", True, WHITE)
        title_rect = title.get_rect(center=(SCREEN_WIDTH // 2, 50))
        screen.blit(title, title_rect)

        # Table header
        start_y = RESULT_TABLE_START_Y
        col_x = [250, 450, 600, 780]

        headers = ["플레이어", "이번 라운드", "누적 위험도", "상태"]
        for i, header in enumerate(headers):
            text = header_font.render(header, True, WHITE)
            screen.blit(text, (col_x[i], start_y))

        # Divider
        pygame.draw.line(
            screen,
            WHITE,
            (200, start_y + 35),
            (SCREEN_WIDTH - 200, start_y + 35),
            2,
        )

        # Player rows
        row_y = start_y + 50
        row_height = RESULT_TABLE_ROW_HEIGHT

        for player in self.players:
            player_id = player.player_id
            round_danger, total = self.round_results.get(player_id, (0, 0))

            if player.is_eliminated:
                pygame.draw.rect(
                    screen,
                    (255, 200, 200),
                    (200, row_y - 5, SCREEN_WIDTH - 400, row_height - 10),
                    border_radius=5,
                )

            # Player name
            screen.blit(font.render(player.name, True, WHITE), (col_x[0], row_y + 10))

            # Round penalty
            penalty_color = DANGER_DANGER if round_danger > 0 else DANGER_SAFE
            screen.blit(
                font.render(f"+{round_danger}", True, penalty_color),
                (col_x[1], row_y + 10),
            )

            # Total score with gauge
            gauge_width = RESULT_TABLE_GAUGE_WIDTH
            gauge_height = RESULT_TABLE_GAUGE_HEIGHT
            fill_ratio = min(total / GAME_OVER_SCORE, 1.0)
            fill_color = get_danger_color(total)

            pygame.draw.rect(
                screen,
                (200, 200, 200),
                (col_x[2], row_y + 12, gauge_width, gauge_height),
                border_radius=3,
            )
            if fill_ratio > 0:
                pygame.draw.rect(
                    screen,
                    fill_color,
                    (col_x[2], row_y + 12, int(gauge_width * fill_ratio), gauge_height),
                    border_radius=3,
                )
            pygame.draw.rect(
                screen,
                WHITE,
                (col_x[2], row_y + 12, gauge_width, gauge_height),
                width=1,
                border_radius=3,
            )

            total_text = small_font.render(f"{total}/{GAME_OVER_SCORE}", True, WHITE)
            screen.blit(total_text, (col_x[2] + gauge_width + 10, row_y + 12))

            # Status with badge icons
            if player.is_eliminated:
                badge_key = "badge_eliminated"
                status_text = font.render("탈락!", True, DANGER_DANGER)
            elif total >= DANGER_SCORE_THRESHOLDS["danger"]:
                badge_key = "badge_danger"
                status_text = font.render("위험", True, DANGER_WARNING)
            else:
                badge_key = "badge_survived"
                status_text = font.render("생존", True, DANGER_SAFE)

            if badge_key in self._ui_images:
                raw_icon = self._ui_images[badge_key]
                icon_h = RESULT_TABLE_BADGE_ICON_SIZE
                aspect = raw_icon.get_width() / max(raw_icon.get_height(), 1)
                icon_w = int(icon_h * aspect)
                badge_icon = pygame.transform.smoothscale(raw_icon, (icon_w, icon_h))
                screen.blit(badge_icon, (col_x[3], row_y + 8))
            else:
                screen.blit(status_text, (col_x[3], row_y + 10))

            row_y += row_height

        # Game over message
        if self.game_over:
            msg_y = SCREEN_HEIGHT - 150
            if self.eliminated_players:
                msg = f"{', '.join(p.name for p in self.eliminated_players)} 탈락!"
            else:
                msg = "게임 종료!"

            # Popup background
            msg_text = header_font.render(msg, True, DANGER_DANGER)
            popup_w = msg_text.get_width() + 40
            popup_h = 50
            popup_rect = pygame.Rect(
                SCREEN_WIDTH // 2 - popup_w // 2,
                msg_y - popup_h // 2,
                popup_w,
                popup_h,
            )
            if "popup_message" in self._ui_images:
                popup_bg = pygame.transform.smoothscale(
                    self._ui_images["popup_message"],
                    (popup_rect.width, popup_rect.height),
                )
                screen.blit(popup_bg, popup_rect.topleft)
            else:
                pygame.draw.rect(screen, (255, 240, 240), popup_rect, border_radius=8)
                pygame.draw.rect(
                    screen, DANGER_DANGER, popup_rect, width=2, border_radius=8
                )
            screen.blit(msg_text, msg_text.get_rect(center=popup_rect.center))

        # Buttons
        for button in self.buttons:
            button.render(screen)

        # Hint
        if self._remote_context is None:
            hint_label = "[SPACE] 또는 버튼 클릭으로 계속"
        elif self._remote_acknowledged:
            hint_label = "다른 플레이어를 기다리는 중..."
        else:
            hint_label = "[SPACE] 또는 버튼 클릭으로 확인"
        hint_text = small_font.render(hint_label, True, WHITE)
        screen.blit(
            hint_text,
            (SCREEN_WIDTH // 2 - hint_text.get_width() // 2, SCREEN_HEIGHT - 30),
        )

        if self._remote_context is not None:
            info_font = get_font(16)
            countdown = max(0, int(self._remote_timeout_remaining + 0.999))
            countdown_label = (
                f"자동 진행까지 {countdown}초"
                if not self._remote_acknowledged
                else f"다음 단계 대기 중 ({countdown}초)"
            )
            countdown_surf = info_font.render(countdown_label, True, WHITE)
            screen.blit(
                countdown_surf,
                countdown_surf.get_rect(
                    center=(SCREEN_WIDTH // 2, SCREEN_HEIGHT - 120)
                ),
            )
