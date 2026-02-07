"""
Game configuration constants for 헤쳐 모여! (Fall In!)
"""

from pathlib import Path

# =============================================================================
# Display Settings
# =============================================================================
SCREEN_WIDTH = 1280
SCREEN_HEIGHT = 720
FPS = 60
GAME_TITLE = "헤쳐 모여! (Fall In!)"

# Data directory for persistent storage
DATA_DIR = Path(__file__).parent.parent.parent / "data"

# =============================================================================
# Colors
# =============================================================================
# Primary colors
AIR_FORCE_BLUE = (30, 58, 95)  # #1E3A5F - 공군 블루
LIGHT_BLUE = (70, 130, 180)  # #4682B4
SAND_BEIGE = (245, 235, 220)  # #F5EBDC - 배경색

# Danger level colors
DANGER_SAFE = (46, 204, 113)  # 안전 - 초록
DANGER_CAUTION = (241, 196, 15)  # 주의 - 노랑
DANGER_WARNING = (230, 126, 34)  # 경고 - 주황
DANGER_DANGER = (231, 76, 60)  # 위험 - 빨강
DANGER_CRITICAL = (142, 68, 173)  # 극한 - 보라

# UI colors
WHITE = (255, 255, 255)
BLACK = (0, 0, 0)
GRAY = (128, 128, 128)
DARK_GRAY = (64, 64, 64)

# Default elements colors
DEALING_CARD_COLOR = (192, 192, 192)  # Silver
DEALING_CARD_BORDER_COLOR = (128, 128, 128)  # Dark silver/gray

# =============================================================================
# Game Rules (젝스님트 based)
# =============================================================================
NUM_PLAYERS = 4  # 총 플레이어 수 (1 human + 3 AI)
CARDS_PER_PLAYER = 10  # 손패 카드 수
TOTAL_CARDS = 104  # 총 카드(병사) 수
MAX_CARDS_PER_ROW = 5  # 열당 최대 카드 수
NUM_ROWS = 4  # 게임판 열 수
GAME_OVER_SCORE = 66  # 탈락 점수

# Danger levels for cards
MIN_DANGER = 1
MAX_DANGER = 7


# =============================================================================
# Asset Paths
# =============================================================================
def _find_project_root() -> Path:
    """Find the project root directory containing assets folder."""
    # Try from the config file location (development mode)
    config_dir = Path(__file__).parent  # fall_in/

    # Go up to find project root with assets folder
    for parent in [config_dir.parent.parent, config_dir.parent, config_dir]:
        if (parent / "assets").exists():
            return parent

    # Fallback: try current working directory
    cwd = Path.cwd()
    if (cwd / "assets").exists():
        return cwd

    # Last resort: use the src parent
    return config_dir.parent.parent


PROJECT_ROOT = _find_project_root()
ASSETS_DIR = PROJECT_ROOT / "assets"
IMAGES_DIR = ASSETS_DIR / "images"
SOUNDS_DIR = ASSETS_DIR / "sounds"
FONTS_DIR = ASSETS_DIR / "fonts"
DATA_DIR = PROJECT_ROOT / "data"

# =============================================================================
# Audio Settings
# =============================================================================
DEFAULT_BGM_VOLUME = 0.5
DEFAULT_SFX_VOLUME = 0.7

# =============================================================================
# Animation Settings
# =============================================================================
CARD_ANIMATION_SPEED = 8  # 카드 이동 속도
SOLDIER_BOUNCE_SPEED = 0.1  # 병사 바운스 속도
SOLDIER_BOUNCE_HEIGHT = 5  # 병사 바운스 높이

# Card dealing animation
CARD_DEAL_DELAY = 0.1  # Delay between each card deal (seconds)
CARD_DEAL_DURATION = 0.4  # Duration of card fly animation (seconds)

# Phase timing
AI_THINKING_DURATION = 0.5  # AI thinking phase duration (seconds)
PLACEMENT_PAUSE_DURATION = 0.5  # Pause after each placement (seconds)
PENALTY_ANIMATION_DURATION = 0.4  # Base duration for penalty card animation

# Timer thresholds for color changes
TIMER_WARNING_THRESHOLD = 15  # Seconds remaining when timer turns yellow
TIMER_DANGER_THRESHOLD = 5  # Seconds remaining when timer turns red

