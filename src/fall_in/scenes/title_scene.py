"""
Title Scene - Game start screen
"""

import pygame

from fall_in.scenes.base_scene import Scene
from fall_in.ui.button import Button
from fall_in.utils.asset_loader import get_font
from fall_in.config import SCREEN_WIDTH, SCREEN_HEIGHT, AIR_FORCE_BLUE, LIGHT_BLUE


class TitleScene(Scene):
    """
    Title screen with game logo and menu buttons.
    """

    def __init__(self):
        super().__init__()
        self.buttons: list[Button] = []
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

        # Tutorial button
        self.buttons.append(
            Button(
                x=button_x,
                y=button_start_y + button_spacing,
                width=button_width,
                height=button_height,
                text="튜토리얼",
                callback=self._on_tutorial,
            )
        )

        # Collection button
        self.buttons.append(
            Button(
                x=button_x,
                y=button_start_y + button_spacing * 2,
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
                y=button_start_y + button_spacing * 3,
                width=button_width,
                height=button_height,
                text="설정",
                callback=self._on_settings,
            )
        )

    def _on_start_game(self) -> None:
        """Start game callback"""
        from fall_in.core.game_manager import GameManager, GameState
        from fall_in.scenes.game_scene import GameScene

        game = GameManager()
        game.state = GameState.PLAYING
        game.change_scene(GameScene())

    def _on_tutorial(self) -> None:
        """Tutorial callback"""
        # TODO: Implement tutorial scene
        print("Tutorial clicked")

    def _on_collection(self) -> None:
        """Collection callback - open recruitment scene"""
        from fall_in.core.game_manager import GameManager, GameState
        from fall_in.scenes.recruitment_scene import RecruitmentScene

        game = GameManager()
        game.state = GameState.COLLECTION
        game.change_scene(RecruitmentScene())

    def _on_settings(self) -> None:
        """Settings callback"""
        # TODO: Implement settings scene
        print("Settings clicked")

    def handle_event(self, event: pygame.event.Event) -> None:
        """Handle pygame events"""
        for button in self.buttons:
            button.handle_event(event)

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
