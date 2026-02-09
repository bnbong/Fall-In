"""
Smuggling Scene - Soldier smuggling selection screen after round end.

Allows the player to select collected soldiers from penalty cards
to smuggle them out. Smuggled soldiers count toward the coup ending condition.

# TODO : add smuggling scene graphics.
"""

import pygame
from typing import Optional

from fall_in.scenes.base_scene import Scene
from fall_in.ui.button import Button
from fall_in.utils.asset_loader import get_font
from fall_in.core.smuggling_manager import SmugglingManager
from fall_in.core.rules import GameRules
from fall_in.core.card import Card
from fall_in.entities.battalion_card import BattalionCard
from fall_in.config import (
    SCREEN_WIDTH,
    SCREEN_HEIGHT,
    WHITE,
    LIGHT_BLUE,
    DANGER_SAFE,
    DANGER_WARNING,
    AIR_FORCE_BLUE,
    SMUGGLING_CARD_WIDTH,
    SMUGGLING_CARD_HEIGHT,
    SMUGGLING_CARD_SPACING_X,
    SMUGGLING_CARD_SPACING_Y,
    SMUGGLING_MAX_CARDS_PER_ROW,
    SMUGGLING_SELECTED_LIFT,
    SMUGGLING_HOVER_LIFT,
)