# =============================================================================
# Isometric Settings - Adjusted to fit background sandy area
# =============================================================================
ISO_TILE_WIDTH = 126.44
ISO_TILE_HEIGHT = 58.77
BOARD_OFFSET_X = SCREEN_WIDTH // 2 + 50
BOARD_OFFSET_Y = 248
ROW_SPACING = 9


# =============================================================================
# AI Difficulty Settings
# =============================================================================
class Difficulty:
    EASY = "easy"
    NORMAL = "normal"
    HARD = "hard"


# =============================================================================
# Card Hand Layout Settings (Fan display at bottom of screen)
# =============================================================================
HAND_FAN_SPREAD = 60  # Total fan angle in degrees
HAND_CARD_OVERLAP = 40  # Horizontal overlap between cards (pixels)
HAND_Y_OFFSET = 50  # Push cards down from bottom (pixels)
HAND_HOVER_POP_DISTANCE = 50  # Pixels card rises on hover
HAND_HOVER_SCALE = 1.20  # Scale factor on hover (1.15 = 15% larger)


# =============================================================================
# Battalion Card Settings
# =============================================================================
BATTALION_CARD_WIDTH = 150
BATTALION_CARD_HEIGHT = 253
BATTALION_PORTRAIT_CENTER_X = 0.5  # Centered horizontally
BATTALION_PORTRAIT_CENTER_Y = 0.30  # Upper portion of card
BATTALION_PORTRAIT_RADIUS_RATIO = 0.30  # Relative to card width
BATTALION_NUMBER_CIRCLE_X = 0.5  # Centered
BATTALION_NUMBER_CIRCLE_Y = 0.055  # Near top

# Text display on card (relative positions for 4 lines)
BATTALION_NAME_Y = 0.55  # Name position (below portrait)
BATTALION_RANK_Y = 0.665  # Rank position
BATTALION_UNIT_Y = 0.76  # Unit position
BATTALION_DANGER_Y = 0.855  # Danger level position
BATTALION_TEXT_FONT_SIZE = 10  # Font size for card text
BATTALION_UNKNOWN_TEXT = "알 수 없음"  # Text for uninterviewed soldiers
BATTALION_DETAIL_TEXT_X = (
    0.65  # X position for rank/unit/danger (0.0=left, 0.5=center, 1.0=right)
)

# Danger level text labels
BATTALION_DANGER_LABELS = {
    1: "안전",
    2: "관심",
    3: "주의",
    5: "매우위험",
    7: "매우위험",
}


# =============================================================================
# Commander Character Settings
# =============================================================================
COMMANDER_X = 100  # X position (left side of screen)
COMMANDER_Y = 520  # Y position (pushed down so lower body is cut off)
COMMANDER_WIDTH = 250
COMMANDER_HEIGHT = 680


# =============================================================================
# Game Board Settings
# =============================================================================
ROW_OFFSETS = [
    (0, 0),  # Row 0 - base position
    (23, 0),  # Row 1 - slight right shift
    (46, 0),  # Row 2 - more right shift
    (69, 0),  # Row 3 - most right shift
]

BARRACKS_X = 1050
BARRACKS_Y = 200


# =============================================================================
# UI Settings
# =============================================================================
UI_TOP_BAR_Y = 15
UI_TOP_BAR_HEIGHT = 70

UI_ELEMENT_PLAYER_ORDER_X = 55
UI_ELEMENT_DANGER_GAUGE_WIDTH = 100
UI_ELEMENT_DANGER_GAUGE_HEIGHT = 20

ICON_HANGER_X = 150

TURN_LOG_X = 10
TURN_LOG_Y = 80
TURN_LOG_WIDTH = 170


# =============================================================================
# Soldier Figure Sprite Settings
# =============================================================================
FIGURE_SPRITE_FRAMES = 4  # Number of animation frames in sprite sheet
FIGURE_DISPLAY_WIDTH = 60  # Display width on screen
FIGURE_DISPLAY_HEIGHT = 63  # Display height on screen
FIGURE_DROP_DURATION = 0.3  # Drop animation duration in seconds
FIGURE_DROP_HEIGHT = 150  # Height from which figure drops

