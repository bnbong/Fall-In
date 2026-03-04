"""
Title Scene - Game start screen
"""

import pygame

from fall_in.scenes.base_scene import Scene
from fall_in.ui.button import Button
from fall_in.utils.asset_loader import get_font
from fall_in.utils.text_utils import draw_outlined_text
from fall_in.config import (
    SCREEN_WIDTH,
    SCREEN_HEIGHT,
    AIR_FORCE_BLUE,
    LIGHT_BLUE,
    IMAGES_DIR,
    DEVELOPER_PROFILE_IMAGE,
    DEVELOPER_NAME,
    DEVELOPER_GITHUB,
    DEVELOPER_MILITARY,
    DEVELOPER_NICKNAME,
    WHITE,
)


class TitleScene(Scene):
    """
    Title screen with game logo and menu buttons.
    """

    def __init__(self):
        super().__init__()
        self.buttons: list[Button] = []
        self.show_dev_info = False  # Developer info popup state

        # Settings popup
        from fall_in.ui.settings_popup import SettingsPopup

        self._settings_popup = SettingsPopup()

        # Player info popup
        from fall_in.ui.player_info_popup import PlayerInfoPopup

        self._player_info_popup = PlayerInfoPopup()

        # Start title BGM
        from fall_in.core.audio_manager import AudioManager
        from fall_in.config import TITLE_BGM_PATH

        AudioManager().play_bgm(TITLE_BGM_PATH)

        # Player profile icon (top-left corner)
        self.profile_btn_center = (40, 40)
        self.profile_btn_radius = 24

        # Circular button positions (top-right corner)
        self.intro_btn_center = (SCREEN_WIDTH - 150, 40)
        self.tutorial_btn_center = (SCREEN_WIDTH - 100, 40)
        self.info_btn_center = (SCREEN_WIDTH - 50, 40)
        self.circle_btn_radius = 18

        # Load developer profile image
        self.dev_profile_image = self._load_dev_profile_image()

        # Load background and logo images
        self._bg_image = self._load_and_scale_bg()
        self._logo_image = self._load_logo()

        # Breathing animation state
        self._anim_timer: float = 0.0

        # UI images — pull from pre-loaded manifest cache
        from fall_in.utils.asset_manifest import AssetManifest

        self._ui_images: dict[str, pygame.Surface] = {}
        for category in ("panels", "icons", "hud", "buttons"):
            self._ui_images.update(AssetManifest.get_loaded(category))

        self._setup_ui()

    def _setup_ui(self) -> None:
        """Setup UI elements"""
        button_width = 200
        button_height = 50
        button_x = SCREEN_WIDTH // 2 - button_width // 2
        button_start_y = SCREEN_HEIGHT // 2 + 50
        button_spacing = 70

        # Game start button
        self.buttons.append(
            Button(
                x=button_x,
                y=button_start_y,
                width=button_width,
                height=button_height,
                text="게임 시작",
                callback=self._on_start_game,
            )
        )

        # Collection button
        self.buttons.append(
            Button(
                x=button_x,
                y=button_start_y + button_spacing,
                width=button_width,
                height=button_height,
                text="병사 수집",
                callback=self._on_collection,
            )
        )

        # Settings button
        self.buttons.append(
            Button(
                x=button_x,
                y=button_start_y + button_spacing * 2,
                width=button_width,
                height=button_height,
                text="설정",
                callback=self._on_settings,
            )
        )

        # Prestige button (only visible if coup was achieved)
        from fall_in.core.prestige_manager import PrestigeManager

        if PrestigeManager().can_prestige():
            self.buttons.append(
                Button(
                    x=button_x,
                    y=button_start_y + button_spacing * 3,
                    width=button_width,
                    height=button_height,
                    text="재입대하기",
                    callback=self._on_prestige,
                )
            )

    def _load_dev_profile_image(self) -> pygame.Surface | None:
        """Load developer profile image from assets"""
        try:
            image_path = IMAGES_DIR / DEVELOPER_PROFILE_IMAGE
            if image_path.exists():
                img = pygame.image.load(str(image_path)).convert_alpha()
                return img
        except Exception:
            pass
        return None

    def _on_start_game(self) -> None:
        """Start game callback — goes through loading screen"""
        from fall_in.core.game_manager import GameManager
        from fall_in.scenes.game_loading_scene import GameLoadingScene

        game = GameManager()
        # Capture current screen so title stays visible behind the closing door
        prev_screen = game.screen.copy() if game.screen else None
        game.change_scene(GameLoadingScene(prev_screen=prev_screen))

    def _on_tutorial(self) -> None:
        """Tutorial callback - opens tutorial information"""
        # TODO: Implement actual tutorial scene
        print("Tutorial clicked")

    def _on_dev_info(self) -> None:
        """Developer info callback - shows developer information popup"""
        self.show_dev_info = True

    # Session-level flag: cutscene shown only once per game launch
    _collection_cutscene_shown: bool = False

    def _on_collection(self) -> None:
        """Collection callback — show cutscene first time, then go direct."""
        from fall_in.core.game_manager import GameManager

        if not TitleScene._collection_cutscene_shown:
            TitleScene._collection_cutscene_shown = True
            from fall_in.scenes.collection_cutscene_scene import (
                CollectionCutsceneScene,
            )

            GameManager().change_scene(CollectionCutsceneScene())
        else:
            from fall_in.scenes.collection_loading_scene import (
                CollectionLoadingScene,
            )

            GameManager().change_scene(CollectionLoadingScene())

    def _on_settings(self) -> None:
        """Settings callback — toggle settings popup"""
        self._settings_popup.toggle()

    def _on_prestige(self) -> None:
        """Prestige/rebirth callback - goes to prestige confirmation scene"""
        from fall_in.core.game_manager import GameManager
        from fall_in.scenes.prestige_scene import PrestigeScene

        GameManager().change_scene(PrestigeScene())

    def handle_event(self, event: pygame.event.Event) -> None:
        """Handle pygame events"""
        # Player info popup consumes events when visible
        if self._player_info_popup.handle_event(event):
            return

        # Settings popup consumes events when visible
        if self._settings_popup.handle_event(event):
            return

        # Close dev info popup on any click outside
        if self.show_dev_info:
            if event.type == pygame.MOUSEBUTTONDOWN:
                self.show_dev_info = False
            return

        for button in self.buttons:
            button.handle_event(event)

        # Handle circular button clicks
        if event.type == pygame.MOUSEBUTTONDOWN:
            mouse_pos = pygame.mouse.get_pos()

            # Player profile icon (top-left)
            profile_dist = (
                (mouse_pos[0] - self.profile_btn_center[0]) ** 2
                + (mouse_pos[1] - self.profile_btn_center[1]) ** 2
            ) ** 0.5
            if profile_dist <= self.profile_btn_radius:
                self._player_info_popup.toggle()
                return

            # Intro replay button (🎬)
            intro_dist = (
                (mouse_pos[0] - self.intro_btn_center[0]) ** 2
                + (mouse_pos[1] - self.intro_btn_center[1]) ** 2
            ) ** 0.5
            if intro_dist <= self.circle_btn_radius:
                self._on_replay_intro()
                return

            # Tutorial button (?)
            tutorial_dist = (
                (mouse_pos[0] - self.tutorial_btn_center[0]) ** 2
                + (mouse_pos[1] - self.tutorial_btn_center[1]) ** 2
            ) ** 0.5
            if tutorial_dist <= self.circle_btn_radius:
                self._on_tutorial()
                return

            # Info button (i)
            info_dist = (
                (mouse_pos[0] - self.info_btn_center[0]) ** 2
                + (mouse_pos[1] - self.info_btn_center[1]) ** 2
            ) ** 0.5
            if info_dist <= self.circle_btn_radius:
                self._on_dev_info()
                return

        # F12 opens debug menu (if DEBUG_MODE is enabled)
        if event.type == pygame.KEYDOWN and event.key == pygame.K_F12:
            self._open_debug_menu()

    def _open_debug_menu(self) -> None:
        """Open debug menu if debug mode is enabled"""
        from fall_in.config import DEBUG_MODE

        if not DEBUG_MODE:
            return

        from fall_in.core.game_manager import GameManager
        from fall_in.scenes.title_debug_scene import DebugScene

        GameManager().change_scene(DebugScene())

    def update(self, dt: float) -> None:
        """Update scene state"""
        self._anim_timer += dt
        for button in self.buttons:
            button.update(dt)

    @staticmethod
    def _load_and_scale_bg() -> pygame.Surface | None:
        """Load and scale the title background to screen size."""
        try:
            path = IMAGES_DIR / "ui" / "backgrounds" / "title.png"
            if path.exists():
                img = pygame.image.load(str(path)).convert()
                return pygame.transform.smoothscale(img, (SCREEN_WIDTH, SCREEN_HEIGHT))
        except Exception:
            pass
        return None

    @staticmethod
    def _load_logo() -> pygame.Surface | None:
        """Load the game logo image."""
        try:
            path = IMAGES_DIR / "fall_in_logo.png"
            if path.exists():
                return pygame.image.load(str(path)).convert_alpha()
        except Exception:
            pass
        return None

    def render(self, screen: pygame.Surface) -> None:
        """Render scene to screen"""
        # Background image
        if self._bg_image:
            screen.blit(self._bg_image, (0, 0))

        # Breathing animation: subtle pulse scale (1.0 ~ 1.03)
        # pulse = 1.0 + 0.007 * math.sin(self._anim_timer * 2.0)
        pulse = 1.0  # no pulse for now...

        # Logo image
        logo_center_y = SCREEN_HEIGHT // 3 - 100
        if self._logo_image:
            logo_w = int(self._logo_image.get_width() * 0.45 * pulse)
            logo_h = int(self._logo_image.get_height() * 0.45 * pulse)
            scaled_logo = pygame.transform.smoothscale(
                self._logo_image, (logo_w, logo_h)
            )
            logo_rect = scaled_logo.get_rect(center=(SCREEN_WIDTH // 2, logo_center_y))
            screen.blit(scaled_logo, logo_rect)

        # Use Korean fonts from asset loader
        font_large = get_font(64)
        font_sub = get_font(32)
        font_tagline = get_font(20)

        # Title text (below logo)
        text_base_y = logo_center_y + 140

        # Main title — with white outline
        title_surf = font_large.render("헤쳐 모여!", True, AIR_FORCE_BLUE)
        title_rect = title_surf.get_rect(center=(SCREEN_WIDTH // 2, text_base_y))
        draw_outlined_text(
            screen,
            "헤쳐 모여!",
            font_large,
            title_rect.topleft,
            AIR_FORCE_BLUE,
            WHITE,
            outline_offset=3,
        )

        # Subtitle — with white outline
        sub_surf = font_sub.render("Fall In!", True, LIGHT_BLUE)
        sub_rect = sub_surf.get_rect(center=(SCREEN_WIDTH // 2, text_base_y + 60))
        draw_outlined_text(
            screen,
            "Fall In!",
            font_sub,
            sub_rect.topleft,
            LIGHT_BLUE,
            WHITE,
            outline_offset=2,
        )

        # Tagline — with white outline
        tag_surf = font_tagline.render(
            "준비 된 인원부터 각 분대로 헤쳐모여!", True, AIR_FORCE_BLUE
        )
        tag_rect = tag_surf.get_rect(center=(SCREEN_WIDTH // 2, text_base_y + 100))
        draw_outlined_text(
            screen,
            "준비 된 인원부터 각 분대로 헤쳐모여!",
            font_tagline,
            tag_rect.topleft,
            AIR_FORCE_BLUE,
            WHITE,
            outline_offset=2,
        )

        # Draw buttons
        for button in self.buttons:
            button.render(screen)

        # Draw player profile icon (top left)
        self._draw_profile_button(screen)

        # Draw prestige indicator (if any)
        self._draw_prestige_indicator(screen)

        # Draw circular buttons (top right) - tutorial (?) and info (i)
        self._draw_circle_buttons(screen)

        # Draw developer info popup if visible
        if self.show_dev_info:
            self._draw_dev_info_popup(screen)

        # Draw settings popup (modal overlay)
        self._settings_popup.render(screen)

        # Build version string in bottom-left corner
        from fall_in import __version__

        ver_font = get_font(12)
        ver_text = ver_font.render(f"v{__version__}", True, (120, 120, 130))
        screen.blit(ver_text, (10, SCREEN_HEIGHT - ver_text.get_height() - 6))

        # Draw player info popup (always last — modal overlay)
        self._player_info_popup.render(screen)

    def _draw_profile_button(self, screen: pygame.Surface) -> None:
        """Draw player profile icon button in the top left corner."""
        center = self.profile_btn_center
        radius = self.profile_btn_radius
        # Black background circle (prevents UI bleed-through)
        pygame.draw.circle(screen, (0, 0, 0), center, radius)

        # Draw portrait photo (player_portrait_unknown as default)
        if "player_portrait_unknown" in self._ui_images:
            avatar_size = radius * 2
            portrait_img = pygame.transform.smoothscale(
                self._ui_images["player_portrait_unknown"],
                (avatar_size, avatar_size),
            )
            # Circular mask
            mask = pygame.Surface((avatar_size, avatar_size), pygame.SRCALPHA)
            pygame.draw.circle(
                mask,
                (255, 255, 255, 255),
                (radius, radius),
                radius,
            )
            portrait_img.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MIN)
            screen.blit(portrait_img, (center[0] - radius, center[1] - radius))
        else:
            pygame.draw.circle(screen, (80, 100, 130), center, radius)
            icon_font = get_font(20)
            icon_text = icon_font.render("👤", True, WHITE)
            screen.blit(icon_text, icon_text.get_rect(center=center))

        # Draw border frame (player_avatar is the border asset)
        if "player_avatar" in self._ui_images:
            frame_size = radius * 2 + 6
            frame_img = pygame.transform.smoothscale(
                self._ui_images["player_avatar"], (frame_size, frame_size)
            )
            screen.blit(
                frame_img,
                (center[0] - frame_size // 2, center[1] - frame_size // 2),
            )
        else:
            pygame.draw.circle(screen, AIR_FORCE_BLUE, center, radius, 2)

    def _draw_prestige_indicator(self, screen: pygame.Surface) -> None:
        """Draw prestige count indicator"""
        from fall_in.core.prestige_manager import PrestigeManager

        prestige = PrestigeManager()
        count = prestige.get_prestige_count()

        if count <= 0:
            return

        # Draw at top center
        font = get_font(16, "bold")
        prestige_text = font.render(f"Prestige x{count}", True, (200, 50, 200))
        rect = prestige_text.get_rect(center=(SCREEN_WIDTH // 2, 30))
        screen.blit(prestige_text, rect)

    def _draw_circle_buttons(self, screen: pygame.Surface) -> None:
        """Draw intro, tutorial, and info icon buttons in the top-right corner."""
        mouse_pos = pygame.mouse.get_pos()
        r = self.circle_btn_radius
        size = r * 2  # 36×36

        def _draw_icon_btn(center: tuple, key: str, fallback: str) -> None:
            if key in self._ui_images:
                icon = pygame.transform.smoothscale(self._ui_images[key], (size, size))
                screen.blit(icon, (center[0] - r, center[1] - r))
            else:
                # Fallback: filled circle + text
                dist = (
                    (mouse_pos[0] - center[0]) ** 2 + (mouse_pos[1] - center[1]) ** 2
                ) ** 0.5
                bg_color = (160, 170, 190) if dist <= r else (200, 200, 200)
                pygame.draw.circle(screen, bg_color, center, r)
                pygame.draw.circle(screen, AIR_FORCE_BLUE, center, r, 2)
                fb_font = get_font(16, "bold")
                fb_surf = fb_font.render(fallback, True, AIR_FORCE_BLUE)
                screen.blit(fb_surf, fb_surf.get_rect(center=center))

        _draw_icon_btn(self.intro_btn_center, "icon_replay", "🎬")
        _draw_icon_btn(self.tutorial_btn_center, "icon_tutorial", "?")
        _draw_icon_btn(self.info_btn_center, "icon_info", "i")

    def _on_replay_intro(self) -> None:
        """Replay intro cutscene"""
        from fall_in.core.game_manager import GameManager
        from fall_in.scenes.intro_cutscene_scene import IntroCutsceneScene

        GameManager().change_scene(IntroCutsceneScene())

    def _draw_dev_info_popup(self, screen: pygame.Surface) -> None:
        """Draw developer information popup"""
        # Semi-transparent overlay
        overlay = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 150))
        screen.blit(overlay, (0, 0))

        # Popup box
        popup_width, popup_height = 400, 280
        popup_x = (SCREEN_WIDTH - popup_width) // 2
        popup_y = (SCREEN_HEIGHT - popup_height) // 2
        popup_rect = pygame.Rect(popup_x, popup_y, popup_width, popup_height)

        # Draw popup background
        if "popup_dev_info" in self._ui_images:
            popup_bg = pygame.transform.smoothscale(
                self._ui_images["popup_dev_info"],
                (popup_width, popup_height),
            )
            screen.blit(popup_bg, popup_rect.topleft)
        else:
            pygame.draw.rect(screen, (255, 255, 255), popup_rect, border_radius=12)
            pygame.draw.rect(screen, AIR_FORCE_BLUE, popup_rect, 3, border_radius=12)

        # Title
        title_font = get_font(24, "bold")
        title_text = title_font.render("개발자 정보", True, AIR_FORCE_BLUE)
        title_rect = title_text.get_rect(center=(SCREEN_WIDTH // 2, popup_y + 35))
        screen.blit(title_text, title_rect)

        # Developer profile picture (circular)
        profile_center = (SCREEN_WIDTH // 2, popup_y + 95)
        profile_radius = 35

        if self.dev_profile_image:
            # Create circular mask and apply to profile image
            mask_surface = pygame.Surface(
                (profile_radius * 2, profile_radius * 2), pygame.SRCALPHA
            )
            pygame.draw.circle(
                mask_surface,
                (255, 255, 255, 255),
                (profile_radius, profile_radius),
                profile_radius,
            )

            # Scale image to fit in circle
            scaled_img = pygame.transform.smoothscale(
                self.dev_profile_image, (profile_radius * 2, profile_radius * 2)
            )

            # Apply mask
            scaled_img.blit(mask_surface, (0, 0), special_flags=pygame.BLEND_RGBA_MIN)

            # Draw the circular image
            img_rect = scaled_img.get_rect(center=profile_center)
            screen.blit(scaled_img, img_rect)

            # Draw border
            pygame.draw.circle(
                screen, AIR_FORCE_BLUE, profile_center, profile_radius, 2
            )
        else:
            # Fallback to placeholder
            pygame.draw.circle(screen, (220, 220, 220), profile_center, profile_radius)
            pygame.draw.circle(
                screen, AIR_FORCE_BLUE, profile_center, profile_radius, 2
            )
            profile_font = get_font(28)
            profile_icon = profile_font.render("ㅎ", True, (100, 100, 100))
            profile_icon_rect = profile_icon.get_rect(center=profile_center)
            screen.blit(profile_icon, profile_icon_rect)

        # Developer info text
        info_font = get_font(16)
        y_offset = popup_y + 145
        line_height = 26

        # Name
        name_text = info_font.render(f"이름: {DEVELOPER_NAME}", True, (60, 60, 60))
        name_rect = name_text.get_rect(center=(SCREEN_WIDTH // 2, y_offset))
        screen.blit(name_text, name_rect)

        # Nickname
        y_offset += line_height
        nick_text = info_font.render(
            f"닉네임: {DEVELOPER_NICKNAME}", True, (60, 60, 60)
        )
        nick_rect = nick_text.get_rect(center=(SCREEN_WIDTH // 2, y_offset))
        screen.blit(nick_text, nick_rect)

        # GitHub
        y_offset += line_height
        github_text = info_font.render(
            f"GitHub: {DEVELOPER_GITHUB}", True, (30, 100, 200)
        )
        github_rect = github_text.get_rect(center=(SCREEN_WIDTH // 2, y_offset))
        screen.blit(github_text, github_rect)

        # Military affiliation
        y_offset += line_height
        military_font = get_font(13)
        military_text = military_font.render(DEVELOPER_MILITARY, True, (80, 80, 80))
        military_rect = military_text.get_rect(center=(SCREEN_WIDTH // 2, y_offset))
        screen.blit(military_text, military_rect)

        # Close hint
        hint_font = get_font(12)
        hint_text = hint_font.render("(클릭하여 닫기)", True, (150, 150, 150))
        hint_rect = hint_text.get_rect(
            center=(SCREEN_WIDTH // 2, popup_y + popup_height - 20)
        )
        screen.blit(hint_text, hint_rect)
