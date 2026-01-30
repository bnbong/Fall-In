"""
Game Scene - Main gameplay screen with isometric board
Integrated with actual game rules and AI players
"""
import pygame
from enum import Enum, auto
from typing import Optional

from fall_in.scenes.base_scene import Scene
from fall_in.utils.asset_loader import get_font
from fall_in.core.card import Card
from fall_in.core.board import Board
from fall_in.core.player import Player, PlayerType, create_players
from fall_in.core.rules import GameRules, RoundPhase, TurnResult
from fall_in.ai.ai_player import AIPlayer, create_ai_players
from fall_in.config import (
    SCREEN_WIDTH, SCREEN_HEIGHT,
    AIR_FORCE_BLUE, WHITE, LIGHT_BLUE, SAND_BEIGE,
    DANGER_SAFE, DANGER_CAUTION, DANGER_WARNING, DANGER_DANGER, DANGER_CRITICAL,
    NUM_ROWS, MAX_CARDS_PER_ROW, NUM_PLAYERS, CARDS_PER_PLAYER,
    ISO_TILE_WIDTH, ISO_TILE_HEIGHT,
    BOARD_OFFSET_X, BOARD_OFFSET_Y, GAME_OVER_SCORE,
    Difficulty
)


class GamePhase(Enum):
    """UI game phase"""
    STARTING = auto()      # Round starting animation
    SELECTING = auto()     # Player selecting card
    AI_THINKING = auto()   # AI players selecting
    REVEALING = auto()     # Cards being revealed
    PLACING = auto()       # Cards being placed
    ROW_SELECT = auto()    # Player must select row
    ROUND_END = auto()     # Round ended
    GAME_OVER = auto()     # Game over


