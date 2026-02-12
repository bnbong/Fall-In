"""
Game configuration constants for 헤쳐 모여! (Fall In!)

Centralizes all tunable game parameters, layout values, and magic numbers
so they can be adjusted from a single location.
"""

from pathlib import Path


# =============================================================================
# Developer Settings
# =============================================================================
DEVELOPER_NAME = "이준혁"
DEVELOPER_NICKNAME = "bnbong"
DEVELOPER_GITHUB = "https://github.com/bnbong"
DEVELOPER_MILITARY = "대한민국 공군 병 825기 30010 전자계산 특기"
DEVELOPER_PROFILE_IMAGE = "developer_profile.JPG"

# =============================================================================
# Display Settings
# =============================================================================
SCREEN_WIDTH = 1280
SCREEN_HEIGHT = 720
FPS = 60
GAME_TITLE = "헤쳐 모여! (Fall In!)"

# =============================================================================
# Debug Mode
# =============================================================================
DEBUG_MODE = True  # Set to False for production builds

# =============================================================================
# Colors
# =============================================================================
# Primary colors
AIR_FORCE_BLUE = (30, 58, 95)  # #1E3A5F
LIGHT_BLUE = (70, 130, 180)  # #4682B4
SAND_BEIGE = (245, 235, 220)  # #F5EBDC - background color

# Danger level colors (cumulative score gauge)
DANGER_SAFE = (46, 204, 113)  # Green
DANGER_CAUTION = (241, 196, 15)  # Yellow
DANGER_WARNING = (230, 126, 34)  # Orange
DANGER_DANGER = (231, 76, 60)  # Red
DANGER_CRITICAL = (142, 68, 173)  # Purple

# UI colors
WHITE = (255, 255, 255)
BLACK = (0, 0, 0)
GRAY = (128, 128, 128)
DARK_GRAY = (64, 64, 64)

# Default card dealing animation colors
DEALING_CARD_COLOR = (192, 192, 192)  # Silver
DEALING_CARD_BORDER_COLOR = (128, 128, 128)  # Dark silver/gray

# Card selection/hover border colors
CARD_SELECTED_BORDER_COLOR = (100, 200, 100)
CARD_HOVER_BORDER_COLOR = (255, 255, 150)
CARD_TEXT_COLOR = (50, 50, 50)

# Top bar UI
TOP_BAR_BG_COLOR = (30, 60, 90, 200)
TOP_BAR_OUTLINE_COLOR = (10, 30, 50)

# Coup ending title color
COUP_TITLE_COLOR = (200, 50, 200)

# Card danger level colors (for number circles and recruitment scene)
DANGER_LEVEL_COLORS = {
    1: (100, 150, 100),  # Green
    2: (200, 180, 50),  # Yellow
    3: (230, 150, 50),  # Orange
    5: (200, 50, 50),  # Red
    7: (100, 50, 150),  # Purple
}

# =============================================================================
# Game Rules (6 Nimmt! based)
# =============================================================================
NUM_PLAYERS = 4  # Total players (1 human + 3 AI)
CARDS_PER_PLAYER = 10  # Cards per hand
TOTAL_CARDS = 104  # Total cards (soldiers)
MAX_CARDS_PER_ROW = 5  # Max cards per board row
NUM_ROWS = 4  # Number of board rows
GAME_OVER_SCORE = 66  # Elimination threshold

# Danger levels for cards
MIN_DANGER = 1
MAX_DANGER = 7

# Danger score thresholds (cumulative) for UI gauge and level labels
DANGER_SCORE_THRESHOLDS = {
    "safe": 0,
    "caution": 20,
    "warning": 35,
    "danger": 50,
    "critical": 60,
    "eliminated": 66,
}

# =============================================================================
# Currency Reward Settings
# =============================================================================
REWARD_VICTORY_BASE = 100
REWARD_VICTORY_PER_ROUND = 10
REWARD_DEFEAT_BASE = 30
REWARD_DEFEAT_PER_ROUND = 5

# =============================================================================
# Turn Timer
# =============================================================================
TURN_TIMEOUT_SECONDS = 30.0


# =============================================================================
# Asset Paths
# =============================================================================
def _find_project_root() -> Path:
    """Find the project root directory containing the assets folder."""
    config_dir = Path(__file__).parent  # fall_in/

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
CARD_ANIMATION_SPEED = 8
SOLDIER_BOUNCE_SPEED = 0.1
SOLDIER_BOUNCE_HEIGHT = 5

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
HAND_HOVER_SCALE = 1.20  # Scale factor on hover (1.20 = 20% larger)


# =============================================================================
# Battalion Card Settings
# =============================================================================
NUMBER_CIRCLE_RADIUS = 14
NUMBER_CIRCLE_FONT_SIZE = 12

