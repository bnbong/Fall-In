"""
Recruitment Scene - Interview and collect soldiers
"""

from enum import Enum, auto
from typing import Optional

import pygame

from fall_in.scenes.base_scene import Scene
from fall_in.utils.asset_loader import AssetLoader, get_font
from fall_in.entities.battalion_card import BattalionCard
from fall_in.entities.frozen_food import FrozenFood
from fall_in.data.soldier_data import SoldierInfo, get_soldier_manager
from fall_in.config import (
    SCREEN_WIDTH,
    SCREEN_HEIGHT,
    WHITE,
    AIR_FORCE_BLUE,
    DANGER_LEVEL_COLORS,
    RECRUIT_BTN_ROSTER_X,
    RECRUIT_BTN_ROSTER_Y,
    RECRUIT_BTN_INTERVIEW_X,
    RECRUIT_BTN_INTERVIEW_Y,
    RECRUIT_BTN_WIDTH,
    RECRUIT_BTN_HEIGHT,
    RECRUIT_ANNOUNCE_DURATION,
    RECRUIT_WALK_IN_DURATION,
    RECRUIT_FADE_OUT_DURATION,
    RECRUIT_PORTRAIT_X,
    RECRUIT_BUST_WIDTH,
    RECRUIT_BUST_HEIGHT,
    RECRUIT_BUST_ANCHOR_Y,
    RECRUIT_BUST_START_SCALE,
    RECRUIT_BUST_END_SCALE,
    RECRUIT_SPEECH_BUBBLE_X,
    RECRUIT_SPEECH_BUBBLE_Y,
    RECRUIT_NOTES_X,
    RECRUIT_NOTES_Y,
    RECRUIT_NOTES_WIDTH,
    RECRUIT_NOTES_HEIGHT,
    RECRUIT_CARD_X,
    RECRUIT_CARD_Y,
    RECRUIT_ROSTER_COLS,
    RECRUIT_ROSTER_ICON_SIZE,
    RECRUIT_ROSTER_ICON_GAP,
    RECRUIT_ROSTER_SCROLL_SPEED,
    RECRUIT_PANEL_BG,
    RECRUIT_PANEL_BORDER,
    RECRUIT_BTN_COLOR,
    RECRUIT_BTN_HOVER_COLOR,
    INTERVIEW_COST,
)


class RecruitPhase(Enum):
    """Recruitment scene phases"""

    INITIAL = auto()  # Two buttons visible
    ANNOUNCING = auto()  # Speaker announcement
    SOLDIER_ENTERING = auto()  # Silhouette walk-in
    INTERVIEW_DISPLAY = auto()  # Show soldier info
    SOLDIER_LEAVING = auto()  # Fade out
    ROSTER_VIEW = auto()  # Scrollable soldier list
    SOLDIER_DETAIL = auto()  # Detail view for selected soldier