class GameScene(Scene):
    """
    Main game scene with isometric 4x6 board.
    Integrated with game rules for actual gameplay.
    """
    
    def __init__(self, difficulty: str = Difficulty.NORMAL, rules: Optional[GameRules] = None):
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
        
        # Turn log for display
        self.turn_log: list[TurnResult] = []
        
        # Animation state
        self.phase_timer = 0.0
        self.message = ""
        self.message_timer = 0.0
        
        # Start round
        self._start_new_round()
    
    def _start_new_round(self) -> None:
        """Start a new round"""
        self.rules.start_new_round()
        self.phase = GamePhase.SELECTING
        self.turn_log.clear()
        self.message = f"라운드 {self.rules.round_state.round_number} 시작!"
        self.message_timer = 2.0
    
    def _cart_to_iso(self, x: int, y: int) -> tuple[int, int]:
        """Convert cartesian coordinates to isometric (horizontally flipped)"""
        iso_x = BOARD_OFFSET_X + (y - x) * (ISO_TILE_WIDTH // 2)
        iso_y = BOARD_OFFSET_Y + (x + y) * (ISO_TILE_HEIGHT // 2)
        return iso_x, iso_y
    
    def _get_danger_color(self, score: int) -> tuple[int, int, int]:
        """Get color based on danger score"""
        if score < 20:
            return DANGER_SAFE
        elif score < 35:
            return DANGER_CAUTION
        elif score < 50:
            return DANGER_WARNING
        elif score < 60:
            return DANGER_DANGER
        else:
            return DANGER_CRITICAL
    
    def _draw_isometric_tile(
        self, 
        screen: pygame.Surface, 
        x: int, 
        y: int, 
        color: tuple,
        border_color: tuple = AIR_FORCE_BLUE,
        card: Optional[Card] = None
    ) -> None:
        """Draw a single isometric tile with optional card"""
        iso_x, iso_y = self._cart_to_iso(x, y)
        
        # Diamond points
        points = [
            (iso_x, iso_y - ISO_TILE_HEIGHT // 2),
            (iso_x + ISO_TILE_WIDTH // 2, iso_y),
            (iso_x, iso_y + ISO_TILE_HEIGHT // 2),
            (iso_x - ISO_TILE_WIDTH // 2, iso_y),
        ]
        
        pygame.draw.polygon(screen, color, points)
        pygame.draw.polygon(screen, border_color, points, width=2)
        
        # Draw card number if present
        if card:
            font = get_font(14)
            text = font.render(str(card.number), True, AIR_FORCE_BLUE)
            text_rect = text.get_rect(center=(iso_x, iso_y))
            screen.blit(text, text_rect)
    
    def _draw_board(self, screen: pygame.Surface) -> None:
        """Draw the isometric game board (bottom-left ascending)"""
        board = self.rules.board
        
        # Draw rows: row 0 at bottom-left, row 3 at top-right
        # Columns: col 0 at left (bottom), growing towards right (top)
        for row_idx in range(NUM_ROWS):
            row = board.rows[row_idx]
            
            for col in range(MAX_CARDS_PER_ROW + 1):
                visual_col = MAX_CARDS_PER_ROW - col
                
                if col < len(row):
                    card = row[col]
                    danger = card.danger
                    if danger <= 2:
                        color = DANGER_SAFE
                    elif danger <= 4:
                        color = DANGER_WARNING
                    else:
                        color = DANGER_DANGER
                    color = tuple(min(255, c + 60) for c in color)
                    self._draw_isometric_tile(screen, visual_col, row_idx, color, card=card)
                else:
                    color = (235, 225, 210)
                    self._draw_isometric_tile(screen, visual_col, row_idx, color)
    
    def _draw_ui(self, screen: pygame.Surface) -> None:
        """Draw UI elements"""
        font = get_font(22)
        small_font = get_font(16)
        mini_font = get_font(12)
        
        # Round indicator
        round_text = font.render(f"라운드 {self.rules.round_state.round_number}", True, AIR_FORCE_BLUE)
        screen.blit(round_text, (20, 20))
        
        # Player order display
        order_y = 55
        order_text = small_font.render("순서:", True, AIR_FORCE_BLUE)
        screen.blit(order_text, (20, order_y))
        
        for i, player in enumerate(self.rules.player_order):
            order_idx_text = mini_font.render(
                f"{i+1}.{player.name[:2]}", 
                True, 
                WHITE if player == self.human_player else AIR_FORCE_BLUE
            )
            bg_color = AIR_FORCE_BLUE if player == self.human_player else LIGHT_BLUE
            order_rect = pygame.Rect(75 + i * 55, order_y - 2, 50, 20)
            pygame.draw.rect(screen, bg_color, order_rect, border_radius=3)
            screen.blit(order_idx_text, (80 + i * 55, order_y))
        
        # Human player info box
        player_rect = pygame.Rect(20, 85, 160, 120)
        pygame.draw.rect(screen, AIR_FORCE_BLUE, player_rect, border_radius=10)
        pygame.draw.rect(screen, WHITE, player_rect, width=2, border_radius=10)
        
        player_name = small_font.render(self.human_player.name, True, WHITE)
        screen.blit(player_name, (player_rect.x + 10, player_rect.y + 8))
        
        # Committed score (previous rounds)
        committed = self.rules.get_player_committed_score(self.human_player)
        committed_text = mini_font.render(f"누적 위험도: {committed}", True, WHITE)
        screen.blit(committed_text, (player_rect.x + 10, player_rect.y + 32))
        
        # Cards taken this round
        cards_taken = self.rules.get_player_round_penalty_count(self.human_player)
        cards_text = mini_font.render(f"이번 라운드 벌칙: {cards_taken}장", True, WHITE)
        screen.blit(cards_text, (player_rect.x + 10, player_rect.y + 52))
        
        # Commander message
        msg = self._get_commander_message()
        msg_text = mini_font.render(msg, True, WHITE)
        screen.blit(msg_text, (player_rect.x + 10, player_rect.y + 80))
        
        # AI players (right side)
        for i, player in enumerate(self.players[1:]):
            ai_rect = pygame.Rect(SCREEN_WIDTH - 140, 20 + i * 80, 120, 70)
            bg_color = DANGER_DANGER if player.is_eliminated else LIGHT_BLUE
            pygame.draw.rect(screen, bg_color, ai_rect, border_radius=8)
            pygame.draw.rect(screen, AIR_FORCE_BLUE, ai_rect, width=2, border_radius=8)
            
            order_pos = self.rules.get_player_order_position(player)
            ai_name = small_font.render(f"{order_pos}.{player.name}", True, WHITE)
            screen.blit(ai_name, (ai_rect.x + 8, ai_rect.y + 6))
            
            # AI committed score
            ai_committed = self.rules.get_player_committed_score(player)
            ai_score = mini_font.render(f"위험도: {ai_committed}", True, WHITE)
            screen.blit(ai_score, (ai_rect.x + 8, ai_rect.y + 28))
            
            # Cards this round
            ai_cards = self.rules.get_player_round_penalty_count(player)
            ai_cards_text = mini_font.render(f"벌칙: {ai_cards}장", True, WHITE)
            screen.blit(ai_cards_text, (ai_rect.x + 8, ai_rect.y + 48))
        
        # Turn log (bottom left)
        if self.turn_log:
            log_y = SCREEN_HEIGHT - 150
            log_title = small_font.render("이번 턴:", True, AIR_FORCE_BLUE)
            screen.blit(log_title, (20, log_y))
            
            for i, result in enumerate(self.turn_log[-4:]):  # Show last 4
                log_entry = mini_font.render(
                    f"{result.placement_order}. {result.player.name[:4]} → #{result.card.number}",
                    True, AIR_FORCE_BLUE
                )
                screen.blit(log_entry, (25, log_y + 20 + i * 16))
        
        # Game message
        if self.message and self.message_timer > 0:
            msg_surface = font.render(self.message, True, AIR_FORCE_BLUE)
            msg_rect = msg_surface.get_rect(center=(SCREEN_WIDTH // 2, SCREEN_HEIGHT // 2 - 50))
            bg_rect = msg_rect.inflate(20, 10)
            pygame.draw.rect(screen, WHITE, bg_rect, border_radius=5)
            pygame.draw.rect(screen, AIR_FORCE_BLUE, bg_rect, width=1, border_radius=5)
            screen.blit(msg_surface, msg_rect)
        
        # Phase indicator
        phase_text = small_font.render(f"[{self._get_phase_text()}]", True, AIR_FORCE_BLUE)
        screen.blit(phase_text, (SCREEN_WIDTH - 120, SCREEN_HEIGHT - 20))
    
    def _get_commander_message(self) -> str:
        """Get commander message based on player's danger score"""
        committed = self.rules.get_player_committed_score(self.human_player)
        
        if committed < 20:
            return "순조롭군!"
        elif committed < 35:
            return "조심해라..."
        elif committed < 50:
            return "정신차려!"
        elif committed < 60:
            return "집무실로 와!"
        else:
            return "진급 포기냐?"
    
    def _get_phase_text(self) -> str:
        """Get current phase description"""
        phase_texts = {
            GamePhase.STARTING: "라운드 시작",
            GamePhase.SELECTING: "카드 선택",
            GamePhase.AI_THINKING: "AI 선택 중",
            GamePhase.REVEALING: "카드 공개",
            GamePhase.PLACING: "카드 배치",
            GamePhase.ROW_SELECT: "열 선택",
            GamePhase.ROUND_END: "라운드 종료",
            GamePhase.GAME_OVER: "게임 종료",
        }
        return phase_texts.get(self.phase, "")
    
    def _draw_hand(self, screen: pygame.Surface) -> None:
        """Draw player's hand cards at the bottom"""
        hand = self.human_player.hand
        if not hand:
            return
        
        card_width = 70
        card_height = 100
        spacing = 8
        total_width = len(hand) * (card_width + spacing) - spacing
        start_x = SCREEN_WIDTH // 2 - total_width // 2
        y = SCREEN_HEIGHT - card_height - 25
        
        font = get_font(16)
        small_font = get_font(12)
        
        for i, card in enumerate(hand):
            x = start_x + i * (card_width + spacing)
            
            if self.dragging and i == self.selected_card_index:
                continue
            
            mouse_pos = pygame.mouse.get_pos()
            card_rect = pygame.Rect(x, y, card_width, card_height)
            is_hovered = card_rect.collidepoint(mouse_pos)
            is_selected = (i == self.selected_card_index)
            
            draw_y = y - 20 if (is_hovered or is_selected) else y
            
            # Card background
            bg_color = (220, 220, 220) if is_selected else (200, 200, 200)
            pygame.draw.rect(screen, bg_color, (x, draw_y, card_width, card_height), border_radius=8)
            border_width = 3 if is_selected else 2
            pygame.draw.rect(screen, AIR_FORCE_BLUE, (x, draw_y, card_width, card_height), width=border_width, border_radius=8)
            
            # Card number
            num_text = font.render(f"#{card.number}", True, AIR_FORCE_BLUE)
            screen.blit(num_text, (x + 8, draw_y + 8))
            
            # Danger indicator
            if card.danger <= 2:
                danger_color = DANGER_SAFE
            elif card.danger <= 4:
                danger_color = DANGER_WARNING
            else:
                danger_color = DANGER_DANGER
            
            pygame.draw.circle(screen, danger_color, (x + card_width - 12, draw_y + 12), 8)
            danger_text = small_font.render(str(card.danger), True, WHITE)
            screen.blit(danger_text, (x + card_width - 16, draw_y + 7))
            
            # Soldier placeholder
            soldier_rect = pygame.Rect(x + 8, draw_y + 35, card_width - 16, 45)
            pygame.draw.rect(screen, LIGHT_BLUE, soldier_rect, border_radius=4)
    
    def handle_event(self, event: pygame.event.Event) -> None:
        """Handle pygame events"""
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                from fall_in.core.game_manager import GameManager
                from fall_in.scenes.title_scene import TitleScene
                GameManager().change_scene(TitleScene())
            elif event.key == pygame.K_SPACE:
                if self.phase == GamePhase.SELECTING and self.selected_card_index is not None:
                    self._confirm_card_selection()
        
        if self.phase == GamePhase.SELECTING:
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                self._handle_card_click(event.pos)
            elif event.type == pygame.MOUSEMOTION and self.dragging:
                self.drag_pos = event.pos
            elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
                if self.dragging:
                    self.dragging = False
    
    def _handle_card_click(self, pos: tuple[int, int]) -> None:
        """Handle clicking on a card in hand"""
        hand = self.human_player.hand
        if not hand:
            return
        
        card_width = 70
        card_height = 100
        spacing = 8
        total_width = len(hand) * (card_width + spacing) - spacing
        start_x = SCREEN_WIDTH // 2 - total_width // 2
        y = SCREEN_HEIGHT - card_height - 25
        
        for i in range(len(hand)):
            x = start_x + i * (card_width + spacing)
            card_rect = pygame.Rect(x, y - 20, card_width, card_height + 20)
            
            if card_rect.collidepoint(pos):
                if self.selected_card_index == i:
                    self._confirm_card_selection()
                else:
                    self.selected_card_index = i
                break
    
    def _confirm_card_selection(self) -> None:
        """Confirm card selection and proceed to AI phase"""
        if self.selected_card_index is None:
            return
        
        card = self.human_player.hand[self.selected_card_index]
        self.human_player.select_card(card)
        self.phase = GamePhase.AI_THINKING
        self.phase_timer = 0.5
        self.message = "AI가 카드를 선택 중..."
        self.message_timer = 0.5
    
    def _ai_select_cards(self) -> None:
        """Have all AI players select cards"""
        for ai in self.ai_controllers:
            if not ai.player.is_eliminated:
                ai.select_card(self.rules.board)
        
        self.phase = GamePhase.PLACING
        self.phase_timer = 0.3
    
    def _execute_turn(self) -> None:
        """Execute the turn - place all selected cards"""
        results = self.rules.execute_turn()
        self.turn_log = results
        
        # Display results
        penalties = [r for r in results if r.result.penalty_score > 0]
        if penalties:
            names = [r.player.name for r in penalties]
            self.message = f"벌점: {', '.join(names)}"
        else:
            self.message = "카드 배치 완료!"
        self.message_timer = 1.5
        
        # Check for round end
        if self.rules.is_round_over():
            self.phase = GamePhase.ROUND_END
            self.phase_timer = 1.0
            self.message = "라운드 종료! 잠시 후 정산..."
        else:
            self.selected_card_index = None
            self.phase = GamePhase.SELECTING
    
    def _go_to_result_scene(self) -> None:
        """Navigate to ResultScene for round settlement"""
        from fall_in.core.game_manager import GameManager
        from fall_in.scenes.result_scene import ResultScene
        
        result_scene = ResultScene(self.rules, self.players)
        GameManager().change_scene(result_scene)
    
    def update(self, dt: float) -> None:
        """Update scene state"""
        # Update timers
        if self.message_timer > 0:
            self.message_timer -= dt
        
        if self.phase_timer > 0:
            self.phase_timer -= dt
            return
        
        # Phase transitions
        if self.phase == GamePhase.AI_THINKING:
            self._ai_select_cards()
        elif self.phase == GamePhase.PLACING:
            self._execute_turn()
        elif self.phase == GamePhase.ROUND_END:
            self._go_to_result_scene()
    
    def render(self, screen: pygame.Surface) -> None:
        """Render scene to screen"""
        self._draw_board(screen)
        self._draw_ui(screen)
        self._draw_hand(screen)
        
        # Instructions at bottom
        if self.phase == GamePhase.SELECTING:
            font = get_font(14)
            hint = font.render("카드를 클릭하여 선택, 다시 클릭 또는 [SPACE]로 확정", True, AIR_FORCE_BLUE)
            screen.blit(hint, (SCREEN_WIDTH // 2 - hint.get_width() // 2, SCREEN_HEIGHT - 18))