BATTALION_CARD_WIDTH = 150
BATTALION_CARD_HEIGHT = 253
BATTALION_PORTRAIT_CENTER_X = 0.5  # Centered horizontally
BATTALION_PORTRAIT_CENTER_Y = 0.30  # Upper portion of card
BATTALION_PORTRAIT_RADIUS_RATIO = 0.30  # Relative to card width
BATTALION_NUMBER_CIRCLE_X = 0.5  # Centered
BATTALION_NUMBER_CIRCLE_Y = 0.055  # Near top

# Text display on card (relative Y positions for 4 lines)
BATTALION_NAME_Y = 0.55  # Name position (below portrait)
BATTALION_RANK_Y = 0.665  # Rank position
BATTALION_UNIT_Y = 0.76  # Unit position
BATTALION_DANGER_Y = 0.855  # Danger level position
BATTALION_TEXT_FONT_SIZE = 10
BATTALION_UNKNOWN_TEXT = "알 수 없음"  # Text for uninterviewed soldiers
BATTALION_DETAIL_TEXT_X = (
    0.65  # X position for rank/unit/danger (0.0=left, 0.5=center, 1.0=right)
)

# Danger level text labels (Korean)
BATTALION_DANGER_LABELS = {
    1: "안전",
    2: "관심",
    3: "주의",
    5: "매우위험",
    7: "매우위험",
}

# Aura effect colors by danger threshold {min_danger: (r, g, b, alpha)}
CARD_AURA_COLORS = {
    3: (255, 165, 0, 100),  # Orange glow
    5: (255, 50, 50, 120),  # Red glow
    7: (100, 50, 150, 140),  # Dark purple glow
}

# Aura visual parameters
CARD_AURA_MARGIN = 35
CARD_AURA_NUM_FLAMES = 12
CARD_AURA_BASE_FLAME_SIZE = 15

# High-resolution scale factor for hover (assets are 2x size)
CARD_HR_SCALE = 2.0

# Card border rendering
CARD_SELECTED_BORDER_WIDTH = 4
CARD_HOVER_BORDER_WIDTH = 3
CARD_BORDER_RADIUS = 8


# =============================================================================
# Commander Character Settings
# =============================================================================
COMMANDER_X = 100  # X position (left side of screen)
COMMANDER_Y = 520  # Y position (lower body cut off)
COMMANDER_WIDTH = 250
COMMANDER_HEIGHT = 680
COMMANDER_SPEECH_BUBBLE_Y = 365

# Commander danger score thresholds for expression changes
COMMANDER_DANGER_THRESHOLDS = {
    0: "pleased",
    15: "neutral",
    30: "concerned",
    45: "angry",
    55: "furious",
}


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
# Soldier Figure - Body Type System
# =============================================================================
class BodyType:
    """
    Soldier body type categories affecting figure display size.
    Each body type corresponds to different sprite sheet dimensions
    and on-screen display sizes.
    """

    NORMAL = "normal"  # Standard body type (default, 960x252 sheets)
    SMALL = "small"  # Smaller/petite body type (TBD sprite sheets)
    LARGE = "large"  # Large/bulky body type (1020x252 sheets, e.g. danger 5)


# Display dimensions per body type: (width, height) in pixels
FIGURE_BODY_TYPE_DIMENSIONS = {
    BodyType.NORMAL: (90, 94),
    BodyType.SMALL: (75, 78),
    BodyType.LARGE: (134, 139),
}

# Y offset per body type for tile anchoring (larger figures need more offset)
FIGURE_BODY_TYPE_OFFSET_Y = {
    BodyType.NORMAL: 20,
    BodyType.SMALL: 16,
    BodyType.LARGE: 24,
}

# Shadow radius per body type
FIGURE_BODY_TYPE_SHADOW_RADIUS = {
    BodyType.NORMAL: 18,
    BodyType.SMALL: 14,
    BodyType.LARGE: 22,
}

# Default body type for mob sprites by danger level
FIGURE_DANGER_BODY_TYPE = {
    1: BodyType.NORMAL,
    2: BodyType.NORMAL,
    3: BodyType.NORMAL,
    5: BodyType.LARGE,
    7: BodyType.NORMAL,
}


# =============================================================================
# Soldier Figure Sprite Settings
# =============================================================================
FIGURE_SPRITE_FRAMES = 4  # Number of animation frames in sprite sheet
FIGURE_DISPLAY_WIDTH = 80  # Default display width (NORMAL body type)
FIGURE_DISPLAY_HEIGHT = 84  # Default display height (NORMAL body type)
FIGURE_DROP_DURATION = 0.3  # Drop animation duration in seconds
FIGURE_DROP_HEIGHT = 150  # Height from which figure drops

