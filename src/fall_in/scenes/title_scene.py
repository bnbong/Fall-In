"""
Title Scene - Game start screen

# TODO : add title scene graphics. (before title, add story line explanation scene)
"""

import pygame

from fall_in.scenes.base_scene import Scene
from fall_in.ui.button import Button
from fall_in.utils.asset_loader import get_font
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
)


class TitleScene(Scene):
    """
    Title screen with game logo and menu buttons.
    """

    def __init__(self):
        super().__init__()
        self.buttons: list[Button] = []
        self.show_dev_info = False  # Developer info popup state

        # Circular button positions (top-right corner)
        self.tutorial_btn_center = (SCREEN_WIDTH - 100, 40)
        self.info_btn_center = (SCREEN_WIDTH - 50, 40)
        self.circle_btn_radius = 18

        # Load developer profile image
        self.dev_profile_image = self._load_dev_profile_image()

        # UI images — pull from pre-loaded manifest cache
        from fall_in.utils.asset_manifest import AssetManifest

        self._ui_images: dict[str, pygame.Surface] = {}
        for category in ("panels", "icons"):
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

    def _on_collection(self) -> None:
        """Collection callback — goes through loading screen"""
        from fall_in.core.game_manager import GameManager
        from fall_in.scenes.collection_loading_scene import CollectionLoadingScene

        game = GameManager()
        game.change_scene(CollectionLoadingScene())

    def _on_settings(self) -> None:
        """Settings callback"""
        # TODO: Implement settings scene
        print("Settings clicked")

    def _on_prestige(self) -> None:
        """Prestige/rebirth callback - goes to prestige confirmation scene"""
        from fall_in.core.game_manager import GameManager
        from fall_in.scenes.prestige_scene import PrestigeScene

        GameManager().change_scene(PrestigeScene())

    def handle_event(self, event: pygame.event.Event) -> None:
        """Handle pygame events"""
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
        from fall_in.scenes.debug_scene import DebugScene

        GameManager().change_scene(DebugScene())

    def update(self, dt: float) -> None:
        """Update scene state"""
        for button in self.buttons:
            button.update(dt)

    def render(self, screen: pygame.Surface) -> None:
        """Render scene to screen"""
        # Use Korean fonts from asset loader
        font_large = get_font(64)
        font_sub = get_font(32)
        font_tagline = get_font(20)

        # Main title
        title_text = font_large.render("헤쳐 모여!", True, AIR_FORCE_BLUE)
        title_rect = title_text.get_rect(center=(SCREEN_WIDTH // 2, SCREEN_HEIGHT // 3))
        screen.blit(title_text, title_rect)

        # Subtitle
        subtitle_text = font_sub.render("Fall In!", True, LIGHT_BLUE)
        subtitle_rect = subtitle_text.get_rect(
            center=(SCREEN_WIDTH // 2, SCREEN_HEIGHT // 3 + 60)
        )
        screen.blit(subtitle_text, subtitle_rect)

        # Tagline
        tagline_text = font_tagline.render(
            "준비 된 인원부터 각 분대로 헤쳐모여!", True, AIR_FORCE_BLUE
        )
        tagline_rect = tagline_text.get_rect(
            center=(SCREEN_WIDTH // 2, SCREEN_HEIGHT // 3 + 100)
        )
        screen.blit(tagline_text, tagline_rect)

        # Draw buttons
        for button in self.buttons:
            button.render(screen)

        # Draw medals (top left)
        self._draw_medals(screen)

        # Draw prestige indicator (if any)
        self._draw_prestige_indicator(screen)

        # Draw circular buttons (top right) - tutorial (?) and info (i)
        self._draw_circle_buttons(screen)

        # Draw developer info popup if visible
        if self.show_dev_info:
            self._draw_dev_info_popup(screen)

    def _draw_medals(self, screen: pygame.Surface) -> None:
        """Draw earned medals in the top left corner"""
        from fall_in.core.medal_manager import MedalManager

        medals = MedalManager().get_player_medals()
        if not medals:
            return

        small_font = get_font(14)
        x, y = 20, 20

        # Title
        title = small_font.render("🏅 획득 훈장", True, AIR_FORCE_BLUE)
        screen.blit(title, (x, y))

        # Medal icons (placeholder - simple text for now)
        y += 25
        medal_font = get_font(12)
        for i, medal_id in enumerate(medals[:5]):  # Show max 5 medals
            info = MedalManager().get_medal_info(medal_id)
            if info:
                medal_text = medal_font.render(f"• {info['name']}", True, (80, 80, 80))
                screen.blit(medal_text, (x, y + i * 18))

        if len(medals) > 5:
            more_text = medal_font.render(
                f"  +{len(medals) - 5} more", True, (120, 120, 120)
            )
            screen.blit(more_text, (x, y + 5 * 18))

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
        """Draw circular tutorial (?) and info (i) buttons in the top right corner"""
        # Tutorial button (?)
        pygame.draw.circle(
            screen, (200, 200, 200), self.tutorial_btn_center, self.circle_btn_radius
        )
        pygame.draw.circle(
            screen, AIR_FORCE_BLUE, self.tutorial_btn_center, self.circle_btn_radius, 2
        )
        tutorial_font = get_font(18, "bold")
        tutorial_text = tutorial_font.render("?", True, AIR_FORCE_BLUE)
        tutorial_rect = tutorial_text.get_rect(center=self.tutorial_btn_center)
        screen.blit(tutorial_text, tutorial_rect)

        # Info button (i)
        pygame.draw.circle(
            screen, (200, 200, 200), self.info_btn_center, self.circle_btn_radius
        )
        pygame.draw.circle(
            screen, AIR_FORCE_BLUE, self.info_btn_center, self.circle_btn_radius, 2
        )
        info_font = get_font(18, "bold")
        info_text = info_font.render("i", True, AIR_FORCE_BLUE)
        info_rect = info_text.get_rect(center=self.info_btn_center)
        screen.blit(info_text, info_rect)

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