# Figure position offset on tile (fine-tuning)
FIGURE_OFFSET_X = 0  # Horizontal offset (positive = right)
FIGURE_OFFSET_Y = 20  # Vertical offset (positive = down)

# Dust particle count by danger level
DUST_PARTICLE_COUNT = {
    1: 5,
    2: 5,
    3: 15,
    4: 15,
    5: 30,
    6: 30,
    7: 60,
}

# Screen shake intensity by danger level (pixels)
SCREEN_SHAKE_INTENSITY = {
    1: 0,
    2: 0,
    3: 2,
    4: 4,
    5: 6,
    6: 9,
    7: 15,
}
SCREEN_SHAKE_DURATION = 0.2  # seconds


# =============================================================================
# Recruitment Scene Settings
# =============================================================================
# Button positions (relative to screen) - adjusted to match background elements
RECRUIT_BTN_ROSTER_X = 550  # Notepad button X (center over notepad)
RECRUIT_BTN_ROSTER_Y = 570  # Notepad button Y (slightly above table edge)
RECRUIT_BTN_INTERVIEW_X = 790  # Microphone button X (near microphone)
RECRUIT_BTN_INTERVIEW_Y = 630  # Microphone button Y (above table)
RECRUIT_BTN_WIDTH = 120
RECRUIT_BTN_HEIGHT = 40

# Animation durations
RECRUIT_ANNOUNCE_DURATION = 2.0  # Speaker announcement duration
RECRUIT_WALK_IN_DURATION = 1.0  # Soldier walk-in duration
RECRUIT_REVEAL_DURATION = 0.3  # Flash reveal duration
RECRUIT_FADE_OUT_DURATION = 0.5  # Fade out duration

# Interview display positions - adjusted for table perspective
RECRUIT_PORTRAIT_X = 380  # Soldier portrait X (left side, behind table)
RECRUIT_PORTRAIT_SIZE = 300  # Portrait display size

# Soldier bust image specifications (for assets/images/characters/soldiers/)
# Recommended size: 600x700px PNG with transparent background
# Character should be centered horizontally, bottom edge at waist level
RECRUIT_BUST_WIDTH = 400  # Display width for bust image
RECRUIT_BUST_HEIGHT = 480  # Display height for bust image
RECRUIT_BUST_ANCHOR_Y = 465  # Y position where bust bottom is anchored (table edge)
RECRUIT_BUST_START_SCALE = 0.3  # Initial scale for zoom animation
RECRUIT_BUST_END_SCALE = 1.0  # Final scale for zoom animation
RECRUIT_SPEECH_BUBBLE_X = 100  # Speech bubble X (right of portrait)
RECRUIT_SPEECH_BUBBLE_Y = 180  # Speech bubble Y (above portrait)
RECRUIT_NOTES_X = 900  # Notes panel X (right side of screen)
RECRUIT_NOTES_Y = 120  # Notes panel Y (upper right)
RECRUIT_NOTES_WIDTH = 360  # Notes panel width
RECRUIT_NOTES_HEIGHT = 320  # Notes panel height
RECRUIT_CARD_X = 60  # Battalion card X (left lower)
RECRUIT_CARD_Y = 350  # Battalion card Y (below portrait)

# Roster view
RECRUIT_ROSTER_COLS = 5  # Icons per row
RECRUIT_ROSTER_ICON_SIZE = 70  # Icon size
RECRUIT_ROSTER_ICON_GAP = 15  # Gap between icons
RECRUIT_ROSTER_SCROLL_SPEED = 30  # Pixels per scroll

# =============================================================================
# Interview Cost Settings
# =============================================================================
INTERVIEW_COST = 50  # 면담 1회 비용 (원)

# =============================================================================
# Frozen Food Settings (BX 냉동식품)
# =============================================================================
FROZEN_FOOD_MIN_COUNT = 1  # 최소 표시 개수
FROZEN_FOOD_MAX_COUNT = 5  # 최대 표시 개수
FROZEN_FOOD_SIZE = 80  # 아이콘 크기
FROZEN_FOOD_GAP = 15  # 아이템 간 간격
FROZEN_FOOD_TABLE_Y = 530  # 테이블 위 Y 위치
FROZEN_FOOD_TABLE_X = 500  # 테이블 중앙 X 위치
