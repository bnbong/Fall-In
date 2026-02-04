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

# =============================================================================
# Isometric Settings - Adjusted to fit background sandy area
# =============================================================================
ISO_TILE_WIDTH = 135
ISO_TILE_HEIGHT = 58
BOARD_OFFSET_X = SCREEN_WIDTH // 2 + 50  # Center on sandy area
BOARD_OFFSET_Y = 260
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
BATTALION_PORTRAIT_CENTER_Y = 0.28  # Upper portion of card
BATTALION_PORTRAIT_RADIUS_RATIO = 0.35  # Relative to card width
BATTALION_NUMBER_CIRCLE_X = 0.5  # Centered
BATTALION_NUMBER_CIRCLE_Y = 0.055  # Near top


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
