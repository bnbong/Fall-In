"""
Game Scene - Main gameplay screen with isometric board.

Integrates actual game rules, AI players, and sequential card placement
animations on a 4-row isometric board.
"""

import random
from enum import Enum, auto
from typing import Callable, Optional

import pygame

from fall_in.scenes.base_scene import Scene
from fall_in.utils.debug_overlay import DebugOverlayMixin, DebugHotkey
from fall_in.utils.asset_loader import get_font, AssetLoader
from fall_in.utils.tween import Tween, TweenGroup
from fall_in.utils.danger_utils import (
    TileType,
    get_danger_color,
    get_tile_type_by_danger,
)
from fall_in.utils.text_utils import draw_outlined_text
from fall_in.core.card import Card
from fall_in.core.player import Player, PlayerType, create_players
from fall_in.core.rules import GameRules, TurnResult
from fall_in.ai.ai_player import create_ai_players
from fall_in.entities.soldier_figure import SoldierFigure
from fall_in.entities.commander import Commander
from fall_in.entities.battalion_card import BattalionCard
from fall_in.entities.dust_particle import DustEffect
from fall_in.config import (
    SCREEN_WIDTH,
    SCREEN_HEIGHT,
    AIR_FORCE_BLUE,
    WHITE,
    LIGHT_BLUE,
    DANGER_SAFE,
    DANGER_WARNING,
    DANGER_DANGER,
    NUM_ROWS,
    MAX_CARDS_PER_ROW,
    ISO_TILE_WIDTH,
    ISO_TILE_HEIGHT,
    ROW_SPACING,
    BOARD_OFFSET_X,
    BOARD_OFFSET_Y,
    GAME_OVER_SCORE,
    Difficulty,
    TURN_TIMEOUT_SECONDS,
    TIMER_WARNING_THRESHOLD,
    TIMER_DANGER_THRESHOLD,
    # Hand layout
    HAND_FAN_SPREAD,
    HAND_CARD_OVERLAP,
    HAND_Y_OFFSET,
    HAND_HOVER_POP_DISTANCE,
    HAND_HOVER_SCALE,
    # Board
    ROW_OFFSETS,
    BARRACKS_X,
    BARRACKS_Y,
    # UI
    UI_TOP_BAR_Y,
    UI_TOP_BAR_HEIGHT,
    UI_ELEMENT_PLAYER_ORDER_X,
    UI_ELEMENT_DANGER_GAUGE_WIDTH,
    UI_ELEMENT_DANGER_GAUGE_HEIGHT,
    ICON_HANGER_X,
    TURN_LOG_X,
    TURN_LOG_Y,
    TURN_LOG_WIDTH,
    DEALING_CARD_COLOR,
    DEALING_CARD_BORDER_COLOR,
    TOP_BAR_BG_COLOR,
    TOP_BAR_OUTLINE_COLOR,
    SCREEN_SHAKE_DURATION,
    SCREEN_SHAKE_PADDING,
    CARD_DEAL_DELAY,
    CARD_DEAL_DURATION,
    AI_THINKING_DURATION,
    PLACEMENT_PAUSE_DURATION,
    ORDER_ANNOUNCE_SHUFFLE_DURATION,
    ORDER_ANNOUNCE_HOLD_DURATION,
    ORDER_ANNOUNCE_SHRINK_DURATION,
)


class GamePhase(Enum):
    """UI game phase states."""

    STARTING = auto()
    ORDER_ANNOUNCE = auto()
    DEALING = auto()
    SELECTING = auto()
    AI_THINKING = auto()
    REVEALING = auto()
    PLACING_PLAYER = auto()
    PENALTY_ANIMATION = auto()
    ROW_SELECT = auto()
    ROUND_END = auto()
    GAME_OVER = auto()