class RecruitmentScene(Scene):
    """
    Soldier recruitment scene with interview flow and roster view.
    """

    # Button colors (from config)
    BTN_COLOR = RECRUIT_BTN_COLOR
    BTN_HOVER_COLOR = RECRUIT_BTN_HOVER_COLOR
    BTN_TEXT_COLOR = WHITE

    # Panel colors (from config)
    PANEL_BG = RECRUIT_PANEL_BG
    PANEL_BORDER = RECRUIT_PANEL_BORDER

    def __init__(self):
        super().__init__()

        # Initialize Battalion Card assets
        BattalionCard.initialize()

        # Load assets
        loader = AssetLoader()
        self.background = loader.load_image("ui/backgrounds/meetingroom_background.png")
        self.background = pygame.transform.smoothscale(
            self.background, (SCREEN_WIDTH, SCREEN_HEIGHT)
        )

        # UI images — pull from pre-loaded manifest cache
        from fall_in.utils.asset_manifest import AssetManifest

        self._ui_images: dict[str, pygame.Surface] = {}
        for category in ("panels", "icons"):
            self._ui_images.update(AssetManifest.get_loaded(category))

        # State
        self.phase = RecruitPhase.INITIAL
        self.phase_timer = 0.0
        self.current_soldier: Optional[SoldierInfo] = None
        self.soldier_manager = get_soldier_manager()

        # Button rects
        self.btn_roster_rect = pygame.Rect(
            RECRUIT_BTN_ROSTER_X,
            RECRUIT_BTN_ROSTER_Y,
            RECRUIT_BTN_WIDTH,
            RECRUIT_BTN_HEIGHT,
        )
        self.btn_interview_rect = pygame.Rect(
            RECRUIT_BTN_INTERVIEW_X,
            RECRUIT_BTN_INTERVIEW_Y,
            RECRUIT_BTN_WIDTH,
            RECRUIT_BTN_HEIGHT,
        )
        self.btn_confirm_rect = pygame.Rect(
            SCREEN_WIDTH // 2 - 60,
            SCREEN_HEIGHT - 80,
            120,
            40,
        )
        self.btn_back_rect = pygame.Rect(20, 20, 80, 35)
        self.btn_title_rect = pygame.Rect(20, 650, 100, 35)  # Back to title button

        # Hover states
        self.roster_hovered = False
        self.interview_hovered = False
        self.confirm_hovered = False
        self.back_hovered = False
        self.title_hovered = False

        # Animation states
        self.soldier_alpha = 0  # For silhouette/reveal
        self.soldier_scale = RECRUIT_BUST_START_SCALE  # For zoom animation
        self.element_alpha = 0  # For fade in/out of UI elements
        self.flash_alpha = 0  # For reveal flash

        # Roster view
        self.roster_scroll_y = 0
        self.roster_max_scroll = 0
        self.selected_soldier_id: Optional[int] = None

        # Toast message
        self.toast_message = ""
        self.toast_timer = 0.0

        # Frozen food entity
        self.frozen_food = FrozenFood()

    def on_enter(self) -> None:
        """Reset to initial state"""
        self.phase = RecruitPhase.INITIAL
        self.current_soldier = None

    def handle_event(self, event: pygame.event.Event) -> None:
        """Handle input events"""
        if event.type == pygame.MOUSEMOTION:
            self._handle_mouse_motion(event.pos)
        elif event.type == pygame.MOUSEBUTTONDOWN:
            if event.button == 1:  # Left click
                self._handle_click(event.pos)
            elif event.button == 4:  # Scroll up
                self._handle_scroll(-1)
            elif event.button == 5:  # Scroll down
                self._handle_scroll(1)
        elif event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                self._handle_back()

    def _handle_mouse_motion(self, pos: tuple[int, int]) -> None:
        """Update hover states"""
        from fall_in.core.audio_manager import AudioManager

        audio = AudioManager()
        prev_roster = self.roster_hovered
        prev_interview = self.interview_hovered
        prev_confirm = self.confirm_hovered
        prev_back = self.back_hovered
        prev_title = self.title_hovered

        self.roster_hovered = self.btn_roster_rect.collidepoint(pos)
        self.interview_hovered = self.btn_interview_rect.collidepoint(pos)
        self.confirm_hovered = self.btn_confirm_rect.collidepoint(pos)
        self.back_hovered = self.btn_back_rect.collidepoint(pos)
        self.title_hovered = self.btn_title_rect.collidepoint(pos)

        # Play cursor SFX on hover transitions
        if (
            (self.roster_hovered and not prev_roster)
            or (self.interview_hovered and not prev_interview)
            or (self.confirm_hovered and not prev_confirm)
            or (self.back_hovered and not prev_back)
            or (self.title_hovered and not prev_title)
        ):
            audio.play_sfx("sfx/cursor.wav")

    def _handle_click(self, pos: tuple[int, int]) -> None:
        """Handle mouse clicks"""
        from fall_in.core.audio_manager import AudioManager

        audio = AudioManager()

        if self.phase == RecruitPhase.INITIAL:
            if self.btn_title_rect.collidepoint(pos):
                audio.play_sfx("sfx/back.wav")
                self._handle_back()
            elif self.btn_roster_rect.collidepoint(pos):
                audio.play_sfx("sfx/confirm.wav")
                self._open_roster()
            elif self.btn_interview_rect.collidepoint(pos):
                audio.play_sfx("sfx/confirm.wav")
                self._start_interview()

        elif self.phase == RecruitPhase.INTERVIEW_DISPLAY:
            if self.btn_confirm_rect.collidepoint(pos):
                audio.play_sfx("sfx/confirm.wav")
                self._confirm_interview()

        elif self.phase == RecruitPhase.ROSTER_VIEW:
            if self.btn_back_rect.collidepoint(pos):
                audio.play_sfx("sfx/back.wav")
                self.phase = RecruitPhase.INITIAL
            else:
                self._handle_roster_click(pos)

        elif self.phase == RecruitPhase.SOLDIER_DETAIL:
            if self.btn_back_rect.collidepoint(pos):
                audio.play_sfx("sfx/back.wav")
                self.phase = RecruitPhase.ROSTER_VIEW

    def _handle_scroll(self, direction: int) -> None:
        """Handle scroll in roster view"""
        if self.phase == RecruitPhase.ROSTER_VIEW:
            self.roster_scroll_y += direction * RECRUIT_ROSTER_SCROLL_SPEED
            self.roster_scroll_y = max(
                0, min(self.roster_scroll_y, self.roster_max_scroll)
            )

    def _handle_back(self) -> None:
        """Handle back navigation"""
        if self.phase == RecruitPhase.ROSTER_VIEW:
            self.phase = RecruitPhase.INITIAL
        elif self.phase == RecruitPhase.SOLDIER_DETAIL:
            self.phase = RecruitPhase.ROSTER_VIEW
        elif self.phase == RecruitPhase.INITIAL:
            # Return to title scene
            from fall_in.core.game_manager import GameManager, GameState
            from fall_in.scenes.title_scene import TitleScene

            game = GameManager()
            game.state = GameState.TITLE
            game.change_scene(TitleScene())

    def _open_roster(self) -> None:
        """Open roster view"""
        self.phase = RecruitPhase.ROSTER_VIEW
        self.roster_scroll_y = 0
        # Calculate max scroll based on soldier count
        total_rows = (104 + RECRUIT_ROSTER_COLS - 1) // RECRUIT_ROSTER_COLS
        row_height = RECRUIT_ROSTER_ICON_SIZE + RECRUIT_ROSTER_ICON_GAP
        visible_rows = (SCREEN_HEIGHT - 100) // row_height
        self.roster_max_scroll = max(0, (total_rows - visible_rows) * row_height)

    def _start_interview(self) -> None:
        """Start interview flow"""
        # Check if player has enough currency
        from fall_in.core.game_manager import GameManager

        game_manager = GameManager()

        if not game_manager.has_currency(INTERVIEW_COST):
            self.toast_message = f"수당이 부족합니다! (필요: {INTERVIEW_COST}원, 보유: {game_manager.currency}원)"
            self.toast_timer = 2.5
            return

        self.current_soldier = self.soldier_manager.get_uncollected_soldier()
        if self.current_soldier:
            # Immediately deduct interview cost and collect soldier
            # (prevents exploit of closing game before confirm)
            game_manager.spend_currency(INTERVIEW_COST)
            self.soldier_manager.collect_soldier(self.current_soldier.id)

            self.phase = RecruitPhase.ANNOUNCING
            self.phase_timer = 0.0
            self.soldier_alpha = 0
            self.soldier_y_offset = 50
            self.element_alpha = 0
            # Set frozen food count based on soldier data
            self.frozen_food.set_count(self.current_soldier.frozen_food_count)

            # Play door knock SFX at start of interview
            from fall_in.core.audio_manager import AudioManager

            AudioManager().play_sfx("sfx/door_knock.wav")
        else:
            self.toast_message = "모든 병사를 모집했습니다!"
            self.toast_timer = 2.0

    def _confirm_interview(self) -> None:
        """Confirm interview - soldier already collected at start"""
        self.phase = RecruitPhase.SOLDIER_LEAVING
        self.phase_timer = 0.0

        # Play door close SFX after dismissing soldier
        from fall_in.core.audio_manager import AudioManager

        AudioManager().play_sfx("sfx/door_close.wav")

    def _handle_roster_click(self, pos: tuple[int, int]) -> None:
        """Handle click on roster grid"""
        # Calculate which icon was clicked
        start_x = (
            SCREEN_WIDTH
            - (
                RECRUIT_ROSTER_COLS
                * (RECRUIT_ROSTER_ICON_SIZE + RECRUIT_ROSTER_ICON_GAP)
            )
        ) // 2
        start_y = 80 - self.roster_scroll_y

        for i in range(1, 105):  # Cards 1-104
            row = (i - 1) // RECRUIT_ROSTER_COLS
            col = (i - 1) % RECRUIT_ROSTER_COLS

            icon_x = start_x + col * (
                RECRUIT_ROSTER_ICON_SIZE + RECRUIT_ROSTER_ICON_GAP
            )
            icon_y = start_y + row * (
                RECRUIT_ROSTER_ICON_SIZE + RECRUIT_ROSTER_ICON_GAP
            )

            icon_rect = pygame.Rect(
                icon_x, icon_y, RECRUIT_ROSTER_ICON_SIZE, RECRUIT_ROSTER_ICON_SIZE
            )

            if icon_rect.collidepoint(pos):
                if self.soldier_manager.is_collected(i):
                    self.selected_soldier_id = i
                    self.phase = RecruitPhase.SOLDIER_DETAIL
                else:
                    from fall_in.core.audio_manager import AudioManager

                    AudioManager().play_sfx("sfx/error.wav")
                    self.toast_message = "아직 모르는 병사다"
                    self.toast_timer = 1.5
                break

    def update(self, dt: float) -> None:
        """Update scene state"""
        self.phase_timer += dt

        # Update toast
        if self.toast_timer > 0:
            self.toast_timer -= dt

        # Phase transitions
        if self.phase == RecruitPhase.ANNOUNCING:
            if self.phase_timer >= RECRUIT_ANNOUNCE_DURATION:
                self.phase = RecruitPhase.SOLDIER_ENTERING
                self.phase_timer = 0.0

                # Play door open SFX when silhouette appears
                from fall_in.core.audio_manager import AudioManager

                AudioManager().play_sfx("sfx/door_open.wav")

        elif self.phase == RecruitPhase.SOLDIER_ENTERING:
            # Animate soldier zooming in (bottom-anchored)
            progress = min(1.0, self.phase_timer / RECRUIT_WALK_IN_DURATION)
            # Ease-out for smooth zoom
            eased_progress = 1 - (1 - progress) ** 2
            self.soldier_scale = (
                RECRUIT_BUST_START_SCALE
                + (RECRUIT_BUST_END_SCALE - RECRUIT_BUST_START_SCALE) * eased_progress
            )

            if progress < 0.7:
                # Still silhouette
                self.soldier_alpha = 255
            else:
                # Start reveal with flash
                reveal_progress = (progress - 0.7) / 0.3
                self.flash_alpha = int(255 * (1 - reveal_progress))

            if self.phase_timer >= RECRUIT_WALK_IN_DURATION + 0.5:
                self.phase = RecruitPhase.INTERVIEW_DISPLAY
                self.phase_timer = 0.0
                self.element_alpha = 0
                self.soldier_scale = RECRUIT_BUST_END_SCALE

        elif self.phase == RecruitPhase.INTERVIEW_DISPLAY:
            # Fade in elements
            self.element_alpha = min(255, self.element_alpha + int(dt * 500))
            # Update frozen food animation
            self.frozen_food.update(dt)

        elif self.phase == RecruitPhase.SOLDIER_LEAVING:
            # Fade out
            progress = min(1.0, self.phase_timer / RECRUIT_FADE_OUT_DURATION)
            self.element_alpha = int(255 * (1 - progress))
            self.soldier_alpha = int(255 * (1 - progress))

            if progress >= 1.0:
                self.phase = RecruitPhase.INITIAL
                self.current_soldier = None

    def render(self, screen: pygame.Surface) -> None:
        """Render scene"""
        # Draw background
        screen.blit(self.background, (0, 0))

        if self.phase == RecruitPhase.INITIAL:
            self._render_initial_buttons(screen)
        elif self.phase == RecruitPhase.ANNOUNCING:
            self._render_announcement(screen)
        elif self.phase in (
            RecruitPhase.SOLDIER_ENTERING,
            RecruitPhase.INTERVIEW_DISPLAY,
        ):
            self._render_interview(screen)
        elif self.phase == RecruitPhase.SOLDIER_LEAVING:
            self._render_interview(screen)
        elif self.phase == RecruitPhase.ROSTER_VIEW:
            self._render_roster(screen)
        elif self.phase == RecruitPhase.SOLDIER_DETAIL:
            self._render_soldier_detail(screen)

        # Render toast
        if self.toast_timer > 0:
            self._render_toast(screen)

    def _render_initial_buttons(self, screen: pygame.Surface) -> None:
        """Render initial state with two buttons"""
        font = get_font(16)
        small_font = get_font(14)

        # Back to title button (top-left)
        color = self.BTN_HOVER_COLOR if self.title_hovered else self.BTN_COLOR
        pygame.draw.rect(screen, color, self.btn_title_rect, border_radius=5)
        pygame.draw.rect(
            screen, AIR_FORCE_BLUE, self.btn_title_rect, width=2, border_radius=5
        )
        text = small_font.render("← 타이틀", True, self.BTN_TEXT_COLOR)
        text_rect = text.get_rect(center=self.btn_title_rect.center)
        screen.blit(text, text_rect)

        # Roster button (near notepad)
        color = self.BTN_HOVER_COLOR if self.roster_hovered else self.BTN_COLOR
        pygame.draw.rect(screen, color, self.btn_roster_rect, border_radius=5)
        pygame.draw.rect(
            screen, AIR_FORCE_BLUE, self.btn_roster_rect, width=2, border_radius=5
        )
        text = font.render("모집 병사 현황", True, self.BTN_TEXT_COLOR)
        text_rect = text.get_rect(center=self.btn_roster_rect.center)
        screen.blit(text, text_rect)

        # Interview button (near microphone)
        color = self.BTN_HOVER_COLOR if self.interview_hovered else self.BTN_COLOR
        pygame.draw.rect(screen, color, self.btn_interview_rect, border_radius=5)
        pygame.draw.rect(
            screen, AIR_FORCE_BLUE, self.btn_interview_rect, width=2, border_radius=5
        )
        text = font.render("면담하기", True, self.BTN_TEXT_COLOR)
        text_rect = text.get_rect(center=self.btn_interview_rect.center)
        screen.blit(text, text_rect)

        # Display currency and interview cost
        from fall_in.core.game_manager import GameManager

        game_manager = GameManager()

        # Currency info box (top-right)
        currency_font = get_font(14)
        cost_font = get_font(12)

        info_rect = pygame.Rect(SCREEN_WIDTH - 220, 20, 205, 75)
        if "panel_currency_info_sm" in self._ui_images:
            info_img = pygame.transform.smoothscale(
                self._ui_images["panel_currency_info_sm"],
                (info_rect.width, info_rect.height),
            )
            screen.blit(info_img, info_rect.topleft)
        else:
            pygame.draw.rect(screen, (255, 255, 255, 220), info_rect, border_radius=8)
            pygame.draw.rect(
                screen, AIR_FORCE_BLUE, info_rect, width=2, border_radius=8
            )

        currency_text = currency_font.render(
            f"보유 수당: {game_manager.currency}원", True, AIR_FORCE_BLUE
        )
        screen.blit(currency_text, (info_rect.x + 70, info_rect.y + 15))

        cost_text = cost_font.render(
            f"면담 비용: {INTERVIEW_COST}원", True, (100, 100, 100)
        )
        screen.blit(cost_text, (info_rect.x + 70, info_rect.y + 42))

    def _render_announcement(self, screen: pygame.Surface) -> None:
        """Render speaker announcement"""
        # Draw speech bubble near speaker (top-left)
        bubble_rect = pygame.Rect(100, 60, 300, 50)
        pygame.draw.rect(screen, WHITE, bubble_rect, border_radius=10)
        pygame.draw.rect(screen, (50, 50, 50), bubble_rect, width=2, border_radius=10)

        font = get_font(14)
        text = font.render("호명하는 병사는 작전계 사무실로 올 것", True, (30, 30, 30))
        text_rect = text.get_rect(center=bubble_rect.center)
        screen.blit(text, text_rect)

    def _render_interview(self, screen: pygame.Surface) -> None:
        """Render interview display"""
        if not self.current_soldier:
            return

        # Load bust image from soldiers folder
        loader = AssetLoader()
        bust_path = f"characters/soldiers/soldier_{self.current_soldier.id}.png"
        try:
            bust_image = loader.load_image(bust_path)
        except Exception:
            # Fallback to portrait if bust not found
            bust_image = BattalionCard._get_portrait_hr_for_danger(
                self.current_soldier.danger, self.current_soldier.id
            )

        if bust_image:
            # Calculate scaled size based on animation progress
            scaled_width = int(RECRUIT_BUST_WIDTH * self.soldier_scale)
            scaled_height = int(RECRUIT_BUST_HEIGHT * self.soldier_scale)

            # Scale the image
            scaled_bust = pygame.transform.smoothscale(
                bust_image, (scaled_width, scaled_height)
            )

            # Apply silhouette effect if entering (before 70% progress)
            if (
                self.phase == RecruitPhase.SOLDIER_ENTERING
                and self.phase_timer < RECRUIT_WALK_IN_DURATION * 0.7
            ):
                silhouette = scaled_bust.copy()
                silhouette.fill((0, 0, 0, 255), special_flags=pygame.BLEND_RGBA_MULT)
                scaled_bust = silhouette

            # Apply alpha for fade out
            if self.soldier_alpha < 255:
                scaled_bust.set_alpha(self.soldier_alpha)

            # Position: center horizontally at PORTRAIT_X, anchor bottom at table edge
            bust_x = RECRUIT_PORTRAIT_X + (RECRUIT_BUST_WIDTH - scaled_width) // 2
            bust_y = RECRUIT_BUST_ANCHOR_Y - scaled_height  # Bottom anchored

            screen.blit(scaled_bust, (bust_x, bust_y))

        # Flash effect
        if self.flash_alpha > 0:
            flash_surface = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT))
            flash_surface.fill((255, 255, 255))
            flash_surface.set_alpha(self.flash_alpha)
            screen.blit(flash_surface, (0, 0))

        # Render frozen food on table (only visible during interview)
        if self.phase in (RecruitPhase.INTERVIEW_DISPLAY, RecruitPhase.SOLDIER_LEAVING):
            self.frozen_food.render(screen, alpha=min(255, self.element_alpha))

        # Only show UI elements after entering
        if self.phase != RecruitPhase.SOLDIER_ENTERING:
            self._render_interview_ui(screen)

    def _render_interview_ui(self, screen: pygame.Surface) -> None:
        """Render interview UI elements with fade"""
        if not self.current_soldier:
            return

        # Create surface for alpha blending
        ui_surface = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)

        # Speech bubble
        bubble_rect = pygame.Rect(
            RECRUIT_SPEECH_BUBBLE_X, RECRUIT_SPEECH_BUBBLE_Y, 280, 60
        )
        pygame.draw.rect(
            ui_surface, (*WHITE, self.element_alpha), bubble_rect, border_radius=10
        )
        pygame.draw.rect(
            ui_surface,
            (*self.PANEL_BORDER, self.element_alpha),
            bubble_rect,
            width=2,
            border_radius=10,
        )

        font = get_font(14)
        intro_text = self.current_soldier.intro
        text = font.render(intro_text, True, (30, 30, 30))
        text.set_alpha(self.element_alpha)
        text_rect = text.get_rect(center=bubble_rect.center)
        ui_surface.blit(text, text_rect)

        # Notes panel
        notes_rect = pygame.Rect(
            RECRUIT_NOTES_X, RECRUIT_NOTES_Y, RECRUIT_NOTES_WIDTH, RECRUIT_NOTES_HEIGHT
        )
        if "panel_notes" in self._ui_images:
            notes_img = pygame.transform.smoothscale(
                self._ui_images["panel_notes"],
                (notes_rect.width, notes_rect.height),
            )
            notes_img.set_alpha(self.element_alpha)
            ui_surface.blit(notes_img, notes_rect.topleft)
        else:
            pygame.draw.rect(
                ui_surface,
                (*self.PANEL_BG, self.element_alpha),
                notes_rect,
                border_radius=5,
            )
            pygame.draw.rect(
                ui_surface,
                (*self.PANEL_BORDER, self.element_alpha),
                notes_rect,
                width=2,
                border_radius=5,
            )

        # Notes content
        title_font = get_font(18, "bold")
        small_font = get_font(14)

        y_offset = notes_rect.top + 15

        # Name and rank
        name_text = f"{self.current_soldier.name} {self.current_soldier.rank}"
        text = title_font.render(name_text, True, (30, 30, 30))
        text.set_alpha(self.element_alpha)
        ui_surface.blit(text, (notes_rect.left + 15, y_offset))
        y_offset += 30

        # Unit
        text = small_font.render(
            f"소속: {self.current_soldier.unit}", True, (60, 60, 60)
        )
        text.set_alpha(self.element_alpha)
        ui_surface.blit(text, (notes_rect.left + 15, y_offset))
        y_offset += 25

        # Separator
        pygame.draw.line(
            ui_surface,
            (*self.PANEL_BORDER, self.element_alpha),
            (notes_rect.left + 15, y_offset),
            (notes_rect.right - 15, y_offset),
            1,
        )
        y_offset += 15

        # Note (multi-line, fill available space above danger label)
        note_lines = self.current_soldier.note.split("\n")
        line_height = 22
        danger_label_y = notes_rect.bottom - 50
        max_note_lines = max(1, (danger_label_y - y_offset) // line_height)
        for line in note_lines[:max_note_lines]:
            text = small_font.render(line, True, (60, 60, 60))
            text.set_alpha(self.element_alpha)
            ui_surface.blit(text, (notes_rect.left + 15, y_offset))
            y_offset += line_height

        # Danger level
        y_offset = danger_label_y
        danger_color = DANGER_LEVEL_COLORS.get(
            self.current_soldier.danger, (100, 100, 100)
        )
        text = small_font.render(
            f"위험도: {self.current_soldier.danger}", True, danger_color
        )
        text.set_alpha(self.element_alpha)
        ui_surface.blit(text, (notes_rect.left + 15, y_offset))

        screen.blit(ui_surface, (0, 0))

        # Battalion card (rendered directly for proper alpha handling)
        if self.element_alpha > 200:  # Only show when mostly visible
            card = self.current_soldier.to_card()
            BattalionCard.render(
                screen,
                card,
                RECRUIT_CARD_X,
                RECRUIT_CARD_Y,
                is_interviewed=True,
                rotation=-15,
            )

        # Confirm button
        self._render_confirm_button(screen)

    def _render_confirm_button(self, screen: pygame.Surface) -> None:
        """Render confirm button"""
        font = get_font(16)
        color = self.BTN_HOVER_COLOR if self.confirm_hovered else self.BTN_COLOR

        btn_surface = pygame.Surface(
            (self.btn_confirm_rect.width, self.btn_confirm_rect.height), pygame.SRCALPHA
        )
        pygame.draw.rect(
            btn_surface,
            (*color, self.element_alpha),
            btn_surface.get_rect(),
            border_radius=5,
        )
        pygame.draw.rect(
            btn_surface,
            (*AIR_FORCE_BLUE, self.element_alpha),
            btn_surface.get_rect(),
            width=2,
            border_radius=5,
        )

        text = font.render("어, 가봐", True, self.BTN_TEXT_COLOR)
        text.set_alpha(self.element_alpha)
        text_rect = text.get_rect(
            center=(self.btn_confirm_rect.width // 2, self.btn_confirm_rect.height // 2)
        )
        btn_surface.blit(text, text_rect)

        screen.blit(btn_surface, self.btn_confirm_rect.topleft)

    def _render_roster(self, screen: pygame.Surface) -> None:
        """Render soldier roster grid"""
        # Semi-transparent overlay
        overlay = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 180))
        screen.blit(overlay, (0, 0))

        # Title
        title_font = get_font(24, "bold")
        title = title_font.render("모집 병사 현황", True, WHITE)
        screen.blit(title, (SCREEN_WIDTH // 2 - title.get_width() // 2, 25))

        # Back button
        font = get_font(14)
        color = self.BTN_HOVER_COLOR if self.back_hovered else self.BTN_COLOR
        pygame.draw.rect(screen, color, self.btn_back_rect, border_radius=5)
        text = font.render("← 돌아가기", True, WHITE)
        text_rect = text.get_rect(center=self.btn_back_rect.center)
        screen.blit(text, text_rect)

        # Create clipping rect for scrollable area
        scroll_area = pygame.Rect(0, 70, SCREEN_WIDTH, SCREEN_HEIGHT - 70)

        # Grid rendering
        start_x = (
            SCREEN_WIDTH
            - (
                RECRUIT_ROSTER_COLS
                * (RECRUIT_ROSTER_ICON_SIZE + RECRUIT_ROSTER_ICON_GAP)
            )
        ) // 2
        start_y = 80 - self.roster_scroll_y

        for i in range(1, 105):  # Cards 1-104
            row = (i - 1) // RECRUIT_ROSTER_COLS
            col = (i - 1) % RECRUIT_ROSTER_COLS

            icon_x = start_x + col * (
                RECRUIT_ROSTER_ICON_SIZE + RECRUIT_ROSTER_ICON_GAP
            )
            icon_y = start_y + row * (
                RECRUIT_ROSTER_ICON_SIZE + RECRUIT_ROSTER_ICON_GAP
            )

            # Skip if outside visible area
            if (
                icon_y + RECRUIT_ROSTER_ICON_SIZE < scroll_area.top
                or icon_y > scroll_area.bottom
            ):
                continue

            self._render_soldier_icon(screen, i, icon_x, icon_y)

        # Scroll indicator
        if self.roster_max_scroll > 0:
            indicator_height = max(
                30,
                (SCREEN_HEIGHT - 100)
                * (SCREEN_HEIGHT - 100)
                // (self.roster_max_scroll + SCREEN_HEIGHT - 100),
            )
            indicator_y = 70 + int(
                (SCREEN_HEIGHT - 100 - indicator_height)
                * self.roster_scroll_y
                / self.roster_max_scroll
            )
            pygame.draw.rect(
                screen,
                (100, 100, 100),
                (SCREEN_WIDTH - 15, indicator_y, 8, indicator_height),
                border_radius=4,
            )

    def _render_soldier_icon(
        self, screen: pygame.Surface, soldier_id: int, x: int, y: int
    ) -> None:
        """Render a single soldier icon in roster"""
        from fall_in.core.card import calculate_danger

        danger = calculate_danger(soldier_id)
        is_collected = self.soldier_manager.is_collected(soldier_id)

        # Icon background
        icon_rect = pygame.Rect(
            x, y, RECRUIT_ROSTER_ICON_SIZE, RECRUIT_ROSTER_ICON_SIZE
        )

        if is_collected:
            # Show portrait
            portrait = BattalionCard.get_portrait_for_danger(danger, soldier_id)
            if portrait:
                portrait = pygame.transform.smoothscale(
                    portrait, (RECRUIT_ROSTER_ICON_SIZE, RECRUIT_ROSTER_ICON_SIZE)
                )
                screen.blit(portrait, (x, y))
            pygame.draw.rect(
                screen, AIR_FORCE_BLUE, icon_rect, width=2, border_radius=5
            )
        else:
            # Silhouette placeholder
            pygame.draw.rect(screen, (40, 40, 40), icon_rect, border_radius=5)
            pygame.draw.rect(screen, (80, 80, 80), icon_rect, width=2, border_radius=5)

            # Question mark
            font = get_font(24)
            text = font.render("?", True, (100, 100, 100))
            text_rect = text.get_rect(center=icon_rect.center)
            screen.blit(text, text_rect)

        # Number circle (top-left)
        circle_color = DANGER_LEVEL_COLORS.get(danger, (100, 100, 100))
        circle_center = (x + 15, y + 15)
        pygame.draw.circle(screen, circle_color, circle_center, 12)
        pygame.draw.circle(screen, WHITE, circle_center, 12, width=1)

        font = get_font(10)
        num_text = font.render(str(soldier_id), True, WHITE)
        num_rect = num_text.get_rect(center=circle_center)
        screen.blit(num_text, num_rect)

    def _render_soldier_detail(self, screen: pygame.Surface) -> None:
        """Render soldier detail view"""
        if not self.selected_soldier_id:
            return

        soldier = self.soldier_manager.get_soldier(self.selected_soldier_id)
        if not soldier:
            # If soldier not in data, show basic info
            from fall_in.core.card import calculate_danger

            danger = calculate_danger(self.selected_soldier_id)
            soldier = SoldierInfo(
                id=self.selected_soldier_id,
                name=f"병사 #{self.selected_soldier_id}",
                rank="일병",
                unit="미정",
                note="데이터 없음",
                intro="...",
                danger=danger,
                is_collected=True,
            )

        # Dark overlay
        overlay = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 200))
        screen.blit(overlay, (0, 0))

        # Detail panel (resume style)
        panel_rect = pygame.Rect(100, 60, SCREEN_WIDTH - 200, SCREEN_HEIGHT - 160)
        if "panel_soldier_detail" in self._ui_images:
            detail_img = pygame.transform.smoothscale(
                self._ui_images["panel_soldier_detail"],
                (panel_rect.width, panel_rect.height),
            )
            screen.blit(detail_img, panel_rect.topleft)
        else:
            pygame.draw.rect(screen, self.PANEL_BG, panel_rect, border_radius=10)
            pygame.draw.rect(
                screen, self.PANEL_BORDER, panel_rect, width=3, border_radius=10
            )

        # Portrait (left side)
        portrait = BattalionCard._get_portrait_hr_for_danger(soldier.danger, soldier.id)
        if portrait:
            portrait = pygame.transform.smoothscale(portrait, (180, 180))
            screen.blit(portrait, (panel_rect.left + 30, panel_rect.top + 30))

        # Info (right side)
        info_x = panel_rect.left + 240
        y_offset = panel_rect.top + 30

        title_font = get_font(22, "bold")
        font = get_font(16)
        small_font = get_font(14)

        # Name
        text = title_font.render(soldier.name, True, (30, 30, 30))
        screen.blit(text, (info_x, y_offset))
        y_offset += 35

        # Rank and unit
        text = font.render(f"{soldier.rank} | {soldier.unit}", True, (60, 60, 60))
        screen.blit(text, (info_x, y_offset))
        y_offset += 30

        # Separator
        pygame.draw.line(
            screen,
            self.PANEL_BORDER,
            (info_x, y_offset),
            (panel_rect.right - 30, y_offset),
            1,
        )
        y_offset += 15

        # Note (fill available space above the danger label area)
        note_lines = soldier.note.split("\n")
        line_height = 24
        danger_area_y = panel_rect.bottom - 190  # Leave room for danger + card
        max_note_lines = max(1, (danger_area_y - y_offset) // line_height)
        for line in note_lines[:max_note_lines]:
            text = small_font.render(line, True, (60, 60, 60))
            screen.blit(text, (info_x, y_offset))
            y_offset += line_height

        # Danger
        y_offset += 20
        danger_color = DANGER_LEVEL_COLORS.get(soldier.danger, (100, 100, 100))
        text = font.render(f"위험도: {soldier.danger}", True, danger_color)
        screen.blit(text, (info_x, y_offset))

        # Battalion card (tilted at bottom)
        card = soldier.to_card()
        card_x = panel_rect.centerx - 50
        card_y = panel_rect.bottom - 140
        BattalionCard.render(
            screen, card, card_x, card_y, is_interviewed=True, rotation=12
        )

        # Back button
        font = get_font(14)
        color = self.BTN_HOVER_COLOR if self.back_hovered else self.BTN_COLOR
        pygame.draw.rect(screen, color, self.btn_back_rect, border_radius=5)
        text = font.render("← 돌아가기", True, WHITE)
        text_rect = text.get_rect(center=self.btn_back_rect.center)
        screen.blit(text, text_rect)

    def _render_toast(self, screen: pygame.Surface) -> None:
        """Render toast message"""
        font = get_font(16)
        text = font.render(self.toast_message, True, WHITE)

        padding = 20
        toast_rect = pygame.Rect(
            SCREEN_WIDTH // 2 - text.get_width() // 2 - padding,
            SCREEN_HEIGHT - 120,
            text.get_width() + padding * 2,
            40,
        )

        # Fade based on timer
        alpha = min(255, int(self.toast_timer * 300))

        toast_surface = pygame.Surface(
            (toast_rect.width, toast_rect.height), pygame.SRCALPHA
        )
        if "toast_bg" in self._ui_images:
            toast_bg = pygame.transform.smoothscale(
                self._ui_images["toast_bg"],
                (toast_rect.width, toast_rect.height),
            )
            toast_bg.set_alpha(alpha)
            toast_surface.blit(toast_bg, (0, 0))
        else:
            pygame.draw.rect(
                toast_surface,
                (40, 40, 40, alpha),
                toast_surface.get_rect(),
                border_radius=8,
            )
        screen.blit(toast_surface, toast_rect.topleft)

        text.set_alpha(alpha)
        screen.blit(
            text,
            (toast_rect.left + padding, toast_rect.centery - text.get_height() // 2),
        )
