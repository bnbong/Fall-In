"""
Fix sprite sheet splits for the 3 problematic sheets:
1. Banners - 4 separate items were merged into one
2. HUD - gauge bars were merged, sub-components need separation
3. Buttons - circle buttons and small hover were misdetected

Uses coordinate analysis data from the alpha channel to perform precise cuts.
"""

from pathlib import Path
from PIL import Image
import numpy as np


ASSETS_DIR = Path(__file__).parent.parent / "assets" / "images"
UI_DIR = ASSETS_DIR / "ui"


def crop_and_save(
    img: Image.Image,
    box: tuple[int, int, int, int],
    output_path: Path,
    padding: int = 2,
) -> None:
    """Crop a region from the image and save it."""
    left, top, right, bottom = box
    left = max(0, left - padding)
    top = max(0, top - padding)
    right = min(img.width, right + padding)
    bottom = min(img.height, bottom + padding)

    cropped = img.crop((left, top, right, bottom))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    cropped.save(str(output_path), "PNG")
    w, h = right - left, bottom - top
    print(f"  Saved: {output_path.name} ({w}x{h})")


def fix_banners():
    """Fix banners - split the 4 clear rows using exact coordinates."""
    print("\n=== Fixing: Banners ===")
    img = Image.open(ASSETS_DIR / "assets_banners.png").convert("RGBA")
    out_dir = UI_DIR / "banners"

    # Row coordinates from alpha analysis:
    regions = [
        ((327, 188, 1882, 646), "banner_victory"),
        ((327, 662, 1882, 1125), "banner_defeat"),
        ((296, 1137, 1913, 1547), "banner_coup"),
        ((965, 1576, 1244, 1843), "star_decoration"),
    ]

    for box, name in regions:
        crop_and_save(img, box, out_dir / f"{name}.png")


def fix_huds():
    """Fix HUD elements with exact coordinate extraction."""
    print("\n=== Fixing: HUDs ===")
    img = Image.open(ASSETS_DIR / "assets_huds.png").convert("RGBA")
    out_dir = UI_DIR / "hud"

    # Top bar
    crop_and_save(img, (69, 93, 2747, 294), out_dir / "hud_top_bar.png")

    # Left column (x=139-940): Gauge background + 5 gauge fills
    # Item 0: gauge_bg      (139,343)-(940,638)  = 801x295 (navy with gold outline)
    # Item 1: gauge_fill_safe     (139,681)-(940,819)  = 801x138 (green)
    # Item 2: gauge_fill_caution  (139,837)-(940,950)  = 801x113 (yellow)
    # Item 3: gauge_fill_warning  (139,967)-(940,1080) = 801x113 (orange)
    # Item 4: gauge_fill_danger   (139,1096)-(940,1210) = 801x114 (red)
    # Item 5: gauge_fill_critical (139,1227)-(940,1340) = 801x113 (purple)
    # Item 6: (extra fill if any) (139,1357)-(940,1470) = 801x113
    left_items = [
        ((139, 343, 940, 638), "gauge_bg"),
        ((139, 681, 940, 819), "gauge_fill_safe"),
        ((139, 837, 940, 950), "gauge_fill_caution"),
        ((139, 967, 940, 1080), "gauge_fill_warning"),
        ((139, 1096, 940, 1210), "gauge_fill_danger"),
        ((139, 1227, 940, 1340), "gauge_fill_critical"),
    ]

    for box, name in left_items:
        crop_and_save(img, box, out_dir / f"{name}.png")

    # Check if item 6 exists and is different
    cropped_6 = img.crop((139, 1357, 940, 1470))
    alpha_6 = np.array(cropped_6)[:, :, 3]
    if np.any(alpha_6 > 10):
        crop_and_save(img, (139, 1357, 940, 1470), out_dir / "gauge_fill_extra.png")

    # Middle column (x=1073-1744):
    # Item 0: (1073,378)-(1744,635) = 671x257 -> hud_round_indicator
    # Item 1: (1073,792)-(1744,1044) = 671x252 -> hud_hangar_icon
    mid_items = [
        ((1073, 378, 1744, 635), "hud_round_indicator"),
        ((1073, 792, 1744, 1044), "hud_hangar_icon"),
    ]

    for box, name in mid_items:
        crop_and_save(img, box, out_dir / f"{name}.png")

    # Right column (x=1786-2704):
    # Item 0: (1786,379)-(2704,733) = 918x354 -> icon_player_avatar
    # Item 1: (1786,779)-(2704,1139) = 918x360 -> icon_danger_warning
    # Item 2: (1786,1197)-(2704,1451) = 918x254 -> panel_ai_player / timer_frame
    right_items = [
        ((1786, 379, 2704, 733), "icon_player_avatar"),
        ((1786, 779, 2704, 1139), "icon_danger_warning"),
        ((1786, 1197, 2704, 1451), "panel_ai_player"),
    ]

    for box, name in right_items:
        crop_and_save(img, box, out_dir / f"{name}.png")


def fix_buttons():
    """Fix button extraction with exact coordinates."""
    print("\n=== Fixing: Buttons ===")
    img = Image.open(ASSETS_DIR / "assets_btns.png").convert("RGBA")
    out_dir = UI_DIR / "buttons"

    # Row 1 Left (x=235-1458): Large buttons with shadows
    # Button + shadow pairs:
    #   Normal: (235,136)-(1458,488) + shadow (235,504)-(1458,543) -> merge to (235,136)-(1458,543)
    #   Pressed: (235,611)-(1458,964) + shadow (235,979)-(1458,1019) -> merge to (235,611)-(1458,1019)
    # BUT we actually want btn_large_hover, not btn_large_pressed here.
    # Looking at the original sprite sheet: Row 1 left = Normal, Row 1 right = Small variants
    # Row 2 left = hover version of large, Row 2 items = circle buttons

    # Let's merge each button with its shadow
    large_items = [
        ((235, 136, 1458, 543), "btn_large_normal"),  # normal + shadow
        ((235, 611, 1458, 1019), "btn_large_pressed"),  # pressed + shadow (or hover)
    ]

    small_items = [
        ((1753, 141, 2469, 434), "btn_small_normal"),  # normal + shadow
        ((1753, 455, 2469, 748), "btn_small_hover"),  # hover + shadow
        ((1753, 768, 2469, 1061), "btn_small_pressed"),  # pressed + shadow
    ]

    # Row 2:
    # (236,1077)-(1458,1396) = large hover btn
    # (1776,1113)-(2053,1391) = circle normal
    # (2177,1113)-(2456,1391) = circle hover
    row2_items = [
        ((236, 1077, 1458, 1396), "btn_large_hover"),
        ((1776, 1113, 2053, 1391), "btn_circle_normal"),
        ((2177, 1113, 2456, 1391), "btn_circle_hover"),
    ]

    for box, name in large_items + small_items + row2_items:
        crop_and_save(img, box, out_dir / f"{name}.png")


def main():
    print("=" * 60)
    print("Fall In! Sprite Sheet Fix Script")
    print("=" * 60)

    fix_banners()
    fix_huds()
    fix_buttons()

    print("\n" + "=" * 60)
    print("All fixes applied! Check assets/images/ui/ for results.")
    print("=" * 60)


if __name__ == "__main__":
    main()