# Figure position offset on tile (fine-tuning)
FIGURE_OFFSET_X = 0  # Horizontal offset (positive = right)
FIGURE_OFFSET_Y = 20  # Vertical offset (positive = down, used as fallback)

# Figure rendering
FIGURE_SHADOW_RADIUS = 18  # Default shadow radius (NORMAL body type)
FIGURE_SHADOW_VISIBILITY_THRESHOLD = 40
FIGURE_NUMBER_FONT_SIZE = 14

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
SCREEN_SHAKE_PADDING = 30  # Extra background padding to prevent white edges


# =============================================================================
# Dust Particle Physics
# =============================================================================
DUST_GRAVITY = 150
DUST_SPEED_MIN = 30
DUST_SPEED_MAX = 80
DUST_UPWARD_MIN = -40
DUST_UPWARD_MAX = -80
DUST_LIFETIME_MIN = 0.3
DUST_LIFETIME_MAX = 0.6
DUST_SIZE_MIN = 2
DUST_SIZE_MAX = 5
DUST_SPAWN_SPREAD_X = 10
DUST_SPAWN_SPREAD_Y = 5


# =============================================================================
# Speech Bubble Settings
# =============================================================================
SPEECH_BUBBLE_APPEAR_DURATION = 0.3
SPEECH_BUBBLE_DEFAULT_VISIBLE_DURATION = 2.5
SPEECH_BUBBLE_DISAPPEAR_DURATION = 0.3
SPEECH_BUBBLE_FONT_SIZE = 14
SPEECH_BUBBLE_PADDING = 12
SPEECH_BUBBLE_TAIL_SIZE = 15


# =============================================================================
# Recruitment Scene Settings
# =============================================================================
# Button positions (relative to screen)
RECRUIT_BTN_ROSTER_X = 550
RECRUIT_BTN_ROSTER_Y = 570
RECRUIT_BTN_INTERVIEW_X = 790
RECRUIT_BTN_INTERVIEW_Y = 630
RECRUIT_BTN_WIDTH = 120
RECRUIT_BTN_HEIGHT = 40

# Animation durations
RECRUIT_ANNOUNCE_DURATION = 2.0
RECRUIT_WALK_IN_DURATION = 1.0
RECRUIT_REVEAL_DURATION = 0.3
RECRUIT_FADE_OUT_DURATION = 0.5

# Interview display positions
RECRUIT_PORTRAIT_X = 380
RECRUIT_PORTRAIT_SIZE = 300

# Soldier bust image specifications
RECRUIT_BUST_WIDTH = 400
RECRUIT_BUST_HEIGHT = 480
RECRUIT_BUST_ANCHOR_Y = 465
RECRUIT_BUST_START_SCALE = 0.3
RECRUIT_BUST_END_SCALE = 1.0
RECRUIT_SPEECH_BUBBLE_X = 100
RECRUIT_SPEECH_BUBBLE_Y = 180
RECRUIT_NOTES_X = 900
RECRUIT_NOTES_Y = 120
RECRUIT_NOTES_WIDTH = 360
RECRUIT_NOTES_HEIGHT = 320
RECRUIT_CARD_X = 60
RECRUIT_CARD_Y = 350

# Roster view
RECRUIT_ROSTER_COLS = 5
RECRUIT_ROSTER_ICON_SIZE = 70
RECRUIT_ROSTER_ICON_GAP = 15
RECRUIT_ROSTER_SCROLL_SPEED = 30

# Recruitment scene panel colors
RECRUIT_PANEL_BG = (245, 240, 230)  # Beige paper
RECRUIT_PANEL_BORDER = (100, 80, 60)  # Dark brown
RECRUIT_BTN_COLOR = (70, 90, 110)
RECRUIT_BTN_HOVER_COLOR = (90, 110, 130)

# =============================================================================
# Interview Cost Settings
# =============================================================================
INTERVIEW_COST = 50  # Cost per interview (currency)

# =============================================================================
# Frozen Food Settings (BX frozen food items)
# =============================================================================
FROZEN_FOOD_MIN_COUNT = 1
FROZEN_FOOD_MAX_COUNT = 5
FROZEN_FOOD_SIZE = 80
FROZEN_FOOD_GAP = 15
FROZEN_FOOD_TABLE_Y = 530
FROZEN_FOOD_TABLE_X = 500

# =============================================================================
# Smuggling Scene Card Layout
# =============================================================================
SMUGGLING_CARD_WIDTH = 100
SMUGGLING_CARD_HEIGHT = 168
SMUGGLING_CARD_SPACING_X = 20
SMUGGLING_CARD_SPACING_Y = 30
SMUGGLING_MAX_CARDS_PER_ROW = 8
SMUGGLING_SELECTED_LIFT = 20
SMUGGLING_HOVER_LIFT = 10