class SmugglingScene(Scene):
    """
    Smuggling selection screen shown after each round.
    Players choose up to N penalty soldiers to smuggle, where N depends
    on collection progress and prestige level. Only collected (interviewed)
    soldiers can be smuggled.
    """

    def __init__(
        self,
        rules: GameRules,
        penalty_cards: list[Card],
        round_penalty: int = 0,
        is_game_over: bool = False,  # Flag indicating if this is the last smuggling before game over
    ):
        super().__init__()
        self.rules = rules
        self.penalty_cards = penalty_cards
        self.round_penalty = round_penalty
        self.is_game_over = is_game_over

        # Smuggling manager
        self.smuggling = SmugglingManager()
        self.smuggling.update_max_count()
        self.smuggling.start_new_selection()  # Clear any previous selection

        # UI state
        self.hovered_card: Optional[Card] = None
        self.buttons: list[Button] = []

        self._setup_ui()

    def _setup_ui(self) -> None:
        """Setup UI elements."""
        button_width = 180
        button_height = 45
        button_y = SCREEN_HEIGHT - 80

        # Skip button
        self.buttons.append(
            Button(
                x=SCREEN_WIDTH // 2 - button_width - 20,
                y=button_y,
                width=button_width,
                height=button_height,
                text="건너뛰기",
                callback=self._on_skip,
            )
        )

        # Confirm button
        self.confirm_button = Button(
            x=SCREEN_WIDTH // 2 + 20,
            y=button_y,
            width=button_width,
            height=button_height,
            text="빼돌리기",
            callback=self._on_confirm,
        )
        self.buttons.append(self.confirm_button)

    def _on_skip(self) -> None:
        """Skip smuggling and continue to next round."""
        self.smuggling.cancel_selection()
        self._continue_game()

    def _on_confirm(self) -> None:
        """Confirm smuggling selection."""
        self.smuggling.confirm_selection()
        self._continue_game()

    def _continue_game(self) -> None:
        """Continue to next round or go to game over."""
        from fall_in.core.game_manager import GameManager

        if self.is_game_over:
            # Go to game over scene
            from fall_in.scenes.game_over_scene import GameOverScene

            game_over_scene = GameOverScene(
                winner=self.rules.winner,
                players=self.rules.players,
                round_number=self.rules.round_state.round_number,
            )
            GameManager().change_scene(game_over_scene)
        else:
            # Continue with next round
            from fall_in.scenes.game_scene import GameScene

            game_scene = GameScene(rules=self.rules)
            GameManager().change_scene(game_scene)

    def handle_event(self, event: pygame.event.Event) -> None:
        """Handle events."""
        for button in self.buttons:
            button.handle_event(event)

        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            self._handle_card_click(event.pos)

        elif event.type == pygame.MOUSEMOTION:
            self._handle_card_hover(event.pos)

        elif event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                self._on_skip()
            elif event.key == pygame.K_RETURN or event.key == pygame.K_SPACE:
                self._on_confirm()

    def _get_card_positions(self) -> list[tuple[int, int]]:
        """Calculate card positions with grid layout and row wrapping."""
        card_width = SMUGGLING_CARD_WIDTH
        card_height = SMUGGLING_CARD_HEIGHT
        card_spacing_x = SMUGGLING_CARD_SPACING_X
        card_spacing_y = SMUGGLING_CARD_SPACING_Y
        max_cards_per_row = SMUGGLING_MAX_CARDS_PER_ROW

        positions: list[tuple[int, int]] = []
        num_cards = len(self.penalty_cards)

        if num_cards == 0:
            return positions

        # Calculate number of rows needed
        num_rows = (num_cards + max_cards_per_row - 1) // max_cards_per_row

        # Total grid height
        total_height = num_rows * card_height + (num_rows - 1) * card_spacing_y
        start_y = (SCREEN_HEIGHT - total_height) // 2 + 30  # Offset for header

        for i in range(num_cards):
            row = i // max_cards_per_row
            col = i % max_cards_per_row

            # Cards in this row
            cards_in_row = min(max_cards_per_row, num_cards - row * max_cards_per_row)
            row_width = cards_in_row * card_width + (cards_in_row - 1) * card_spacing_x
            row_start_x = (SCREEN_WIDTH - row_width) // 2

            x = row_start_x + col * (card_width + card_spacing_x)
            y = start_y + row * (card_height + card_spacing_y)

            positions.append((x, y))

        return positions

    def _handle_card_click(self, pos: tuple[int, int]) -> None:
        """Handle clicking on a card."""
        card_width = SMUGGLING_CARD_WIDTH
        card_height = SMUGGLING_CARD_HEIGHT
        positions = self._get_card_positions()

        for i, card in enumerate(self.penalty_cards):
            if i >= len(positions):
                break
            x, y = positions[i]
            rect = pygame.Rect(x, y, card_width, card_height)

            if rect.collidepoint(pos):
                # Toggle selection if possible
                self.smuggling.select_soldier(card.number)
                break

    def _handle_card_hover(self, pos: tuple[int, int]) -> None:
        """Handle hovering over cards."""
        card_width = SMUGGLING_CARD_WIDTH
        card_height = SMUGGLING_CARD_HEIGHT
        positions = self._get_card_positions()

        self.hovered_card = None
        for i, card in enumerate(self.penalty_cards):
            if i >= len(positions):
                break
            x, y = positions[i]
            rect = pygame.Rect(x, y, card_width, card_height)

            if rect.collidepoint(pos):
                self.hovered_card = card
                break

    def update(self, dt: float) -> None:
        """Update scene."""
        for button in self.buttons:
            button.update(dt)

    def render(self, screen: pygame.Surface) -> None:
        """Render smuggling scene."""
        # Background
        screen.fill((40, 50, 70))

        title_font = get_font(32, "bold")
        font = get_font(20)
        small_font = get_font(16)

        # Title
        title_text = title_font.render("병사 빼돌리기", True, WHITE)
        title_rect = title_text.get_rect(center=(SCREEN_WIDTH // 2, 50))
        screen.blit(title_text, title_rect)

        # Subtitle / instructions
        max_count = self.smuggling.get_max_smuggle_count()
        remaining = self.smuggling.get_remaining_slots()
        selected_count = len(self.smuggling.get_current_selection())
        subtitle_text = font.render(
            f"빼돌릴 병사를 선택하세요. (선택: {selected_count}/{max_count})",
            True,
            LIGHT_BLUE,
        )
        subtitle_rect = subtitle_text.get_rect(center=(SCREEN_WIDTH // 2, 90))
        screen.blit(subtitle_text, subtitle_rect)

        # Current accumulated smuggled soldiers info
        smuggled = self.smuggling.get_smuggled_soldiers()
        if smuggled:
            smuggled_text = small_font.render(
                f"이번 게임에서 빼돌린 병사: {sorted(smuggled)}", True, DANGER_SAFE
            )
            screen.blit(smuggled_text, (50, 120))

        # Cards
        self._render_cards(screen)

        # Selection info
        current_selection = self.smuggling.get_current_selection()
        if current_selection:
            select_text = font.render(
                f"선택됨: {sorted(current_selection)}", True, DANGER_SAFE
            )
            select_rect = select_text.get_rect(
                center=(SCREEN_WIDTH // 2, SCREEN_HEIGHT - 140)
            )
            screen.blit(select_text, select_rect)

        # Hover info - show warning if can't select
        if self.hovered_card:
            is_collected = self.smuggling.is_soldier_collected(self.hovered_card.number)
            if not is_collected:
                hover_text = small_font.render(
                    "※ 면담하지 않은 병사는 빼돌릴 수 없습니다", True, DANGER_WARNING
                )
                hover_rect = hover_text.get_rect(
                    center=(SCREEN_WIDTH // 2, SCREEN_HEIGHT - 170)
                )
                screen.blit(hover_text, hover_rect)
            elif remaining == 0 and not self.smuggling.is_selected(
                self.hovered_card.number
            ):
                hover_text = small_font.render(
                    f"※ 최대 {max_count}명까지만 선택 가능합니다", True, DANGER_WARNING
                )
                hover_rect = hover_text.get_rect(
                    center=(SCREEN_WIDTH // 2, SCREEN_HEIGHT - 170)
                )
                screen.blit(hover_text, hover_rect)

        # Buttons
        for button in self.buttons:
            button.render(screen)

        # Hint
        hint_text = small_font.render(
            "[ESC] 건너뛰기 / [SPACE] 확인", True, AIR_FORCE_BLUE
        )
        hint_rect = hint_text.get_rect(center=(SCREEN_WIDTH // 2, SCREEN_HEIGHT - 30))
        screen.blit(hint_text, hint_rect)

    def _render_cards(self, screen: pygame.Surface) -> None:
        """Render penalty cards."""
        if not self.penalty_cards:
            no_cards_font = get_font(24)
            no_cards_text = no_cards_font.render(
                "이번 라운드에서 받은 벌점이 없습니다.", True, WHITE
            )
            no_cards_rect = no_cards_text.get_rect(
                center=(SCREEN_WIDTH // 2, SCREEN_HEIGHT // 2)
            )
            screen.blit(no_cards_text, no_cards_rect)
            return

        card_width = SMUGGLING_CARD_WIDTH
        card_height = SMUGGLING_CARD_HEIGHT
        positions = self._get_card_positions()

        for i, card in enumerate(self.penalty_cards):
            if i >= len(positions):
                break
            x, y = positions[i]

            # Determine card state
            is_selected = self.smuggling.is_selected(card.number)
            is_hovered = card == self.hovered_card
            is_collected = self.smuggling.is_soldier_collected(card.number)

            # Lift selected/hovered cards
            if is_selected:
                y -= SMUGGLING_SELECTED_LIFT
            elif is_hovered:
                y -= SMUGGLING_HOVER_LIFT

            # Render card using BattalionCard classmethod
            scale = card_width / BattalionCard.CARD_WIDTH
            BattalionCard.render(
                screen,
                card,
                x,
                y,
                is_interviewed=is_collected,
                is_selected=is_selected,
                is_hovered=is_hovered,
                scale=scale,
            )

            # Overlay for non-selectable cards (not collected)
            if not is_collected:
                overlay = pygame.Surface((card_width, card_height))
                overlay.fill((100, 100, 100))
                overlay.set_alpha(150)
                screen.blit(overlay, (x, y))

                # Lock icon or text
                lock_font = get_font(12)
                lock_text = lock_font.render("미수집", True, WHITE)
                lock_rect = lock_text.get_rect(
                    center=(x + card_width // 2, y + card_height // 2)
                )
                screen.blit(lock_text, lock_rect)

            # Selection indicator
            if is_selected:
                # Draw checkmark or highlight
                check_font = get_font(24)
                check_text = check_font.render("✓", True, DANGER_SAFE)
                check_rect = check_text.get_rect(center=(x + card_width // 2, y - 10))
                screen.blit(check_text, check_rect)