class GameScene(Scene, DebugOverlayMixin):
    """
    Main game scene with isometric 4x6 board.
    Integrates with game rules for actual gameplay.
    """

    ROW_OFFSETS = ROW_OFFSETS

    def __init__(
        self, difficulty: str = Difficulty.NORMAL, rules: Optional[GameRules] = None
    ):
        super().__init__()

        # Create or reuse game rules
        if rules is None:
            self.players = create_players()
            self.rules = GameRules(self.players)
            self.is_new_game = True
        else:
            self.rules = rules
            self.players = rules.players
            self.is_new_game = False

        self.human_player = self.players[0]
        self.ai_controllers = create_ai_players(self.players, difficulty)
        self.difficulty = difficulty

        # Game UI state
        self.phase = GamePhase.STARTING
        self.selected_card_index: Optional[int] = None
        self.dragging = False
        self.drag_pos = (0, 0)

        # Turn timer
        self.turn_timer = TURN_TIMEOUT_SECONDS

        # Turn log for display
        self.turn_log: list[TurnResult] = []

        # Sequential placement state
        self.placement_queue: list[tuple] = []
        self.current_placement: Optional[TurnResult] = None
        self.placement_tween: Optional[Tween] = None
        self.penalty_tweens: TweenGroup = TweenGroup()
        self.penalty_cards_animating: list[tuple[Card, Tween]] = []

        # Dealing animation state
        self.dealing_cards: list[tuple[Card, Tween]] = []
        self.dealt_card_count = 0

        # Animation state
        self.phase_timer = 0.0
        self.message = ""
        self.message_timer = 0.0

        # Commander (left side)
        self.commander = Commander()

        # Settings popup
        from fall_in.ui.settings_popup import SettingsPopup

        self._settings_popup = SettingsPopup()

        # Settings gear button (top-right corner)
        self._settings_btn_center = (SCREEN_WIDTH - 230, 30)
        self._settings_btn_radius = 18

        # Emote popup (PR-07) — palette that opens on player icon click.
        # Wire the send-side by calling set_emote_send_callback() after
        # construction.  In single-player the palette opens but does nothing.
        from fall_in.ui.emote_popup import EmotePopup

        self._emote_popup = EmotePopup()
        # Route emote button clicks through _on_emote_selected so the scene
        # can own the send logic rather than the popup itself.
        self._emote_popup.set_callback(self._on_emote_selected)
        # External send callback — set by the networking layer for multiplayer.
        self._emote_send_callback: Optional[Callable[[str], None]] = None
        self._card_select_callback: Optional[Callable[[int], None]] = None

        # Player icon position — matches _draw_player_icon_ui()
        self._player_icon_center = (SCREEN_WIDTH - 170, UI_TOP_BAR_Y + 20)
        self._player_icon_radius = 28

        # Per-seat emote display state: seat_index → (emote_label, ttl_seconds)
        # Populated from RemoteGameAdapter in multiplayer (drained in update()),
        # or directly via show_emote() in single-player / tests.
        self._emote_display: dict[int, tuple[str, float]] = {}
        # Display duration for each received emote (seconds)
        self._emote_display_duration: float = 3.0

        # RemoteGameAdapter for multiplayer — set by the networking layer.
        # When set, update() drains pending emotes from it each frame.
        self._remote_adapter: Optional[object] = None  # RemoteGameAdapter

        # Optional network tick callback — set by the multiplayer bootstrap.
        # Called once per frame (before emote drain) so the networking layer
        # can pump the WS client and route incoming messages to the adapter.
        # TODO (PR-09 WS client bootstrap): set via set_network_tick_callback().
        self._network_tick_callback: Optional[Callable[[], None]] = None
        self._remote_reveal_step_timer = 0.0
        self._remote_reveal_step_duration = 0.42
        self._remote_current_reveal_seat: Optional[int] = None
        self._remote_round_result: Optional[dict] = None
        self._remote_round_result_timer = 0.0
        self._remote_round_result_acknowledged = False
        self._remote_selection_sent_pending = False
        self._round_ready_callback: Optional[Callable[[], None]] = None
        self._exit_match_callback: Optional[Callable[[], None]] = None

        # Timeout SFX (plays every second when timer <= 5)
        from fall_in.config import SOUNDS_DIR

        self._timeout_sfx: pygame.mixer.Sound | None = None
        try:
            sfx_path = SOUNDS_DIR / "sfx" / "timeout.wav"
            if sfx_path.exists():
                self._timeout_sfx = pygame.mixer.Sound(str(sfx_path))
                from fall_in.core.audio_manager import AudioManager

                self._timeout_sfx.set_volume(AudioManager().sfx_volume)
        except Exception:
            pass
        self._last_timeout_tick: int = -1  # last second boundary we played SFX at

        # Dust effect system
        self.dust_effect = DustEffect()

        # Screen shake state
        self.screen_shake_timer = 0.0
        self.screen_shake_intensity = 0
        self.screen_shake_offset = (0, 0)

        # Persistent soldier figures on board (card.number -> SoldierFigure)
        self.soldier_figures: dict[int, SoldierFigure] = {}

        # Order announce animation state
        self._order_announce_timer = 0.0
        self._order_announce_sub = 0  # 0=shuffle, 1=hold, 2=shrink
        self._prev_order: list = []  # previous round player order

        # Load background image (with extra padding for shake)
        loader = AssetLoader()
        self.background_image = loader.load_image(
            "ui/backgrounds/ingame_background.png"
        )
        self.background_image = pygame.transform.smoothscale(
            self.background_image,
            (
                SCREEN_WIDTH + SCREEN_SHAKE_PADDING * 2,
                SCREEN_HEIGHT + SCREEN_SHAKE_PADDING * 2,
            ),
        )

        # Load tile images
        self.tile_images = {
            TileType.EMPTY.value: loader.load_image("entity/tile_1.png"),
            TileType.SAFE.value: loader.load_image("entity/tile_2.png"),
            TileType.WARNING.value: loader.load_image("entity/tile_3.png"),
            TileType.DANGER.value: loader.load_image("entity/tile_4.png"),
        }
        for key in self.tile_images:
            self.tile_images[key] = pygame.transform.smoothscale(
                self.tile_images[key], (int(ISO_TILE_WIDTH), int(ISO_TILE_HEIGHT))
            )

        # HUD images — pull from pre-loaded manifest cache
        from fall_in.utils.asset_manifest import AssetManifest

        self._hud_images: dict[str, pygame.Surface] = AssetManifest.get_loaded("hud")
        self._hud_images.update(AssetManifest.get_loaded("panels"))

        # Debug overlay (via mixin)
        self.init_debug_overlay(self._get_game_debug_hotkeys())

        # Start round
        self._start_new_round()

    # ------------------------------------------------------------------
    # Round lifecycle
    # ------------------------------------------------------------------

    def _start_new_round(self) -> None:
        """Start a new round."""
        # Save previous order before rotation
        self._prev_order = list(self.rules.player_order)

        self.rules.start_new_round()
        self.turn_log.clear()
        self.placement_queue.clear()
        self.soldier_figures.clear()

        committed = self.rules.get_player_committed_score(self.human_player)
        self.commander.set_expression_from_danger(committed)

        # Start dealing animation in background
        self._start_dealing_animation_cards_only()

        # Start order announce overlay
        self._order_announce_timer = 0.0
        round_num = self.rules.round_state.round_number

        self._order_announce_sub = 0 if round_num > 1 else 1
        self.phase = GamePhase.ORDER_ANNOUNCE

        from fall_in.core.audio_manager import AudioManager
        from fall_in.config import GAME_BGM_PATH

        AudioManager().play_bgm(GAME_BGM_PATH)

    def _start_dealing_animation_cards_only(self) -> None:
        """Setup dealing card tweens without changing the phase."""
        self.dealing_cards.clear()
        self.dealt_card_count = 0

        hand = self.human_player.hand
        num_cards = len(hand)
        card_width = 60
        spacing = 65
        total_width = num_cards * card_width + (num_cards - 1) * (spacing - card_width)
        start_x = (SCREEN_WIDTH - total_width) // 2
        hand_y = SCREEN_HEIGHT - 120

        for i, card in enumerate(hand):
            target_x = start_x + i * spacing + card_width // 2
            target_y = hand_y + 40

            tween = Tween(
                start=(BARRACKS_X, BARRACKS_Y),
                end=(target_x, target_y),
                duration=CARD_DEAL_DURATION,
                easing="ease_out",
                delay=i * CARD_DEAL_DELAY,
            )
            self.dealing_cards.append((card, tween))

    def _update_dealing_animation(self, dt: float) -> None:
        """Update dealing animation and check for completion."""
        all_complete = True
        arrived_count = 0

        for _, tween in self.dealing_cards:
            tween.update(dt)
            if tween.is_complete:
                arrived_count += 1
            else:
                all_complete = False

        # Play card_draw SFX for each newly arrived card
        if arrived_count > self.dealt_card_count:
            from fall_in.core.audio_manager import AudioManager

            AudioManager().play_sfx("sfx/card_draw.wav")

        self.dealt_card_count = arrived_count

        if all_complete and self.phase == GamePhase.DEALING:
            self.phase = GamePhase.SELECTING
            self.turn_timer = TURN_TIMEOUT_SECONDS
            self.dealing_cards.clear()

    # ------------------------------------------------------------------
    # Isometric helpers
    # ------------------------------------------------------------------

    def _cart_to_iso(self, x: int, y: int) -> tuple[int, int]:
        """
        Convert cartesian (col, row) to isometric screen coordinates.

        Args:
            x: Column position within row (card index).
            y: Row index (0-3).

        Returns:
            (iso_x, iso_y) screen coordinates.
        """
        row_x_offset, row_y_offset = (
            self.ROW_OFFSETS[y] if y < len(self.ROW_OFFSETS) else (0, 0)
        )

        iso_x = BOARD_OFFSET_X + (y - x) * (ISO_TILE_WIDTH // 2) + row_x_offset
        iso_y = (
            BOARD_OFFSET_Y
            + (x + y) * (ISO_TILE_HEIGHT // 2)
            + y * ROW_SPACING
            + row_y_offset
        )
        return int(iso_x), int(iso_y)

    # ------------------------------------------------------------------
    # Board drawing
    # ------------------------------------------------------------------

    def _draw_isometric_tile(
        self,
        screen: pygame.Surface,
        x: int,
        y: int,
        tile_type: TileType = TileType.EMPTY,
    ) -> None:
        """Draw a single isometric tile using tile images."""
        iso_x, iso_y = self._cart_to_iso(x, y)
        tile_image = self.tile_images.get(
            tile_type.value, self.tile_images[TileType.EMPTY.value]
        )
        tile_rect = tile_image.get_rect(center=(iso_x, iso_y))
        screen.blit(tile_image, tile_rect)

    def _draw_board(self, screen: pygame.Surface) -> None:
        """Draw the isometric game board with soldier figures."""
        board_rows = self._get_display_board_rows()

        # Collect all tiles with depth for proper z-ordering
        tiles_to_draw = []
        for row_idx in range(NUM_ROWS):
            for col in range(MAX_CARDS_PER_ROW + 1):
                visual_col = MAX_CARDS_PER_ROW - col
                row = board_rows[row_idx] if row_idx < len(board_rows) else []

                tile_type = (
                    get_tile_type_by_danger(row[col].danger)
                    if col < len(row)
                    else TileType.EMPTY
                )
                iso_x, iso_y = self._cart_to_iso(visual_col, row_idx)
                tiles_to_draw.append((iso_y, visual_col, row_idx, tile_type))

        tiles_to_draw.sort(key=lambda t: t[0])

        for _, visual_col, row_idx, tile_type in tiles_to_draw:
            self._draw_isometric_tile(screen, visual_col, row_idx, tile_type)

        # Draw soldier figures (sorted by depth)
        soldiers_to_draw = []
        for row_idx in range(NUM_ROWS):
            row = board_rows[row_idx] if row_idx < len(board_rows) else []
            for col in range(len(row)):
                visual_col = MAX_CARDS_PER_ROW - col
                card = row[col]
                iso_x, iso_y = self._cart_to_iso(visual_col, row_idx)
                soldiers_to_draw.append((iso_y, iso_x, iso_y, card))

        soldiers_to_draw.sort(key=lambda s: s[0])

        for _, iso_x, iso_y, card in soldiers_to_draw:
            if card.number not in self.soldier_figures:
                figure = SoldierFigure(card)
                figure.start_drop(iso_y)
                self.soldier_figures[card.number] = figure
            else:
                figure = self.soldier_figures[card.number]
            figure.render(screen, iso_x, iso_y, int(ISO_TILE_HEIGHT))

    def _to_display_card(self, card_like) -> Card:
        """
        Convert a network DTO or local Card into a renderable Card object.

        Multiplayer public/private state carries only number + danger, which is
        enough for the current UI fallback visuals.
        """
        if isinstance(card_like, Card):
            return card_like
        return Card(number=card_like.number, danger=card_like.danger)

    def _get_public_state(self):
        """Return the latest multiplayer public state, or None in single-player."""
        if self._remote_adapter is None:
            return None
        return self._remote_adapter.get_public_state()

    def _get_private_state(self):
        """Return the latest multiplayer private hand state, or None if unavailable."""
        if self._remote_adapter is None:
            return None
        return self._remote_adapter.get_private_state()

    def _get_display_board_rows(self) -> list[list[Card]]:
        """Return board rows suitable for rendering in local or remote play."""
        public = self._get_public_state()
        if public is None:
            return self.rules.board.rows
        return [
            [self._to_display_card(card) for card in row]
            for row in public.board_rows
        ]

    def _get_display_hand_cards(self) -> list[Card]:
        """Return the local player's visible hand for the current mode."""
        private = self._get_private_state()
        if private is None:
            return self.human_player.hand
        cards = [self._to_display_card(card) for card in private.hand]
        # The server keeps the selected card in the hand until turn resolution.
        # Hide it from the display once the selection has been confirmed so the
        # player doesn't see a ghost card (especially on the last turn).
        selected_num = getattr(self, "_last_remote_selected_card_number", None)
        if selected_num is not None and private.has_selected:
            cards = [c for c in cards if c.number != selected_num]
        return cards

    def _get_round_number(self) -> int:
        """Return the authoritative round number for the current mode."""
        public = self._get_public_state()
        if public is not None:
            return public.round_number
        return self.rules.round_state.round_number

    def _get_local_committed_score(self) -> int:
        """Return the committed danger score for the local seat."""
        public = self._get_public_state()
        if public is not None:
            return public.committed_scores.get(self._get_my_seat(), 0)
        return self.rules.get_player_committed_score(self.human_player)

    def _get_local_round_penalty_card_count(self) -> int:
        """Return the local player's penalty-card count for this round."""
        if self._remote_adapter is not None:
            return self._remote_adapter.get_round_penalty_card_count(self._get_my_seat())
        try:
            return int(self.rules.get_player_round_penalty_count(self.human_player))
        except Exception:
            return 0

    def _consume_selection_timer(self, dt: float, *, on_timeout: Optional[Callable[[], None]]) -> bool:
        """
        Advance the selection timer with hitch protection.

        Large frame spikes can otherwise chew through most of the timer in one
        update and make the turn look like it expired early.
        """
        timer_dt = max(0.0, min(float(dt), 0.25))
        self.turn_timer = max(0.0, self.turn_timer - timer_dt)
        if self.turn_timer <= 5.0 and self._timeout_sfx is not None:
            current_tick = int(self.turn_timer)
            if current_tick != self._last_timeout_tick and self.turn_timer > 0:
                self._last_timeout_tick = current_tick
                self._timeout_sfx.play()
        if self.turn_timer > 0:
            return False
        self._last_timeout_tick = -1
        if on_timeout is not None:
            on_timeout()
            return True
        return False

    def _get_player_order_entries(self) -> list[tuple[str, bool]]:
        """
        Return player-order labels for the current mode.

        Each item is ``(label, is_local_player)``.
        """
        public = self._get_public_state()
        if public is None:
            entries = []
            for player in self.rules.player_order:
                entries.append(
                    (
                        "나" if player == self.human_player else player.name.replace("AI ", ""),
                        player == self.human_player,
                    )
                )
            return entries

        my_seat = self._get_my_seat()
        entries = []
        for seat_index in public.player_order_seats:
            if seat_index == my_seat:
                entries.append(("나", True))
            else:
                entries.append((str(seat_index + 1), False))
        return entries

    def _get_multiplayer_display_name(self, seat_index: int) -> str:
        """Return the display name for a multiplayer seat (nickname or AI name)."""
        public = self._get_public_state()
        if public is None:
            return f"P{seat_index + 1}"
        seat = public.get_seat(seat_index)
        if seat is None:
            return f"P{seat_index + 1}"
        return seat.display_name or f"P{seat_index + 1}"

    def _advance_remote_reveal(self, dt: float) -> None:
        if self._remote_adapter is None:
            return

        # Update running penalty tweens.
        if self.penalty_cards_animating:
            if self.penalty_tweens.update(dt):
                self.penalty_cards_animating.clear()

        if self._remote_reveal_step_timer > 0:
            self._remote_reveal_step_timer = max(0.0, self._remote_reveal_step_timer - dt)
            if self._remote_reveal_step_timer > 0:
                return

        next_step = self._remote_adapter.pop_next_reveal_step()
        if next_step is not None:
            step, snapshot = next_step
            self._remote_adapter.apply_public_state(snapshot)
            self._remote_current_reveal_seat = step.seat_index
            actor = "나" if step.seat_index == self._get_my_seat() else self._get_multiplayer_display_name(step.seat_index)
            self.message = f"{actor}: #{step.card_number}"

            if step.penalty_score > 0 and step.penalty_card_count > 0:
                # Extend the reveal timer to allow the penalty animation to play.
                anim_duration = 0.4 + step.penalty_card_count * 0.1
                self._remote_reveal_step_timer = self._remote_reveal_step_duration + anim_duration
                self.message_timer = self._remote_reveal_step_timer
                self._start_remote_penalty_animation(step)
            else:
                self._remote_reveal_step_timer = self._remote_reveal_step_duration
                self.message_timer = self._remote_reveal_step_duration
            return

        if not self._remote_adapter.is_turn_reveal_active():
            self._remote_current_reveal_seat = None
            for state in self._remote_adapter.flush_post_reveal_public_states():
                self._remote_adapter.apply_public_state(state)

    def _start_remote_penalty_animation(self, step) -> None:
        """Start penalty card animation for a multiplayer reveal step."""
        from types import SimpleNamespace

        self.penalty_cards_animating.clear()
        self.penalty_tweens = TweenGroup()

        my_seat = self._get_my_seat()
        other_seats = self._get_other_seat_order()

        if step.seat_index == my_seat:
            target_x, target_y = ICON_HANGER_X + 48, UI_TOP_BAR_Y + 18
        elif step.seat_index in other_seats:
            panel_index = other_seats.index(step.seat_index)
            panel_w, panel_h = 200, 70
            panel_spacing = 10
            panel_count = len(other_seats)
            total_h = panel_count * panel_h + max(0, panel_count - 1) * panel_spacing
            panel_area_top = UI_TOP_BAR_HEIGHT + 10
            panel_area_bottom = SCREEN_HEIGHT - 220
            panel_start_y = panel_area_top + (panel_area_bottom - panel_area_top - total_h) // 2
            panel_x = SCREEN_WIDTH - panel_w - 10
            target_x = panel_x + panel_w // 2
            target_y = panel_start_y + panel_index * (panel_h + panel_spacing) + panel_h // 2
        else:
            target_x, target_y = SCREEN_WIDTH // 2, SCREEN_HEIGHT // 2

        for i in range(step.penalty_card_count):
            tween = Tween(
                start=(BOARD_OFFSET_X, BOARD_OFFSET_Y + 50),
                end=(target_x, target_y),
                duration=0.4 + i * 0.1,
                easing="ease_in",
            )
            proxy_card = SimpleNamespace(number=step.card_number, danger=step.card_danger)
            self.penalty_cards_animating.append((proxy_card, tween))
            self.penalty_tweens.add(tween)

        if step.seat_index == my_seat:
            self.commander.say_penalty_taken()

    def _has_remote_round_result_overlay(self) -> bool:
        return getattr(self, "_remote_round_result", None) is not None

    def _is_remote_reveal_in_progress(self) -> bool:
        if self._remote_adapter is None:
            return False
        if getattr(self, "_remote_current_reveal_seat", None) is not None:
            return True
        has_pending = getattr(self._remote_adapter, "has_pending_reveal_steps", None)
        if callable(has_pending) and has_pending():
            return True
        is_active = getattr(self._remote_adapter, "is_turn_reveal_active", None)
        if callable(is_active) and is_active():
            return True
        return getattr(self, "_remote_reveal_step_timer", 0.0) > 0

    def _is_local_player_eliminated(self) -> bool:
        """Return True when the local seat is eliminated in multiplayer."""
        private = self._get_private_state()
        if private is None:
            return False
        return private.is_eliminated

    def _can_interact_with_cards(self) -> bool:
        if self._remote_adapter is None:
            return self.phase == GamePhase.SELECTING

        if self._is_local_player_eliminated():
            return False
        public = self._get_public_state()
        if public is None or public.phase != "SELECTING":
            return False
        if self._has_remote_round_result_overlay():
            return False
        if self._is_remote_reveal_in_progress():
            return False
        return not self._is_waiting_for_other_players()

    def _is_waiting_for_other_players(self) -> bool:
        if self._remote_adapter is None:
            return False
        public = self._get_public_state()
        private = self._get_private_state()
        if public is None or public.phase != "SELECTING":
            return False
        if self._has_remote_round_result_overlay():
            return False
        if private is not None and private.has_selected:
            return True
        return bool(getattr(self, "_remote_selection_sent_pending", False))

    def _should_show_selection_ui(self) -> bool:
        if self._remote_adapter is None:
            return self.phase == GamePhase.SELECTING
        if self._is_local_player_eliminated():
            return False
        public = self._get_public_state()
        return (
            public is not None
            and public.phase == "SELECTING"
            and not self._has_remote_round_result_overlay()
            and not self._is_remote_reveal_in_progress()
        )

    def _start_remote_round_result(self, data: dict) -> None:
        normalised = dict(data)
        normalised["round_danger"] = {
            int(seat_index): int(value)
            for seat_index, value in (data.get("round_danger") or {}).items()
        }
        normalised["total_scores"] = {
            int(seat_index): int(value)
            for seat_index, value in (data.get("total_scores") or {}).items()
        }
        normalised["eliminated_seats"] = [int(seat) for seat in data.get("eliminated_seats", [])]
        self._remote_round_result = normalised
        self._remote_round_result_timer = float(data.get("timeout_seconds", 0))
        self._remote_round_result_acknowledged = False
        self._remote_selection_sent_pending = False
        self.selected_card_index = None
        self.message = ""
        self.message_timer = 0.0

    def _clear_remote_round_result(self) -> None:
        self._remote_round_result = None
        self._remote_round_result_timer = 0.0
        self._remote_round_result_acknowledged = False

    def _confirm_remote_round_result(self) -> None:
        if not self._has_remote_round_result_overlay():
            return
        if self._remote_round_result_acknowledged:
            return
        self._remote_round_result_acknowledged = True
        if self._round_ready_callback is not None:
            self._round_ready_callback()

    def _reset_remote_selecting_phase(self, remaining_time: float = TURN_TIMEOUT_SECONDS) -> None:
        """Reset transient local UI state when the server enters SELECTING."""
        self.turn_timer = remaining_time
        self._last_timeout_tick = -1
        self.selected_card_index = None
        self._remote_selection_sent_pending = False
        self._last_remote_selected_card_number = None
        self._clear_remote_round_result()
        # Reset penalty counters when the round number advances so stale
        # counts from the previous round don't linger on turn 1.
        if self._remote_adapter is not None:
            public = self._remote_adapter.get_public_state()
            if public is not None:
                current_round = public.round_number
                prev_round = getattr(self, "_last_penalty_reset_round", 0)
                if current_round != prev_round:
                    self._remote_adapter.reset_round_penalty_counts()
                    self._last_penalty_reset_round = current_round
                    # Clear soldier figures so cards from the new deck get
                    # fresh drop animations (same numbers reused across rounds).
                    if hasattr(self, "soldier_figures"):
                        self.soldier_figures.clear()

    def _enter_remote_result_scene(self, round_result: dict) -> None:
        """Switch to the shared ResultScene for multiplayer round settlement."""
        public = self._get_public_state()
        if public is None or self._remote_adapter is None:
            return

        from fall_in.core.game_manager import GameManager, GameState
        from fall_in.scenes.result_scene import ResultScene

        gm = GameManager()
        gm.state = GameState.RESULT
        gm.change_scene(
            ResultScene.from_remote(
                round_result=round_result,
                public_state=public,
                remote_adapter=self._remote_adapter,
                resume_scene=self,
                network_tick_callback=self._network_tick_callback,
                round_ready_callback=self._round_ready_callback,
            )
        )

    def _update_remote_match_flow(self, dt: float) -> bool:
        if self._remote_adapter is None:
            return False

        # Handle server-side SELECTION_TIMEOUT events FIRST, before
        # consuming PHASE_SELECTING.  When the server times out, it sends
        # SELECTION_TIMEOUT, resolves the turn, and immediately broadcasts
        # PHASE_SELECTING for the next turn — all in one pump batch.
        # Processing the timeout first lets the subsequent PHASE_SELECTING
        # reset cleanly override the stale state (pending flag, timer=0).
        pop_timeout = getattr(self._remote_adapter, "pop_selection_timeout", None)
        if callable(pop_timeout):
            timed_out_seats = pop_timeout()
            if timed_out_seats is not None:
                my_seat = self._get_my_seat()
                if my_seat in timed_out_seats:
                    self.message = "시간 초과! 자동 선택됨"
                    self.message_timer = 1.0
                    self._remote_selection_sent_pending = True
                self.turn_timer = 0.0

        consume_selecting = getattr(self._remote_adapter, "consume_selecting_phase_started", None)
        if callable(consume_selecting):
            remaining = consume_selecting()
            while remaining is not None:
                self._reset_remote_selecting_phase(remaining)
                remaining = consume_selecting()

        if not self._is_remote_reveal_in_progress():
            pop_round_result = getattr(self._remote_adapter, "pop_round_result", None)
            if callable(pop_round_result):
                round_result = pop_round_result()
                if round_result is not None:
                    self._enter_remote_result_scene(round_result)
                    return True

        pop_match_result = getattr(self._remote_adapter, "pop_match_result", None)
        if callable(pop_match_result):
            match_result = pop_match_result()
            if match_result is not None:
                self._clear_remote_round_result()
                self._go_to_remote_game_over(match_result)
                return True

        # Always consume the selection timer when in SELECTING phase so it
        # stays in sync with the server's 30-second timeout.  Previously the
        # timer was paused during reveal animations, causing drift where the
        # server would auto-select while the client still showed time left.
        # Eliminated players skip the timer entirely — they are spectators.
        public = self._get_public_state()
        in_selecting = (
            public is not None
            and public.phase == "SELECTING"
            and not self._has_remote_round_result_overlay()
            and not self._is_local_player_eliminated()
        )
        if in_selecting:
            self._consume_selection_timer(dt, on_timeout=self._remote_auto_select_card)
        else:
            self._last_timeout_tick = -1

        if self._has_remote_round_result_overlay():
            self._remote_round_result_timer = max(0.0, self._remote_round_result_timer - dt)
        return False

    def _build_remote_game_over_players(self, match_result: dict) -> tuple[Optional[Player], list[Player]]:
        public = self._get_public_state()
        if public is None:
            return None, []

        my_seat = self._get_my_seat()
        final_scores = {
            int(seat_index): int(value)
            for seat_index, value in (match_result.get("final_scores") or {}).items()
        }
        players: list[Player] = []
        for seat in sorted(public.seats, key=lambda s: s.seat_index):
            player = Player(
                name=seat.display_name,
                player_type=PlayerType.HUMAN if seat.seat_index == my_seat else PlayerType.AI,
                player_id=seat.seat_index,
            )
            player.penalty_score = int(
                final_scores.get(seat.seat_index, public.committed_scores.get(seat.seat_index, 0))
            )
            player.is_eliminated = player.penalty_score >= GAME_OVER_SCORE
            players.append(player)

        winner_seat = match_result.get("winner_seat")
        if winner_seat is not None:
            winner_seat = int(winner_seat)
        winner = next((player for player in players if player.player_id == winner_seat), None)
        return winner, players

    def _go_to_remote_game_over(self, match_result: dict) -> None:
        winner, players = self._build_remote_game_over_players(match_result)
        if not players:
            return

        # Extract per-seat reward granted by the server.
        my_seat = self._get_my_seat()
        rewards = match_result.get("rewards") or {}
        my_reward = int(rewards.get(str(my_seat), rewards.get(my_seat, 0)))

        from fall_in.core.game_manager import GameManager, GameState
        from fall_in.scenes.game_over_scene import GameOverScene

        gm = GameManager()
        gm.clear_pending_match_reconnect()
        gm.state = GameState.GAMEOVER
        gm.change_scene(
            GameOverScene(
                winner=winner,
                players=players,
                round_number=self._get_round_number(),
                multiplayer_reward=my_reward,
            )
        )

    def _handle_exit_match(self) -> None:
        """Handle voluntary exit from a multiplayer match."""
        is_eliminated = self._is_local_player_eliminated()

        # Send MATCH_LEAVE to server
        if self._exit_match_callback is not None:
            self._exit_match_callback()

        # Build a minimal player list for GameOverScene
        from fall_in.core.game_manager import GameManager, GameState
        from fall_in.scenes.game_over_scene import GameOverScene

        public = self._get_public_state()
        my_seat = self._get_my_seat()
        players: list[Player] = []

        if public is not None:
            for seat in sorted(public.seats, key=lambda s: s.seat_index):
                player = Player(
                    name=seat.display_name,
                    player_type=PlayerType.HUMAN if seat.seat_index == my_seat else PlayerType.AI,
                    player_id=seat.seat_index,
                )
                player.penalty_score = int(
                    public.committed_scores.get(seat.seat_index, 0)
                )
                players.append(player)
        else:
            # Fallback: create a single human player
            player = Player(name="", player_type=PlayerType.HUMAN, player_id=my_seat)
            players.append(player)

        gm = GameManager()
        gm.clear_pending_match_reconnect()
        gm.state = GameState.GAMEOVER
        gm.change_scene(
            GameOverScene(
                winner=None,
                players=players,
                round_number=self._get_round_number(),
                early_exit=not is_eliminated,
            )
        )

    # ------------------------------------------------------------------
    # UI drawing
    # ------------------------------------------------------------------

    def _draw_ui(self, screen: pygame.Surface) -> None:
        """Draw UI elements: top bar, player sidebar, turn log, messages."""
        title_font = get_font(24, "bold")
        font = get_font(18)
        small_font = get_font(14)
        mini_font = get_font(12)

        # === TOP BAR ===
        if "top_bar" in self._hud_images:
            top_bar_img = pygame.transform.smoothscale(
                self._hud_images["top_bar"], (SCREEN_WIDTH + 4, UI_TOP_BAR_HEIGHT + 2)
            )
            screen.blit(top_bar_img, (-2, -1))
        else:
            top_bar_surface = pygame.Surface(
                (SCREEN_WIDTH, UI_TOP_BAR_HEIGHT), pygame.SRCALPHA
            )
            top_bar_surface.fill(TOP_BAR_BG_COLOR)
            screen.blit(top_bar_surface, (0, 0))
            pygame.draw.line(
                screen,
                AIR_FORCE_BLUE,
                (0, UI_TOP_BAR_HEIGHT),
                (SCREEN_WIDTH, UI_TOP_BAR_HEIGHT),
                2,
            )

        top_y = UI_TOP_BAR_Y

        # Round indicator badge
        if "round_indicator" in self._hud_images:
            badge_w, badge_h = 160, 50
            badge_img = pygame.transform.smoothscale(
                self._hud_images["round_indicator"], (badge_w, badge_h)
            )
            badge_x = 10
            badge_y = (UI_TOP_BAR_HEIGHT - badge_h) // 2
            screen.blit(badge_img, (badge_x, badge_y))
            # Draw round number centered on the badge
            round_num_font = get_font(20, "bold")
            round_text = round_num_font.render(
                f"ROUND {self._get_round_number()}", True, WHITE
            )
            round_rect = round_text.get_rect(
                center=(badge_x + badge_w // 2, badge_y + badge_h // 2)
            )
            screen.blit(round_text, round_rect)
        else:
            draw_outlined_text(
                screen,
                f"ROUND {self._get_round_number()}",
                title_font,
                (20, top_y),
                WHITE,
                TOP_BAR_OUTLINE_COLOR,
            )

        # Hangar icon + penalty cards count
        hangar_x = ICON_HANGER_X
        if "hangar_icon" in self._hud_images:
            hangar_img = pygame.transform.smoothscale(
                self._hud_images["hangar_icon"], (60, 24)
            )
            screen.blit(hangar_img, (hangar_x, top_y))
        else:
            hangar_points = [
                (hangar_x, top_y + 25),
                (hangar_x + 15, top_y + 5),
                (hangar_x + 45, top_y + 5),
                (hangar_x + 60, top_y + 25),
            ]
            pygame.draw.polygon(screen, LIGHT_BLUE, hangar_points)
            pygame.draw.polygon(screen, WHITE, hangar_points, width=2)

        cards_taken = self._get_local_round_penalty_card_count()
        badge_center = (hangar_x + 48, top_y + 18)
        pygame.draw.circle(screen, AIR_FORCE_BLUE, badge_center, 12)
        pygame.draw.circle(screen, WHITE, badge_center, 12, 2)
        count_text = mini_font.render(str(cards_taken), True, WHITE)
        screen.blit(count_text, count_text.get_rect(center=badge_center))

        # Danger color legend below UI bar
        legend_y = UI_TOP_BAR_HEIGHT + 3
        legend_items = [
            ((100, 150, 100), "1"),
            ((200, 180, 50), "2"),
            ((230, 150, 50), "3"),
            ((200, 50, 50), "5"),
            ((100, 50, 150), "7"),
        ]
        legend_font = mini_font
        draw_outlined_text(
            screen,
            "위험도 포인트 : ",
            legend_font,
            (hangar_x - 5, legend_y + 1),
            WHITE,
            TOP_BAR_OUTLINE_COLOR,
        )
        label_w = legend_font.size("위험도 포인트 : ")[0]
        lx = hangar_x - 5 + label_w
        for color, pts in legend_items:
            pygame.draw.circle(screen, color, (lx + 6, legend_y + 6), 6)
            draw_outlined_text(
                screen,
                pts,
                legend_font,
                (lx + 6 - legend_font.size(pts)[0] // 2, legend_y + 1),
                WHITE,
                TOP_BAR_OUTLINE_COLOR,
            )
            lx += 15

        # Player order display
        order_y = top_y + 59
        draw_outlined_text(
            screen, "순서:", mini_font, (20, order_y), WHITE, TOP_BAR_OUTLINE_COLOR
        )

        order_x = UI_ELEMENT_PLAYER_ORDER_X
        order_entries = self._get_player_order_entries()
        for i, (name, is_local_player) in enumerate(order_entries):
            label = name
            color = DANGER_SAFE if is_local_player else LIGHT_BLUE

            is_current = False
            if self._remote_adapter is None:
                player = self.rules.player_order[i]
                is_current = (
                    self.current_placement
                    and self.current_placement.player == player
                    and self.phase
                    in [GamePhase.PLACING_PLAYER, GamePhase.PENALTY_ANIMATION]
                )
            elif self._remote_current_reveal_seat is not None:
                public = self._get_public_state()
                if public is not None and i < len(public.player_order_seats):
                    is_current = public.player_order_seats[i] == self._remote_current_reveal_seat

            if is_current:
                pygame.draw.rect(
                    screen,
                    DANGER_WARNING,
                    (order_x - 4, order_y - 2, 24, 16),
                    border_radius=3,
                )

            draw_outlined_text(
                screen,
                label,
                mini_font,
                (order_x, order_y),
                WHITE if is_current else color,
                TOP_BAR_OUTLINE_COLOR,
            )

            if i < len(order_entries) - 1:
                draw_outlined_text(
                    screen,
                    "→",
                    mini_font,
                    (order_x + 18, order_y),
                    LIGHT_BLUE,
                    TOP_BAR_OUTLINE_COLOR,
                )
            order_x += 38

        # Danger gauge (center-right)
        committed = self._get_local_committed_score()
        gauge_x = SCREEN_WIDTH // 2 + 50

        # Danger warning icon
        if "danger_warning" in self._hud_images:
            warn_img = pygame.transform.smoothscale(
                self._hud_images["danger_warning"], (26, 22)
            )
            screen.blit(warn_img, (gauge_x - 13, top_y + 4))
        else:
            pygame.draw.polygon(
                screen,
                DANGER_DANGER,
                [
                    (gauge_x, top_y + 5),
                    (gauge_x - 12, top_y + 25),
                    (gauge_x + 12, top_y + 25),
                ],
            )
            screen.blit(small_font.render("!", True, WHITE), (gauge_x - 3, top_y + 8))

        draw_outlined_text(
            screen,
            f"{committed}/{GAME_OVER_SCORE}",
            font,
            (gauge_x + 20, top_y + 5),
            WHITE,
            TOP_BAR_OUTLINE_COLOR,
        )

        bar_x = gauge_x + 80
        bar_w = UI_ELEMENT_DANGER_GAUGE_WIDTH
        bar_h = UI_ELEMENT_DANGER_GAUGE_HEIGHT
        fill_ratio = min(committed / GAME_OVER_SCORE, 1.0)

        # Gauge background image
        if "gauge_bg" in self._hud_images:
            gauge_bg_img = pygame.transform.smoothscale(
                self._hud_images["gauge_bg"], (bar_w, bar_h)
            )
            screen.blit(gauge_bg_img, (bar_x, top_y + 8))

            # Draw fill on top of bg, inset to stay within frame
            if fill_ratio > 0:
                fill_key = self._get_gauge_fill_key(committed)
                if fill_key in self._hud_images:
                    pad_x, pad_y = 3, 4
                    inner_w = bar_w - pad_x * 2
                    inner_h = bar_h - pad_y * 2
                    fill_w = max(1, int(inner_w * fill_ratio))
                    full_fill = pygame.transform.smoothscale(
                        self._hud_images[fill_key], (inner_w, inner_h)
                    )
                    clipped = full_fill.subsurface((0, 0, fill_w, inner_h))
                    screen.blit(clipped, (bar_x + pad_x, top_y + 8 + pad_y))
        else:
            pygame.draw.rect(
                screen,
                (200, 200, 200),
                (bar_x, top_y + 8, bar_w, bar_h),
                border_radius=3,
            )

            # Gauge fill overlay (fallback)
            if fill_ratio > 0:
                pygame.draw.rect(
                    screen,
                    get_danger_color(committed),
                    (bar_x, top_y + 8, int(bar_w * fill_ratio), bar_h),
                    border_radius=3,
                )

            pygame.draw.rect(
                screen,
                AIR_FORCE_BLUE,
                (bar_x, top_y + 8, bar_w, bar_h),
                width=1,
                border_radius=3,
            )

        # Player icon (far right)
        self._draw_player_icon_ui(screen, top_y)

        # === OTHER PLAYERS (Right sidebar, center-right aligned) ===
        # Single-player: iterate Player objects directly (original approach).
        # Multiplayer: use server-state dicts from _get_other_player_panels().
        if self._remote_adapter is None:
            other_players = self.players[1:]
        else:
            other_players = []

        mp_panel_data = self._get_other_player_panels() if self._remote_adapter is not None else []

        panel_count = len(other_players) if self._remote_adapter is None else len(mp_panel_data)
        panel_w, panel_h = 200, 70
        panel_spacing = 10
        total_panels_height = (
            panel_count * panel_h + max(0, panel_count - 1) * panel_spacing
        )
        panel_area_top = UI_TOP_BAR_HEIGHT + 10
        panel_area_bottom = SCREEN_HEIGHT - 220
        panel_start_y = (
            panel_area_top
            + (panel_area_bottom - panel_area_top - total_panels_height) // 2
        )
        panel_x = SCREEN_WIDTH - panel_w - 10

        _panel_iter = other_players if self._remote_adapter is None else mp_panel_data
        for i, panel_item in enumerate(_panel_iter):
            p_rect = pygame.Rect(
                panel_x, panel_start_y + i * (panel_h + panel_spacing), panel_w, panel_h
            )

            # Panel background
            if self._remote_adapter is None:
                player = panel_item
                is_elim = player.is_eliminated
            else:
                pdata = panel_item
                is_elim = pdata.get("is_eliminated", False)
            if "player_panel" in self._hud_images:
                panel_img = pygame.transform.smoothscale(
                    self._hud_images["player_panel"], (p_rect.width, p_rect.height)
                )
                if is_elim:
                    tint = pygame.Surface(panel_img.get_size(), pygame.SRCALPHA)
                    tint.fill((180, 40, 40, 100))
                    panel_img = panel_img.copy()
                    panel_img.blit(tint, (0, 0))
                screen.blit(panel_img, p_rect.topleft)
            else:
                bg_color = DANGER_DANGER if is_elim else LIGHT_BLUE
                pygame.draw.rect(screen, bg_color, p_rect, border_radius=6)
                pygame.draw.rect(
                    screen, AIR_FORCE_BLUE, p_rect, width=2, border_radius=6
                )

            # Profile picture (circular, left side of panel)
            avatar_radius = 25
            avatar_cx = p_rect.x + 8 + avatar_radius
            avatar_cy = p_rect.y + p_rect.height // 2

            # Black background circle
            pygame.draw.circle(screen, (0, 0, 0), (avatar_cx, avatar_cy), avatar_radius)

            # Portrait photo
            from fall_in.utils.asset_manifest import AssetManifest

            icons = AssetManifest.get_loaded("icons")
            if "player_portrait_unknown" in icons:
                avatar_size = avatar_radius * 2
                portrait_img = pygame.transform.smoothscale(
                    icons["player_portrait_unknown"], (avatar_size, avatar_size)
                )
                mask = pygame.Surface((avatar_size, avatar_size), pygame.SRCALPHA)
                pygame.draw.circle(
                    mask,
                    (255, 255, 255, 255),
                    (avatar_radius, avatar_radius),
                    avatar_radius,
                )
                portrait_img.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MIN)
                screen.blit(
                    portrait_img, (avatar_cx - avatar_radius, avatar_cy - avatar_radius)
                )
            else:
                avatar_icon = mini_font.render("👤", True, WHITE)
                screen.blit(
                    avatar_icon, avatar_icon.get_rect(center=(avatar_cx, avatar_cy))
                )

            # Border frame (player_avatar)
            if "player_avatar" in self._hud_images:
                frame_size = avatar_radius * 2 + 6
                frame_img = pygame.transform.smoothscale(
                    self._hud_images["player_avatar"], (frame_size, frame_size)
                )
                screen.blit(
                    frame_img,
                    (avatar_cx - frame_size // 2, avatar_cy - frame_size // 2),
                )
            else:
                pygame.draw.circle(
                    screen, WHITE, (avatar_cx, avatar_cy), avatar_radius, 2
                )

            # Text info (right of avatar)
            text_x = avatar_cx + avatar_radius + 6
            if self._remote_adapter is None:
                order_pos = self.rules.get_player_order_position(player)
                p_name = player.name
                p_committed = self.rules.get_player_committed_score(player)
                p_cards = self.rules.get_player_round_penalty_count(player)
                p_status = ""
            else:
                order_pos = pdata.get("order_pos", 0)
                p_name = pdata.get("name", "?")
                p_committed = pdata.get("committed", 0)
                p_cards = pdata.get("penalty", 0)
                p_status = pdata.get("status", "")
            screen.blit(
                small_font.render(f"{order_pos}.{p_name}", True, WHITE),
                (text_x, p_rect.y + 8),
            )

            screen.blit(
                mini_font.render(f"위험: {p_committed}", True, WHITE),
                (text_x, p_rect.y + 28),
            )

            meta_text = f"벌칙: {p_cards}장"
            meta_color = WHITE
            if p_status:
                meta_text = f"{meta_text}  ·  {p_status}"
                meta_color = DANGER_WARNING if p_status == "재접속 중" else LIGHT_BLUE
            screen.blit(
                mini_font.render(meta_text, True, meta_color),
                (text_x, p_rect.y + 45),
            )

        # Turn log
        if self.turn_log:
            log_x = TURN_LOG_X
            log_y = TURN_LOG_Y
            log_width = TURN_LOG_WIDTH
            log_height = 32 + min(len(self.turn_log), 4) * 18

            if "turn_log" in self._hud_images:
                log_bg = pygame.transform.smoothscale(
                    self._hud_images["turn_log"], (log_width, log_height)
                )
                screen.blit(log_bg, (log_x, log_y))
            else:
                log_container = pygame.Surface((log_width, log_height), pygame.SRCALPHA)
                log_container.fill((30, 60, 90, 180))
                screen.blit(log_container, (log_x, log_y))
                pygame.draw.rect(
                    screen,
                    AIR_FORCE_BLUE,
                    (log_x, log_y, log_width, log_height),
                    width=2,
                    border_radius=4,
                )

            draw_outlined_text(
                screen,
                "이번 턴:",
                small_font,
                (log_x + 8, log_y + 4),
                WHITE,
                AIR_FORCE_BLUE,
            )

            for i, result in enumerate(self.turn_log[-4:]):
                entry_text = f"{result.placement_order}. {result.player.name[:4]} → #{result.card.number}"
                draw_outlined_text(
                    screen,
                    entry_text,
                    mini_font,
                    (log_x + 10, log_y + 22 + i * 18),
                    WHITE,
                    (20, 40, 60),
                )

        # Game message
        if self.message and self.message_timer > 0:
            msg_surface = font.render(self.message, True, AIR_FORCE_BLUE)
            msg_rect = msg_surface.get_rect(
                center=(SCREEN_WIDTH // 2, SCREEN_HEIGHT // 2 - 50)
            )
            bg_rect = msg_rect.inflate(20, 10)
            if "popup_message" in self._hud_images:
                popup_bg = pygame.transform.smoothscale(
                    self._hud_images["popup_message"],
                    (bg_rect.width, bg_rect.height),
                )
                screen.blit(popup_bg, bg_rect.topleft)
            else:
                pygame.draw.rect(screen, WHITE, bg_rect, border_radius=5)
                pygame.draw.rect(
                    screen, AIR_FORCE_BLUE, bg_rect, width=1, border_radius=5
                )
            screen.blit(msg_surface, msg_rect)

        # Emote display — floating emoji badges above player panels (PR-07)
        self._draw_emote_display(screen, panel_x, panel_start_y, panel_h, panel_spacing)

        # Phase indicator
        phase_text = small_font.render(
            f"[{self._get_phase_text()}]", True, AIR_FORCE_BLUE
        )
        screen.blit(phase_text, (SCREEN_WIDTH - 120, SCREEN_HEIGHT - 20))

    def _get_gauge_fill_key(self, committed: int) -> str:
        """Map committed score to the correct gauge fill image key."""
        from fall_in.config import GAME_OVER_SCORE

        ratio = committed / GAME_OVER_SCORE
        if ratio >= 0.75:
            return "gauge_critical"
        elif ratio >= 0.5:
            return "gauge_danger"
        elif ratio >= 0.25:
            return "gauge_warning"
        return "gauge_safe"

    def _draw_player_icon_ui(self, screen: pygame.Surface, top_y: int) -> None:
        """Draw player icon and currency in top bar (far right)."""
        icon_x = SCREEN_WIDTH - 170
        icon_y = top_y + 20
        icon_radius = 28

        # Black background circle (prevents UI bleed-through)
        pygame.draw.circle(screen, (0, 0, 0), (icon_x, icon_y), icon_radius)

        # Portrait photo (player_portrait_unknown)
        from fall_in.utils.asset_manifest import AssetManifest

        icons = AssetManifest.get_loaded("icons")
        if "player_portrait_unknown" in icons:
            avatar_size = icon_radius * 2
            portrait_img = pygame.transform.smoothscale(
                icons["player_portrait_unknown"], (avatar_size, avatar_size)
            )
            # Circular mask
            mask = pygame.Surface((avatar_size, avatar_size), pygame.SRCALPHA)
            pygame.draw.circle(
                mask, (255, 255, 255, 255), (icon_radius, icon_radius), icon_radius
            )
            portrait_img.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MIN)
            screen.blit(portrait_img, (icon_x - icon_radius, icon_y - icon_radius))
        else:
            icon_font = get_font(18)
            icon_text = icon_font.render("👤", True, WHITE)
            screen.blit(icon_text, icon_text.get_rect(center=(icon_x, icon_y)))

        # Border frame (player_avatar)
        if "player_avatar" in self._hud_images:
            frame_size = icon_radius * 2 + 6
            frame_img = pygame.transform.smoothscale(
                self._hud_images["player_avatar"], (frame_size, frame_size)
            )
            screen.blit(
                frame_img,
                (icon_x - frame_size // 2, icon_y - frame_size // 2),
            )
        else:
            pygame.draw.circle(screen, AIR_FORCE_BLUE, (icon_x, icon_y), icon_radius, 2)

    def _get_phase_text(self) -> str:
        """Get current phase description in Korean."""
        if self._has_remote_round_result_overlay():
            return "라운드 정산"

        public = self._get_public_state()
        if public is not None:
            has_pending_reveal = False
            if self._remote_adapter is not None:
                has_pending = getattr(self._remote_adapter, "has_pending_reveal_steps", None)
                if callable(has_pending):
                    has_pending_reveal = has_pending()
            if self._remote_current_reveal_seat is not None or has_pending_reveal:
                return "카드 배치"
            remote_phase_texts = {
                "SELECTING": "카드 선택",
                "PLACING": "카드 배치",
                "ROUND_END": "라운드 종료",
                "GAME_OVER": "게임 종료",
            }
            return remote_phase_texts.get(public.phase.upper(), public.phase)

        phase_texts = {
            GamePhase.STARTING: "라운드 시작",
            GamePhase.SELECTING: "카드 선택",
            GamePhase.AI_THINKING: "AI 선택 중",
            GamePhase.REVEALING: "카드 공개",
            GamePhase.PLACING_PLAYER: "카드 배치",
            GamePhase.PENALTY_ANIMATION: "벌점 처리",
            GamePhase.ROW_SELECT: "열 선택",
            GamePhase.ROUND_END: "라운드 종료",
            GamePhase.GAME_OVER: "게임 종료",
        }
        return phase_texts.get(self.phase, "")

    # ------------------------------------------------------------------
    # Emote display
    # ------------------------------------------------------------------

    def _get_my_seat(self) -> int:
        """Return the local player's seat index (0 in single-player, adapter.my_seat in multiplayer)."""
        if self._remote_adapter is not None:
            return self._remote_adapter.my_seat
        return 0

    def _get_other_seat_order(self) -> list[int]:
        """
        Return seat indices of all non-local seats, in the order they appear as
        sidebar panels (ascending seat_index, skipping my seat).

        Single-player: seats 1, 2, 3.
        Multiplayer: sorted server seat indices excluding my_seat.
        """
        my_seat = self._get_my_seat()
        if self._remote_adapter is not None:
            public = self._remote_adapter.get_public_state()
            if public:
                return sorted(
                    s.seat_index for s in public.seats if s.seat_index != my_seat
                )
        return [i for i in range(1, len(self.players))]

    def _get_other_player_panels(self) -> list[dict]:
        """
        Build panel data list for the right sidebar.

        In single-player mode: uses local GameRules data.
        In multiplayer mode: uses RemoteGameAdapter public state so that the
        server-authoritative names and scores are shown.
        """
        if self._remote_adapter is None:
            # Single-player — local rules
            panels: list[dict] = []
            for i, p in enumerate(self.players[1:]):
                try:
                    panels.append(
                        {
                            "name": p.name,
                            "committed": self.rules.get_player_committed_score(p),
                            "penalty": self.rules.get_player_round_penalty_count(p),
                            "order_pos": self.rules.get_player_order_position(p),
                            "seat_index": i + 1,
                            "is_eliminated": p.is_eliminated,
                        }
                    )
                except Exception as exc:  # noqa: BLE001
                    import sys
                    print(f"[PANEL] failed for player {p.name!r} (id={p.player_id}): {exc}", file=sys.stderr)
                    panels.append(
                        {
                            "name": p.name,
                            "committed": 0,
                            "penalty": 0,
                            "order_pos": 0,
                            "seat_index": i + 1,
                            "is_eliminated": getattr(p, "is_eliminated", False),
                        }
                    )
            return panels

        # Multiplayer — server state
        public = self._remote_adapter.get_public_state()
        my_seat = self._remote_adapter.my_seat
        if public is None:
            return []

        order = public.player_order_seats
        scores = public.committed_scores
        panels = []
        for seat in sorted(public.seats, key=lambda s: s.seat_index):
            if seat.seat_index == my_seat:
                continue
            order_pos = (order.index(seat.seat_index) + 1) if seat.seat_index in order else 0
            committed = scores.get(seat.seat_index, 0)
            # Eliminated: score >= 66 or removed from player order
            is_elim = committed >= GAME_OVER_SCORE or (
                seat.seat_index not in order and committed > 0
            )
            status = ""
            if self._remote_adapter.is_seat_bot_takeover(seat.seat_index):
                status = "BOT 대체"
            elif self._remote_adapter.is_seat_disconnected(seat.seat_index):
                status = "재접속 중"
            panels.append(
                {
                    "name": seat.display_name,
                    "committed": committed,
                    "penalty": self._remote_adapter.get_round_penalty_card_count(seat.seat_index),
                    "order_pos": order_pos,
                    "seat_index": seat.seat_index,
                    "is_eliminated": is_elim,
                    "status": status,
                }
            )
        return panels

    def _draw_emote_display(
        self,
        screen: pygame.Surface,
        panel_x: int,
        panel_start_y: int,
        panel_h: int,
        panel_spacing: int,
    ) -> None:
        """
        Render floating emote badges near each player's UI element.

        My seat  → below my player icon in the top bar (right side).
        Other seats → to the LEFT of their sidebar panel so the badge
                      doesn't obscure the panel content.

        Seat mapping is relative to the local player's my_seat so that
        multiplayer clients (seat != 0) are handled correctly.
        """
        if not self._emote_display:
            return

        emote_font = get_font(26)
        my_seat = self._get_my_seat()
        other_seats = self._get_other_seat_order()

        for seat_index, (emoji, ttl) in self._emote_display.items():
            alpha = 255
            if ttl < 0.5:
                alpha = int(255 * (ttl / 0.5))

            if seat_index == my_seat:
                # My emote: below the player icon in the top bar
                cx, cy = self._player_icon_center
                badge_cx = cx
                badge_cy = cy + self._player_icon_radius + 20
            elif seat_index in other_seats:
                panel_index = other_seats.index(seat_index)
                panel_top = panel_start_y + panel_index * (panel_h + panel_spacing)
                panel_center_y = panel_top + panel_h // 2
                # Badge to the LEFT of the panel, vertically centred
                badge_cx = panel_x - 28
                badge_cy = panel_center_y
            else:
                continue  # unknown seat — skip

            emoji_surf = emote_font.render(emoji, True, WHITE)
            emoji_surf.set_alpha(alpha)
            emoji_rect = emoji_surf.get_rect(center=(badge_cx, badge_cy))

            bg = pygame.Surface(
                (emoji_rect.width + 10, emoji_rect.height + 6), pygame.SRCALPHA
            )
            pygame.draw.rect(
                bg,
                (0, 0, 0, min(alpha, 140)),
                (0, 0, bg.get_width(), bg.get_height()),
                border_radius=8,
            )
            screen.blit(bg, (emoji_rect.x - 5, emoji_rect.y - 3))
            screen.blit(emoji_surf, emoji_rect)

    # ------------------------------------------------------------------
    # Hand drawing
    # ------------------------------------------------------------------

    def _draw_hand(self, screen: pygame.Surface) -> None:
        """Draw player's hand cards in a fan layout at the bottom."""
        hand = self._get_display_hand_cards()
        if not hand:
            return

        arrived_cards = set()
        if self.phase in (GamePhase.DEALING, GamePhase.ORDER_ANNOUNCE):
            for card, tween in self.dealing_cards:
                if tween.is_complete:
                    arrived_cards.add(card)

        card_width = BattalionCard.CARD_WIDTH
        card_height = BattalionCard.CARD_HEIGHT
        num_cards = len(hand)

        total_width = card_width + (num_cards - 1) * (card_width - HAND_CARD_OVERLAP)
        start_x = SCREEN_WIDTH // 2 - total_width // 2
        base_y = SCREEN_HEIGHT - card_height + HAND_Y_OFFSET

        # Determine hovered card (check from right to left)
        mouse_pos = pygame.mouse.get_pos()
        hovered_index = None
        for i in range(num_cards - 1, -1, -1):
            x = start_x + i * (card_width - HAND_CARD_OVERLAP)
            card_rect = pygame.Rect(
                x,
                base_y - HAND_HOVER_POP_DISTANCE,
                card_width,
                card_height + HAND_HOVER_POP_DISTANCE,
            )
            if card_rect.collidepoint(mouse_pos):
                hovered_index = i
                break

        # Draw cards (hovered card last for z-order)
        draw_order = list(range(num_cards))
        if hovered_index is not None:
            draw_order.remove(hovered_index)
            draw_order.append(hovered_index)

        for i in draw_order:
            card = hand[i]

            if (
                self.phase in (GamePhase.DEALING, GamePhase.ORDER_ANNOUNCE)
                and card not in arrived_cards
            ):
                continue
            if self.dragging and i == self.selected_card_index:
                continue

            x = start_x + i * (card_width - HAND_CARD_OVERLAP)

            center_index = (num_cards - 1) / 2
            offset_from_center = i - center_index
            rotation = (
                (offset_from_center / max(1, num_cards - 1)) * HAND_FAN_SPREAD
                if num_cards > 1
                else 0
            )

            is_hovered = i == hovered_index
            is_selected = i == self.selected_card_index

            if is_hovered or is_selected:
                draw_y = base_y - HAND_HOVER_POP_DISTANCE
                scale = HAND_HOVER_SCALE
                rotation = 0
            else:
                draw_y = base_y
                scale = 1.0

            BattalionCard.render(
                screen,
                card,
                x,
                draw_y,
                is_interviewed=getattr(card, "is_collected", False),
                is_selected=is_selected,
                is_hovered=is_hovered,
                rotation=rotation,
                scale=scale,
            )

    # ------------------------------------------------------------------
    # Event handling
    # ------------------------------------------------------------------

    def handle_event(self, event: pygame.event.Event) -> None:
        """Handle pygame events."""
        if self._has_remote_round_result_overlay():
            if event.type == pygame.KEYDOWN and event.key in (pygame.K_SPACE, pygame.K_RETURN):
                self._confirm_remote_round_result()
                return
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if self._get_round_ready_button_rect().collidepoint(event.pos):
                    self._confirm_remote_round_result()
            return

        # Settings popup consumes events when visible
        if self._settings_popup.handle_event(event):
            return

        # Emote popup: forward non-click events (motion, keyboard) so that
        # hover tracking and Escape-to-close work, but never block gameplay.
        # Click events are handled inline in the MOUSEBUTTONDOWN block below
        # so we can prevent the icon from immediately re-opening the palette
        # when an outside click dismisses it.
        if event.type != pygame.MOUSEBUTTONDOWN:
            if self._emote_popup.handle_event(event):
                return

        # Debug overlay handling (via mixin)
        if self.handle_debug_event(event):
            return

        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                self._settings_popup.toggle()
                return
            elif event.key == pygame.K_SPACE:
                if self._can_interact_with_cards() and self.selected_card_index is not None:
                    self._confirm_card_selection()

        if event.type == pygame.MOUSEBUTTONDOWN:
            mx, my = event.pos

            # Emote popup gets first crack at clicks when it is open.
            # If the click is outside the palette, the popup closes and returns
            # False — we must NOT then check the player icon, or the palette
            # would immediately re-open.
            _popup_was_open = self._emote_popup.visible
            if _popup_was_open:
                if self._emote_popup.handle_event(event):
                    return  # click consumed by palette button / frame
                # Outside click: palette just closed — skip icon re-check but
                # fall through so the click still reaches card selection.

            # Settings gear button click
            sx, sy = self._settings_btn_center
            if ((mx - sx) ** 2 + (my - sy) ** 2) ** 0.5 <= self._settings_btn_radius:
                self._settings_popup.toggle()
                return

            # Player icon click → open emote palette (only when it was closed)
            if not _popup_was_open:
                ix, iy = self._player_icon_center
                if ((mx - ix) ** 2 + (my - iy) ** 2) ** 0.5 <= self._player_icon_radius:
                    self._emote_popup.show(self._player_icon_center)
                    return

        if self._can_interact_with_cards():
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                self._handle_card_click(event.pos)
            elif event.type == pygame.MOUSEMOTION and self.dragging:
                self.drag_pos = event.pos
            elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
                if self.dragging:
                    self.dragging = False

    def _handle_card_click(self, pos: tuple[int, int]) -> None:
        """Handle clicking on a card in hand (fan layout)."""
        if not self._can_interact_with_cards():
            return

        hand = self._get_display_hand_cards()
        if not hand:
            return

        card_width = BattalionCard.CARD_WIDTH
        card_height = BattalionCard.CARD_HEIGHT
        num_cards = len(hand)

        total_width = card_width + (num_cards - 1) * (card_width - HAND_CARD_OVERLAP)
        start_x = SCREEN_WIDTH // 2 - total_width // 2
        base_y = SCREEN_HEIGHT - card_height + HAND_Y_OFFSET

        for i in range(num_cards - 1, -1, -1):
            x = start_x + i * (card_width - HAND_CARD_OVERLAP)
            card_rect = pygame.Rect(
                x,
                base_y - HAND_HOVER_POP_DISTANCE,
                card_width,
                card_height + HAND_HOVER_POP_DISTANCE,
            )

            if card_rect.collidepoint(pos):
                if self.selected_card_index == i:
                    self._confirm_card_selection()
                else:
                    self.selected_card_index = i
                break

    # ------------------------------------------------------------------
    # Card selection / AI / placement
    # ------------------------------------------------------------------

    def _confirm_card_selection(self) -> None:
        """Confirm card selection and proceed to AI phase."""
        if self.selected_card_index is None:
            return
        if self._remote_adapter is not None and not self._can_interact_with_cards():
            return

        hand = self._get_display_hand_cards()
        if not 0 <= self.selected_card_index < len(hand):
            self.selected_card_index = None
            return

        card = hand[self.selected_card_index]

        if self._remote_adapter is not None:
            self.selected_card_index = None
            if self._card_select_callback is not None:
                self._remote_selection_sent_pending = True
                self._last_remote_selected_card_number = card.number
                self._card_select_callback(card.number)
                self.message = "선택 완료"
                self.message_timer = 0.6
            return

        self.human_player.select_card(card)
        self.selected_card_index = None

        self.phase = GamePhase.AI_THINKING
        self.phase_timer = AI_THINKING_DURATION
        self.message = "AI가 카드를 선택 중..."
        self.message_timer = AI_THINKING_DURATION

    def _ai_select_cards(self) -> None:
        """Have all AI players select cards."""
        for ai in self.ai_controllers:
            if not ai.player.is_eliminated:
                ai.select_card(self.rules.board)

        play_order = self.rules.prepare_turn()
        self.placement_queue = [
            (player, card, idx + 1) for idx, (player, card) in enumerate(play_order)
        ]
        self.turn_log.clear()
        self._start_next_placement()

    def _start_next_placement(self) -> None:
        """Execute and animate the next player's card placement."""
        if not self.placement_queue:
            self.rules.check_round_end()
            self._finish_turn()
            return

        player, card, order_idx = self.placement_queue.pop(0)
        result = self.rules.execute_single_placement(player, card, order_idx)
        self.turn_log.append(result)
        self.current_placement = result

        self.message = f"{result.player.name}: #{result.card.number}"
        self.message_timer = 1.0

        if result.result.penalty_score > 0:
            self.phase = GamePhase.PENALTY_ANIMATION
            self._start_penalty_animation(result)
        else:
            self.phase = GamePhase.PLACING_PLAYER
            self.phase_timer = PLACEMENT_PAUSE_DURATION

    def _start_penalty_animation(self, result: TurnResult) -> None:
        """Start animation of penalty cards moving to hangar or player."""
        self.penalty_cards_animating.clear()
        self.penalty_tweens = TweenGroup()

        taken_cards = result.result.penalty_cards

        if result.player == self.human_player:
            target_x, target_y = 180, 40
        else:
            player_idx = self.players.index(result.player) - 1
            # Match the OTHER PLAYERS panel layout
            panel_w, panel_h = 200, 70
            panel_spacing = 10
            other_count = len(self.players) - 1
            total_h = other_count * panel_h + (other_count - 1) * panel_spacing
            panel_area_top = UI_TOP_BAR_HEIGHT + 10
            panel_area_bottom = SCREEN_HEIGHT - 220
            panel_start_y = (
                panel_area_top + (panel_area_bottom - panel_area_top - total_h) // 2
            )
            panel_x = SCREEN_WIDTH - panel_w - 10
            target_x = panel_x + panel_w // 2
            target_y = (
                panel_start_y + player_idx * (panel_h + panel_spacing) + panel_h // 2
            )

        for i, card in enumerate(taken_cards):
            tween = Tween(
                start=(BOARD_OFFSET_X, BOARD_OFFSET_Y + 50),
                end=(target_x, target_y),
                duration=0.4 + i * 0.1,
                easing="ease_in",
            )
            self.penalty_cards_animating.append((card, tween))
            self.penalty_tweens.add(tween)

        if taken_cards and result.player == self.human_player:
            self.commander.say_penalty_taken()

    def _finish_turn(self) -> None:
        """Finish the turn after all placements are animated."""
        has_penalties = any(r.result.penalty_score > 0 for r in self.turn_log)
        self.message = "배치 및 벌점 부여 완료!" if has_penalties else "카드 배치 완료!"
        self.message_timer = 1.0

        if self.rules.is_round_over():
            self.phase = GamePhase.ROUND_END
            self.phase_timer = 1.0
            self.message = "라운드 종료! 잠시 후 정산..."
        else:
            self.selected_card_index = None
            self.turn_timer = TURN_TIMEOUT_SECONDS
            self.phase = GamePhase.SELECTING

    def _auto_select_card(self) -> None:
        """Auto-select a random card when timer runs out."""
        hand = self.human_player.hand
        if hand:
            card = random.choice(hand)
            self.human_player.select_card(card)
            self.message = "시간 초과! 자동 선택됨"
            self.message_timer = 1.0
            self.phase = GamePhase.AI_THINKING
            self.phase_timer = 0.3

    def _remote_auto_select_card(self) -> None:
        """Auto-select a random card in multiplayer when client timer expires."""
        if self._is_waiting_for_other_players():
            return
        if self._is_local_player_eliminated():
            return
        hand = self._get_display_hand_cards()
        if hand and self._card_select_callback is not None:
            card = random.choice(hand)
            self._remote_selection_sent_pending = True
            self._last_remote_selected_card_number = card.number
            self._card_select_callback(card.number)
            self.message = "시간 초과! 자동 선택됨"
            self.message_timer = 1.0

    def _go_to_result_scene(self) -> None:
        """Navigate to ResultScene for round settlement."""
        from fall_in.core.game_manager import GameManager
        from fall_in.scenes.result_scene import ResultScene

        GameManager().change_scene(ResultScene(self.rules, self.players))

    # ------------------------------------------------------------------
    # Update / Render
    # ------------------------------------------------------------------

    def set_emote_send_callback(self, callback: Callable[[str], None]) -> None:
        """
        Register the function that transmits an emote to the server.

        Called by the networking layer before the scene starts rendering.
        In single-player this is never called; the palette opens but does
        nothing when the player clicks an emote button.

        Example (multiplayer setup)::

            scene.set_emote_send_callback(ws_client.send_emote)

        .. note::
            TODO (PR-09 WS client bootstrap): call this during the multiplayer
            scene setup after the WS connection is established, before the
            first ``update()`` tick.
        """
        self._emote_send_callback = callback

    def set_card_select_callback(self, callback: Callable[[int], None]) -> None:
        """
        Register the function that submits the chosen card number to the server.

        Multiplayer uses this instead of mutating local GameRules state.
        """
        self._card_select_callback = callback

    def set_round_ready_callback(self, callback: Callable[[], None]) -> None:
        """Register the function that acknowledges the round-settlement screen."""
        self._round_ready_callback = callback

    def set_remote_adapter(self, adapter: object) -> None:
        """
        Attach a RemoteGameAdapter so that incoming EMOTE_BROADCAST messages
        are consumed each frame and displayed via show_emote().

        The adapter must expose ``pop_pending_emotes() -> list[(seat, emote_id)]``.
        Call this once after the match starts and before the first update().

        .. note::
            TODO (PR-09 WS client bootstrap): call this during the multiplayer
            scene setup, passing the ``RemoteGameAdapter`` instance that
            receives ``EMOTE_BROADCAST`` messages from the server.
        """
        self._remote_adapter = adapter
        # Disable the local-only opening round flow once the scene becomes
        # server-authoritative. The actual match state now comes from the adapter.
        self.phase = GamePhase.SELECTING
        self.turn_timer = TURN_TIMEOUT_SECONDS
        self.phase_timer = 0.0
        self.message = ""
        self.message_timer = 0.0
        self._remote_selection_sent_pending = False
        self._clear_remote_round_result()
        self.dealing_cards.clear()
        self.placement_queue.clear()
        self.penalty_cards_animating.clear()
        self.current_placement = None
        self._remote_reveal_step_timer = 0.0
        self._remote_current_reveal_seat = None

        # Wire exit button in settings popup for multiplayer
        self._settings_popup.set_exit_callback(self._handle_exit_match)

    def set_network_tick_callback(self, callback: Callable[[], None]) -> None:
        """
        Register a zero-argument callable that is invoked once per frame from
        update(), before emotes are drained from the remote adapter.

        The networking layer uses this hook to pump the WsClient and route
        incoming server messages (PHASE_SELECTING, PRIVATE_HAND_STATE,
        EMOTE_BROADCAST, etc.) to the RemoteGameAdapter.

        .. note::
            TODO (PR-09 WS client bootstrap): wired from RoomLobbyScene after
            MATCH_START is received and the GameScene is constructed.
        """
        self._network_tick_callback = callback

    def set_exit_match_callback(self, callback: Callable[[], None]) -> None:
        """Register the function that sends MATCH_LEAVE to the server."""
        self._exit_match_callback = callback

    def _on_emote_selected(self, emote_id: str) -> None:
        """
        Internal callback wired to EmotePopup.

        Always displays the emote immediately on the local player's panel
        (seat 0) so single-player mode gives visual feedback.  In multiplayer
        the send callback transmits it to the server; the server broadcast
        then triggers show_emote() again via the adapter — the duplicate
        display is harmless as it simply resets the TTL.
        """
        self.show_emote(self._get_my_seat(), emote_id)
        if self._emote_send_callback is not None:
            self._emote_send_callback(emote_id)

    def show_emote(self, seat_index: int, emote_id: str) -> None:
        """
        Display an emote above the given seat's panel.

        Called by the networking layer when an EMOTE_BROADCAST arrives, or
        directly in tests.  Maps emote_id slug to an emoji string for display.
        """
        from fall_in.ui.emote_popup import EMOTE_CATALOG

        emoji = emote_id  # fallback: show slug
        for slug, em, _ in EMOTE_CATALOG:
            if slug == emote_id:
                emoji = em
                break
        self._emote_display[seat_index] = (emoji, self._emote_display_duration)

    def update(self, dt: float) -> None:
        """Update scene state."""
        if self.message_timer > 0:
            self.message_timer -= dt

        # Network tick: pump WS client and route messages to the adapter.
        if self._network_tick_callback is not None:
            self._network_tick_callback()

        # Sync eliminated state to settings popup (so exit button label updates)
        if self._remote_adapter is not None:
            self._settings_popup.set_eliminated(self._is_local_player_eliminated())

        # Drain incoming emotes from RemoteGameAdapter (multiplayer only)
        if self._remote_adapter is not None:
            for seat_index, emote_id in self._remote_adapter.pop_pending_emotes():
                self.show_emote(seat_index, emote_id)

        # Decay emote display TTLs
        expired = [s for s, (_, ttl) in self._emote_display.items() if ttl - dt <= 0]
        for s in expired:
            del self._emote_display[s]
        for s in list(self._emote_display):
            if s not in expired:
                emoji, ttl = self._emote_display[s]
                self._emote_display[s] = (emoji, ttl - dt)

        if self._remote_adapter is not None:
            self._advance_remote_reveal(dt)
            if self._update_remote_match_flow(dt):
                return
            if self.screen_shake_timer > 0:
                self.screen_shake_timer -= dt
                intensity = self.screen_shake_intensity
                self.screen_shake_offset = (
                    random.randint(-intensity, intensity),
                    random.randint(-intensity, intensity),
                )
                if self.screen_shake_timer <= 0:
                    self.screen_shake_offset = (0, 0)

            self.dust_effect.update(dt)

            board_rows = self._get_display_board_rows()
            for row_idx in range(min(NUM_ROWS, len(board_rows))):
                for col in range(len(board_rows[row_idx])):
                    card = board_rows[row_idx][col]
                    if card.number in self.soldier_figures:
                        figure = self.soldier_figures[card.number]
                        spawn_dust, trigger_shake = figure.update(dt)

                        if spawn_dust or trigger_shake:
                            visual_col = MAX_CARDS_PER_ROW - col
                            iso_x, iso_y = self._cart_to_iso(visual_col, row_idx)

                            if spawn_dust:
                                self.dust_effect.spawn(
                                    iso_x, iso_y, figure.get_dust_count()
                                )
                                # Play danger-level SFX on tile landing
                                from fall_in.core.audio_manager import AudioManager

                                danger = card.danger
                                sfx_map = {
                                    1: "sfx/drop_danger_1.wav",
                                    2: "sfx/drop_danger_2.wav",
                                    3: "sfx/drop_danger_3.wav",
                                    5: "sfx/drop_danger_5.mp3",
                                    7: "sfx/drop_danger_7.mp3",
                                }
                                sfx_path = sfx_map.get(danger)
                                if sfx_path:
                                    AudioManager().play_sfx(sfx_path)
                                # Trigger commander reaction on landing
                                self.commander.react_to_soldier(card.danger)
                            if trigger_shake:
                                self.screen_shake_intensity = figure.get_shake_intensity()
                                self.screen_shake_timer = SCREEN_SHAKE_DURATION

            committed = self._get_local_committed_score()
            self.commander.set_expression_from_danger(committed)
            self.commander.update(dt)
            return

        # Screen shake
        if self.screen_shake_timer > 0:
            self.screen_shake_timer -= dt
            intensity = self.screen_shake_intensity
            self.screen_shake_offset = (
                random.randint(-intensity, intensity),
                random.randint(-intensity, intensity),
            )
            if self.screen_shake_timer <= 0:
                self.screen_shake_offset = (0, 0)

        # Dust particles
        self.dust_effect.update(dt)

        # Update soldier figures and trigger effects
        board = self.rules.board
        for row_idx in range(NUM_ROWS):
            for col in range(len(board.rows[row_idx])):
                card = board.rows[row_idx][col]
                if card.number in self.soldier_figures:
                    figure = self.soldier_figures[card.number]
                    spawn_dust, trigger_shake = figure.update(dt)

                    if spawn_dust or trigger_shake:
                        visual_col = MAX_CARDS_PER_ROW - col
                        iso_x, iso_y = self._cart_to_iso(visual_col, row_idx)

                        if spawn_dust:
                            self.dust_effect.spawn(
                                iso_x, iso_y, figure.get_dust_count()
                            )
                            # Play danger-level SFX on tile landing
                            from fall_in.core.audio_manager import AudioManager

                            danger = card.danger
                            sfx_map = {
                                1: "sfx/drop_danger_1.wav",
                                2: "sfx/drop_danger_2.wav",
                                3: "sfx/drop_danger_3.wav",
                                5: "sfx/drop_danger_5.mp3",
                                7: "sfx/drop_danger_7.mp3",
                            }
                            sfx_path = sfx_map.get(danger)
                            if sfx_path:
                                AudioManager().play_sfx(sfx_path)
                            # Trigger commander reaction on landing
                            self.commander.react_to_soldier(card.danger)
                        if trigger_shake:
                            self.screen_shake_intensity = figure.get_shake_intensity()
                            self.screen_shake_timer = SCREEN_SHAKE_DURATION

        # Order announce animation (dealing runs concurrently)
        if self.phase == GamePhase.ORDER_ANNOUNCE:
            self._update_dealing_animation(dt)
            self._order_announce_timer += dt
            if self._order_announce_sub == 0:  # shuffle
                if self._order_announce_timer >= ORDER_ANNOUNCE_SHUFFLE_DURATION:
                    self._order_announce_sub = 1
                    self._order_announce_timer = 0.0
            elif self._order_announce_sub == 1:  # hold
                if self._order_announce_timer >= ORDER_ANNOUNCE_HOLD_DURATION:
                    self._order_announce_sub = 2
                    self._order_announce_timer = 0.0
            elif self._order_announce_sub == 2:  # shrink
                if self._order_announce_timer >= ORDER_ANNOUNCE_SHRINK_DURATION:
                    # If dealing already finished, go to SELECTING
                    all_dealt = all(tw.is_complete for _, tw in self.dealing_cards)
                    if all_dealt:
                        self.phase = GamePhase.SELECTING
                        self.turn_timer = TURN_TIMEOUT_SECONDS
                        self.dealing_cards.clear()
                    else:
                        self.phase = GamePhase.DEALING
            self.commander.update(dt)
            return

        # Dealing animation
        if self.phase == GamePhase.DEALING:
            self._update_dealing_animation(dt)
            self.commander.update(dt)
            return

        # Turn timer during selection
        if self.phase == GamePhase.SELECTING:
            if self._consume_selection_timer(dt, on_timeout=self._auto_select_card):
                return

        # Commander expression
        committed = self._get_local_committed_score()
        self.commander.set_expression_from_danger(committed)
        self.commander.update(dt)

        # Penalty animations
        if self.phase == GamePhase.PENALTY_ANIMATION:
            if self.penalty_tweens.update(dt):
                self.penalty_cards_animating.clear()
                self._start_next_placement()
            return

        if self.phase_timer > 0:
            self.phase_timer -= dt
            return

        # Phase transitions
        if self.phase == GamePhase.AI_THINKING:
            self._ai_select_cards()
        elif self.phase == GamePhase.PLACING_PLAYER:
            self._start_next_placement()
        elif self.phase == GamePhase.ROUND_END:
            self._go_to_result_scene()

    def render(self, screen: pygame.Surface) -> None:
        """Render scene to screen."""
        shake_x, shake_y = self.screen_shake_offset

        # Background (with shake + padding offset)
        screen.blit(
            self.background_image,
            (shake_x - SCREEN_SHAKE_PADDING, shake_y - SCREEN_SHAKE_PADDING),
        )

        self._draw_board(screen)
        self.dust_effect.render(screen, self.screen_shake_offset)
        self.commander.render(screen)
        self._draw_ui(screen)
        self._draw_hand(screen)

        # Dealing animation (also runs during ORDER_ANNOUNCE)
        if self.phase in (GamePhase.DEALING, GamePhase.ORDER_ANNOUNCE):
            self._draw_dealing_animation(screen)
            if self.phase == GamePhase.DEALING:
                hint = get_font(18).render("카드 배급 중...", True, AIR_FORCE_BLUE)
                screen.blit(
                    hint,
                    (SCREEN_WIDTH // 2 - hint.get_width() // 2, SCREEN_HEIGHT - 50),
                )

        # Order announce popup
        if self.phase == GamePhase.ORDER_ANNOUNCE:
            self._draw_order_announce(screen)

        # Penalty card animations
        self._draw_penalty_animation(screen)

        # Timer & hint during selection
        if self._should_show_selection_ui():
            self._draw_turn_timer(screen)
            if self._is_waiting_for_other_players():
                self._draw_waiting_dialog(screen)
            else:
                hint = get_font(14).render(
                    "카드를 클릭하여 선택, 다시 클릭 또는 [SPACE]로 확정",
                    True,
                    AIR_FORCE_BLUE,
                )
                hint_x = SCREEN_WIDTH // 2 - hint.get_width() // 2
                hint_y = UI_TOP_BAR_HEIGHT + 5
                pill_w = hint.get_width() + 16
                pill_h = hint.get_height() + 6
                hint_bg = pygame.Surface((pill_w, pill_h), pygame.SRCALPHA)
                pygame.draw.rect(
                    hint_bg,
                    (255, 255, 255, 200),
                    (0, 0, pill_w, pill_h),
                    border_radius=4,
                )
                screen.blit(hint_bg, (hint_x - 8, hint_y - 3))
                screen.blit(hint, (hint_x, hint_y))

        # Eliminated spectator banner (multiplayer only)
        if self._is_local_player_eliminated() and not self._has_remote_round_result_overlay():
            self._draw_eliminated_banner(screen)

        # Settings gear button (top-right)
        sx, sy = self._settings_btn_center
        r = self._settings_btn_radius
        from fall_in.utils.asset_manifest import AssetManifest

        icon_imgs = AssetManifest.get_loaded("icons")
        if "icon_settings_gear" in icon_imgs:
            gear_icon = pygame.transform.smoothscale(
                icon_imgs["icon_settings_gear"], (r * 2, r * 2)
            )
            screen.blit(gear_icon, (sx - r, sy - r))
        else:
            pygame.draw.circle(screen, (40, 50, 70, 200), (sx, sy), r)
            pygame.draw.circle(screen, AIR_FORCE_BLUE, (sx, sy), r, 2)
            gear_font = get_font(18)
            gear_text = gear_font.render("⚙", True, WHITE)
            screen.blit(gear_text, gear_text.get_rect(center=(sx, sy)))

        # Debug overlay (via mixin)
        self.draw_debug_overlay(screen)

        # Emote popup palette (PR-07) — rendered above everything except settings
        self._emote_popup.render(screen)

        if self._has_remote_round_result_overlay():
            self._draw_remote_round_result_overlay(screen)

        # Settings popup (always last — modal overlay)
        self._settings_popup.render(screen)

    def _draw_turn_timer(self, screen: pygame.Surface) -> None:
        """Draw the turn timer with color-coded urgency."""
        timer_font = get_font(28, "bold")
        seconds = max(0, int(self.turn_timer))

        if seconds > TIMER_WARNING_THRESHOLD:
            color = WHITE
        elif seconds > TIMER_DANGER_THRESHOLD:
            color = DANGER_WARNING
        else:
            color = DANGER_DANGER

        draw_outlined_text(
            screen, f"{seconds}s", timer_font, (280, 20), color, TOP_BAR_OUTLINE_COLOR
        )

    def _get_round_ready_button_rect(self) -> pygame.Rect:
        return pygame.Rect(SCREEN_WIDTH // 2 - 95, SCREEN_HEIGHT // 2 + 158, 190, 48)

    def _draw_waiting_dialog(self, screen: pygame.Surface) -> None:
        dots = "." * (int(pygame.time.get_ticks() / 400) % 4)
        font = get_font(18, "bold")
        small_font = get_font(14)
        title = font.render(f"다른 플레이어의 선택을 기다리는 중{dots}", True, WHITE)
        subtitle = small_font.render("모든 플레이어가 카드를 고르면 배치가 시작됩니다.", True, WHITE)

        box_w = max(title.get_width(), subtitle.get_width()) + 36
        box_h = title.get_height() + subtitle.get_height() + 30
        rect = pygame.Rect(0, 0, box_w, box_h)
        rect.center = (SCREEN_WIDTH // 2, UI_TOP_BAR_HEIGHT + 48)

        overlay = pygame.Surface((rect.width, rect.height), pygame.SRCALPHA)
        overlay.fill((20, 36, 56, 215))
        screen.blit(overlay, rect.topleft)
        pygame.draw.rect(screen, LIGHT_BLUE, rect, width=2, border_radius=10)
        screen.blit(title, title.get_rect(center=(rect.centerx, rect.y + 22)))
        screen.blit(subtitle, subtitle.get_rect(center=(rect.centerx, rect.y + 48)))

    def _draw_eliminated_banner(self, screen: pygame.Surface) -> None:
        """Draw a spectator banner for an eliminated player."""
        font = get_font(18, "bold")
        small_font = get_font(14)
        title = font.render("탈락 - 관전 중", True, (255, 100, 100))
        subtitle = small_font.render("위험도 66점 초과로 탈락했습니다.", True, WHITE)

        box_w = max(title.get_width(), subtitle.get_width()) + 36
        box_h = title.get_height() + subtitle.get_height() + 30
        rect = pygame.Rect(0, 0, box_w, box_h)
        rect.center = (SCREEN_WIDTH // 2, UI_TOP_BAR_HEIGHT + 48)

        overlay = pygame.Surface((rect.width, rect.height), pygame.SRCALPHA)
        overlay.fill((56, 20, 20, 215))
        screen.blit(overlay, rect.topleft)
        pygame.draw.rect(screen, (255, 100, 100), rect, width=2, border_radius=10)
        screen.blit(title, title.get_rect(center=(rect.centerx, rect.y + 22)))
        screen.blit(subtitle, subtitle.get_rect(center=(rect.centerx, rect.y + 48)))

    def _draw_remote_round_result_overlay(self, screen: pygame.Surface) -> None:
        result = self._remote_round_result
        if result is None:
            return

        overlay = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
        overlay.fill((8, 14, 22, 180))
        screen.blit(overlay, (0, 0))

        panel = pygame.Rect(0, 0, 760, 470)
        panel.center = (SCREEN_WIDTH // 2, SCREEN_HEIGHT // 2)
        panel_surface = pygame.Surface((panel.width, panel.height), pygame.SRCALPHA)
        panel_surface.fill((22, 34, 48, 235))
        screen.blit(panel_surface, panel.topleft)
        pygame.draw.rect(screen, LIGHT_BLUE, panel, width=3, border_radius=16)

        title_font = get_font(34, "bold")
        header_font = get_font(20, "bold")
        body_font = get_font(18)
        small_font = get_font(15)

        title = title_font.render(f"라운드 {result.get('round_number', '?')} 정산", True, WHITE)
        screen.blit(title, title.get_rect(center=(panel.centerx, panel.y + 42)))

        public = self._get_public_state()
        seats = sorted(public.seats, key=lambda seat: seat.seat_index) if public is not None else []
        col_x = [panel.x + 70, panel.x + 320, panel.x + 460, panel.x + 610]
        header_y = panel.y + 95
        headers = ["플레이어", "이번 라운드", "누적 위험도", "상태"]
        for idx, header in enumerate(headers):
            header_surf = header_font.render(header, True, WHITE)
            screen.blit(header_surf, (col_x[idx], header_y))
        pygame.draw.line(
            screen,
            LIGHT_BLUE,
            (panel.x + 45, header_y + 34),
            (panel.right - 45, header_y + 34),
            2,
        )

        round_danger = result.get("round_danger", {})
        total_scores = result.get("total_scores", {})
        eliminated = set(result.get("eliminated_seats", []))
        row_y = header_y + 56
        row_height = 58

        for seat in seats:
            is_local = seat.seat_index == self._get_my_seat()
            label = "나" if is_local else seat.display_name
            if seat.controller_type.name == "BOT":
                label = seat.display_name

            if seat.seat_index in eliminated:
                bg = pygame.Surface((panel.width - 90, row_height - 8), pygame.SRCALPHA)
                bg.fill((120, 32, 32, 105))
                screen.blit(bg, (panel.x + 45, row_y - 6))

            screen.blit(body_font.render(label, True, WHITE), (col_x[0], row_y))

            round_value = int(round_danger.get(seat.seat_index, 0))
            round_color = DANGER_DANGER if round_value > 0 else DANGER_SAFE
            round_text = f"+{round_value}" if round_value > 0 else "0"
            screen.blit(body_font.render(round_text, True, round_color), (col_x[1], row_y))

            total_value = int(total_scores.get(seat.seat_index, 0))
            total_color = get_danger_color(total_value)
            screen.blit(
                body_font.render(f"{total_value}/{GAME_OVER_SCORE}", True, total_color),
                (col_x[2], row_y),
            )

            if seat.seat_index in eliminated:
                status = "탈락"
                status_color = DANGER_DANGER
            else:
                status = "생존"
                status_color = DANGER_SAFE
            screen.blit(body_font.render(status, True, status_color), (col_x[3], row_y))
            row_y += row_height

        countdown = max(0, int(self._remote_round_result_timer + 0.999))
        if self._remote_round_result_acknowledged:
            footer_text = "확인 완료. 다른 플레이어를 기다리는 중..."
        elif result.get("game_over"):
            footer_text = f"{countdown}초 후 최종 결과 화면으로 이동합니다."
        else:
            footer_text = f"{countdown}초 후 자동으로 다음 라운드가 시작됩니다."
        footer = small_font.render(footer_text, True, WHITE)
        screen.blit(footer, footer.get_rect(center=(panel.centerx, panel.bottom - 118)))

        btn_rect = self._get_round_ready_button_rect()
        btn_color = (90, 120, 150) if self._remote_round_result_acknowledged else AIR_FORCE_BLUE
        pygame.draw.rect(screen, btn_color, btn_rect, border_radius=10)
        pygame.draw.rect(screen, WHITE, btn_rect, width=2, border_radius=10)
        btn_label = "확인 완료" if self._remote_round_result_acknowledged else "확인"
        btn_text = header_font.render(btn_label, True, WHITE)
        screen.blit(btn_text, btn_text.get_rect(center=btn_rect.center))

        shortcut = small_font.render("[ENTER] 또는 [SPACE]로 확인", True, WHITE)
        screen.blit(shortcut, shortcut.get_rect(center=(panel.centerx, panel.bottom - 24)))

    def _draw_dealing_animation(self, screen: pygame.Surface) -> None:
        """Draw cards flying from barracks to hand positions."""
        for card, tween in self.dealing_cards:
            if not tween.is_started or tween.is_complete:
                continue

            pos = tween.get_current_int()
            card_w, card_h = 50, 70
            card_rect = pygame.Rect(
                pos[0] - card_w // 2,
                pos[1] - card_h // 2,
                card_w,
                card_h,  # type: ignore
            )

            pygame.draw.rect(screen, DEALING_CARD_COLOR, card_rect, border_radius=5)
            pygame.draw.rect(
                screen, DEALING_CARD_BORDER_COLOR, card_rect, width=2, border_radius=5
            )

            num_font = get_font(14, "bold")
            num_text = num_font.render(f"#{card.number}", True, AIR_FORCE_BLUE)
            screen.blit(
                num_text,
                (
                    card_rect.centerx - num_text.get_width() // 2,
                    card_rect.centery - num_text.get_height() // 2,
                ),
            )

    def _draw_penalty_animation(self, screen: pygame.Surface) -> None:
        """Draw penalty cards shrinking and moving toward hangar/player."""
        for card, tween in self.penalty_cards_animating:
            if tween.is_complete:
                continue

            pos = tween.get_current_int()
            progress = tween.get_progress()

            scale = 1.0 - progress * 0.7
            card_w = int(40 * scale)
            card_h = int(55 * scale)

            if card_w > 5 and card_h > 5:
                card_rect = pygame.Rect(
                    pos[0] - card_w // 2,
                    pos[1] - card_h // 2,
                    card_w,
                    card_h,  # type: ignore
                )

                # penalty card colors
                if card.danger <= 2:
                    color = DANGER_SAFE
                elif card.danger <= 4:
                    color = DANGER_WARNING
                else:
                    color = DANGER_DANGER

                pygame.draw.rect(screen, color, card_rect, border_radius=3)
                pygame.draw.rect(
                    screen, AIR_FORCE_BLUE, card_rect, width=1, border_radius=3
                )

                if scale > 0.5:
                    num_font = get_font(int(12 * scale))
                    num_text = num_font.render(str(card.number), True, WHITE)
                    screen.blit(num_text, num_text.get_rect(center=card_rect.center))

    # ------------------------------------------------------------------
    # Debug hotkeys (via DebugOverlayMixin)
    # ------------------------------------------------------------------

    def _get_game_debug_hotkeys(self) -> list[DebugHotkey]:
        """Define in-game debug hotkeys."""
        return [
            DebugHotkey(pygame.K_F1, "강제 패배 (게임 오버)", self._debug_force_lose),
            DebugHotkey(pygame.K_F2, "강제 승리", self._debug_force_win),
            DebugHotkey(pygame.K_F3, "정산 화면으로 이동", self._go_to_result_scene),
            DebugHotkey(pygame.K_F4, "위험도 +30", self._debug_add_danger),
            DebugHotkey(pygame.K_F5, "위험도 초기화", self._debug_reset_danger),
            DebugHotkey(pygame.K_F6, "다음 라운드 스킵", self._debug_skip_round),
        ]

    def _debug_force_lose(self) -> None:
        """Force game over — eliminate human player."""
        from fall_in.core.game_manager import GameManager
        from fall_in.config import GAME_OVER_SCORE
        from fall_in.scenes.game_over_scene import GameOverScene

        self.human_player.penalty_score = GAME_OVER_SCORE + 1
        self.human_player.is_eliminated = True
        winner = next(
            (p for p in self.players if not p.is_eliminated and p != self.human_player),
            None,
        )
        GameManager().change_scene(
            GameOverScene(winner, self.players, self.rules.round_state.round_number)
        )

    def _debug_force_win(self) -> None:
        """Force victory — eliminate all AI."""
        from fall_in.core.game_manager import GameManager
        from fall_in.config import GAME_OVER_SCORE
        from fall_in.scenes.game_over_scene import GameOverScene

        for p in self.players:
            if p != self.human_player:
                p.penalty_score = GAME_OVER_SCORE + 1
                p.is_eliminated = True
        GameManager().change_scene(
            GameOverScene(
                self.human_player, self.players, self.rules.round_state.round_number
            )
        )

    def _debug_add_danger(self) -> None:
        """Add 30 danger to player."""
        pid = self.human_player.player_id
        self.rules.committed_scores[pid] += 30
        new_score = self.rules.committed_scores[pid]
        self.message = f"[DEBUG] 위험도 +30 → {new_score}"
        self.message_timer = 2.0
        self.is_debug_active = False

    def _debug_reset_danger(self) -> None:
        """Reset danger to 0."""
        pid = self.human_player.player_id
        self.rules.committed_scores[pid] = 0
        self.message = "[DEBUG] 위험도 초기화"
        self.message_timer = 2.0
        self.is_debug_active = False

    def _debug_skip_round(self) -> None:
        """Skip to next round."""
        self.phase = GamePhase.ROUND_END
        self.phase_timer = 0.1
        self.is_debug_active = False

    # ------------------------------------------------------------------
    # Order announce animation
    # ------------------------------------------------------------------

    def _draw_order_announce(self, screen: pygame.Surface) -> None:
        """Draw the player order popup with round title and shuffle/hold/shrink animation."""
        order = self.rules.player_order
        t = self._order_announce_timer
        sub = self._order_announce_sub
        round_num = self.rules.round_state.round_number

        def _label(p: object) -> str:
            return (
                "나"
                if p == self.human_player
                else getattr(p, "name", "").replace("AI ", "")
            )

        def _color(p: object) -> tuple:
            return DANGER_SAFE if p == self.human_player else LIGHT_BLUE

        # Target position (UI bar order display)
        target_x = UI_ELEMENT_PLAYER_ORDER_X
        target_y = UI_TOP_BAR_Y + 59

        # Center position
        center_x = SCREEN_WIDTH // 2
        center_y = SCREEN_HEIGHT // 2 - 50

        # Compute interpolation factor and position
        if sub == 2:  # shrink
            frac = min(t / ORDER_ANNOUNCE_SHRINK_DURATION, 1.0)
            frac = _ease_out_cubic(frac)
            scale = 1.0 - frac * 0.6  # 1.0 -> 0.4
            alpha = max(0, int(255 * (1.0 - frac)))
            pos_x = center_x + (target_x - center_x) * frac
            pos_y = center_y + (target_y - center_y) * frac
        else:  # shuffle or hold
            scale = 1.0
            alpha = 255
            pos_x = center_x
            pos_y = center_y

        # Reference font for size calculations
        title_font_size = max(8, int(20 * scale))
        order_font_size = max(8, int(18 * scale))
        title_font = get_font(title_font_size, "bold")
        order_font = get_font(order_font_size, "bold")

        # Round title text
        round_title = f"라운드 {round_num} 시작!"
        title_surf = title_font.render(round_title, True, WHITE)

        # Calculate order row width
        labels = [_label(p) for p in order]
        arrow_w = order_font.size(" → ")[0]
        total_text_w = sum(order_font.size(lbl)[0] for lbl in labels)
        total_text_w += arrow_w * (len(labels) - 1)

        # Panel size (wider of title or order row, + padding)
        content_w = max(title_surf.get_width(), total_text_w)
        panel_w = int((content_w + 60) * scale)
        panel_h = int(100 * scale)
        if panel_w < 10 or panel_h < 10:
            return

        popup = pygame.Surface((panel_w, panel_h), pygame.SRCALPHA)

        # Panel background — use popup_message HUD asset if available
        bg_alpha = min(alpha, 220)
        if "popup_message" in self._hud_images:
            popup_bg = pygame.transform.smoothscale(
                self._hud_images["popup_message"], (panel_w, panel_h)
            )
            popup_bg.set_alpha(bg_alpha)
            popup.blit(popup_bg, (0, 0))
        else:
            pygame.draw.rect(
                popup,
                (20, 30, 50, bg_alpha),
                (0, 0, panel_w, panel_h),
                border_radius=int(12 * scale),
            )
            pygame.draw.rect(
                popup,
                (*AIR_FORCE_BLUE, bg_alpha),
                (0, 0, panel_w, panel_h),
                width=max(1, int(2 * scale)),
                border_radius=int(12 * scale),
            )

        # Line 1: "라운드 N 시작!"
        title_y = int(12 * scale)
        title_x = panel_w // 2 - title_surf.get_width() // 2
        popup.blit(title_surf, (title_x, title_y))

        # Line 2: Player order with arrows
        name_y = int(55 * scale)

        # During shuffle sub-phase for round >= 2, show flash animation
        if sub == 0 and self._prev_order:
            shuffle_t = min(t / ORDER_ANNOUNCE_SHUFFLE_DURATION, 1.0)
            # Show old order first half, new order second half
            display_order = self._prev_order if shuffle_t < 0.5 else order
            # Flash effect
            flash_val = abs(((shuffle_t * 6) % 2) - 1)
            name_alpha = max(80, int(flash_val * 255))
        else:
            display_order = order
            name_alpha = alpha

        rendered_items: list[pygame.Surface] = []
        row_w = 0
        for i, p in enumerate(display_order):
            lbl = _label(p)
            col = _color(p)
            txt = order_font.render(lbl, True, (*col[:3], name_alpha))
            rendered_items.append(txt)
            row_w += txt.get_width()
            if i < len(display_order) - 1:
                arrow = order_font.render(" → ", True, (*LIGHT_BLUE[:3], name_alpha))
                rendered_items.append(arrow)
                row_w += arrow.get_width()

        # Center order row in panel
        x_offset = (panel_w - row_w) // 2
        for item in rendered_items:
            popup.blit(item, (x_offset, name_y))
            x_offset += item.get_width()

        # Blit popup to screen
        blit_x = int(pos_x) - panel_w // 2
        blit_y = int(pos_y) - panel_h // 2
        screen.blit(popup, (blit_x, blit_y))


def _ease_out_cubic(t: float) -> float:
    """Ease-out cubic for smooth deceleration."""
    return 1 - (1 - t) ** 3
