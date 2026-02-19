"""
Sprite Sheet Splitter for 헤쳐 모여! (Fall In!) UI Assets

Splits 7 Nanobanana-generated sprite sheets into individual PNG files
and organizes them into the proper directory structure under assets/images/ui/.

Uses alpha-channel bounding box detection to find individual sprites,
then crops and saves each one with appropriate naming.
"""

from pathlib import Path
from PIL import Image
import numpy as np


ASSETS_DIR = Path(__file__).parent.parent / "assets" / "images"
UI_DIR = ASSETS_DIR / "ui"


def find_connected_components(
    alpha: np.ndarray, min_area: int = 500
) -> list[tuple[int, int, int, int]]:
    """
    Find bounding boxes of connected non-transparent regions.
    Uses a simple flood-fill approach on the alpha channel.

    Returns list of (left, top, right, bottom) bounding boxes.
    """
    h, w = alpha.shape
    visited = np.zeros_like(alpha, dtype=bool)
    components = []

    # Threshold: consider pixels with alpha > 10 as non-transparent
    mask = alpha > 10

    for y in range(h):
        for x in range(w):
            if mask[y, x] and not visited[y, x]:
                # BFS to find connected component
                queue = [(x, y)]
                visited[y, x] = True
                min_x, min_y = x, y
                max_x, max_y = x, y
                pixel_count = 0

                while queue:
                    cx, cy = queue.pop(0)
                    pixel_count += 1
                    min_x = min(min_x, cx)
                    min_y = min(min_y, cy)
                    max_x = max(max_x, cx)
                    max_y = max(max_y, cy)

                    # Check 4-connected neighbors
                    for dx, dy in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                        nx, ny = cx + dx, cy + dy
                        if (
                            0 <= nx < w
                            and 0 <= ny < h
                            and mask[ny, nx]
                            and not visited[ny, nx]
                        ):
                            visited[ny, nx] = True
                            queue.append((nx, ny))

                if pixel_count >= min_area:
                    components.append((min_x, min_y, max_x + 1, max_y + 1))

    return components


def merge_close_components(
    components: list[tuple[int, int, int, int]], gap_threshold: int = 15
) -> list[tuple[int, int, int, int]]:
    """Merge bounding boxes that are very close together (part of same sprite)."""
    if not components:
        return components

    merged = True
    while merged:
        merged = False
        new_components = []
        used = set()

        for i, box_a in enumerate(components):
            if i in used:
                continue

            current = list(box_a)
            for j, box_b in enumerate(components):
                if j <= i or j in used:
                    continue

                # Check if boxes overlap or are within gap_threshold
                if (
                    current[0] - gap_threshold <= box_b[2]
                    and current[2] + gap_threshold >= box_b[0]
                    and current[1] - gap_threshold <= box_b[3]
                    and current[3] + gap_threshold >= box_b[1]
                ):
                    # Merge
                    current[0] = min(current[0], box_b[0])
                    current[1] = min(current[1], box_b[1])
                    current[2] = max(current[2], box_b[2])
                    current[3] = max(current[3], box_b[3])
                    used.add(j)
                    merged = True

            new_components.append(tuple(current))

        components = new_components

    return components


def sort_components_grid(
    components: list[tuple[int, int, int, int]],
) -> list[tuple[int, int, int, int]]:
    """Sort components in reading order (top-to-bottom, left-to-right)."""
    if not components:
        return components

    # Group by approximate rows (within 50px = same row)
    rows: list[list[tuple[int, int, int, int]]] = []
    sorted_by_y = sorted(components, key=lambda b: b[1])

    current_row: list[tuple[int, int, int, int]] = [sorted_by_y[0]]
    current_row_y = sorted_by_y[0][1]

    for box in sorted_by_y[1:]:
        if abs(box[1] - current_row_y) < 80:
            current_row.append(box)
        else:
            rows.append(sorted(current_row, key=lambda b: b[0]))
            current_row = [box]
            current_row_y = box[1]

    rows.append(sorted(current_row, key=lambda b: b[0]))

    result = []
    for row in rows:
        result.extend(row)
    return result


def crop_and_save(
    img: Image.Image,
    box: tuple[int, int, int, int],
    output_path: Path,
    padding: int = 2,
) -> None:
    """Crop a region from the image and save it."""
    left, top, right, bottom = box
    # Add small padding
    left = max(0, left - padding)
    top = max(0, top - padding)
    right = min(img.width, right + padding)
    bottom = min(img.height, bottom + padding)

    cropped = img.crop((left, top, right, bottom))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    cropped.save(str(output_path), "PNG")
    print(f"  Saved: {output_path.name} ({right - left}x{bottom - top})")


def split_buttons(img_path: Path) -> None:
    """Split buttons sprite sheet."""
    print(f"\n=== Splitting: {img_path.name} ===")
    img = Image.open(img_path).convert("RGBA")
    alpha = np.array(img)[:, :, 3]

    components = find_connected_components(alpha, min_area=1000)
    components = merge_close_components(components, gap_threshold=20)
    components = sort_components_grid(components)

    out_dir = UI_DIR / "buttons"

    # Expected order based on the sprite sheet layout:
    # Row 1 (left): Large Normal | Row 1 (right): Small Normal
    # Row 2 (left): Large Hover  | Row 2 (right): Small Hover
    # Row 3 (left): Large Pressed| Row 3 (right): Small Pressed, Circle Normal, Circle Hover
    names = [
        "btn_large_normal",
        "btn_small_normal",
        "btn_large_hover",
        "btn_small_hover",
        "btn_large_pressed",
        "btn_small_pressed",
        "btn_circle_normal",
        "btn_circle_hover",
    ]

    print(f"  Found {len(components)} components, expected {len(names)}")
    for i, (box, name) in enumerate(zip(components, names)):
        crop_and_save(img, box, out_dir / f"{name}.png")


def split_huds(img_path: Path) -> None:
    """Split HUD elements sprite sheet."""
    print(f"\n=== Splitting: {img_path.name} ===")
    img = Image.open(img_path).convert("RGBA")
    alpha = np.array(img)[:, :, 3]

    components = find_connected_components(alpha, min_area=800)
    components = merge_close_components(components, gap_threshold=25)
    components = sort_components_grid(components)

    out_dir = UI_DIR / "hud"

    # Expected layout based on the image:
    # Row 1: Top bar (full width)
    # Row 2: Round indicator | Hangar icon | Player avatar frame
    # Rows 3-7: Gauge bg, gauge fills (safe, caution, warning, danger, critical)
    # Also: warning triangle, AI panel, phase indicator
    names = [
        "hud_top_bar",
        "hud_round_indicator",
        "hud_hangar_icon",
        "icon_player_avatar",
        "gauge_bg",
        "gauge_fill_safe",
        "icon_danger_warning",
        "gauge_fill_caution",
        "panel_ai_player",
        "gauge_fill_warning",
        "gauge_fill_danger",
        "panel_phase_indicator",
        "gauge_fill_critical",
    ]

    print(f"  Found {len(components)} components, expected {len(names)}")
    for i, (box, name) in enumerate(zip(components, names)):
        crop_and_save(img, box, out_dir / f"{name}.png")


def split_panels(img_path: Path) -> None:
    """Split panels sprite sheet."""
    print(f"\n=== Splitting: {img_path.name} ===")
    img = Image.open(img_path).convert("RGBA")
    alpha = np.array(img)[:, :, 3]

    components = find_connected_components(alpha, min_area=1500)
    components = merge_close_components(components, gap_threshold=20)
    components = sort_components_grid(components)

    out_dir = UI_DIR / "panels"

    # Expected layout:
    # Row 1: AI panel, Turn log panel, Message popup, (empty)
    # Row 2: Stats box, Rankings panel, Result table
    # Row 3: Notes panel, Soldier detail, Dev info popup, Currency info
    names = [
        "panel_ai_player",
        "panel_turn_log",
        "popup_message",
        "panel_stats_box",
        "panel_rankings",
        "panel_result_table",
        "panel_notes",
        "panel_soldier_detail",
        "popup_dev_info",
        "panel_currency_info_sm",
        "panel_currency_info",
    ]

    print(f"  Found {len(components)} components, expected {len(names)}")
    for i, (box, name) in enumerate(zip(components, names)):
        crop_and_save(img, box, out_dir / f"{name}.png")


def split_banners(img_path: Path) -> None:
    """Split banners sprite sheet."""
    print(f"\n=== Splitting: {img_path.name} ===")
    img = Image.open(img_path).convert("RGBA")
    alpha = np.array(img)[:, :, 3]

    components = find_connected_components(alpha, min_area=1000)
    components = merge_close_components(components, gap_threshold=30)
    components = sort_components_grid(components)

    out_dir = UI_DIR / "banners"

    # Expected: Victory, Defeat, Coup, Star decoration
    names = [
        "banner_victory",
        "banner_defeat",
        "banner_coup",
        "star_decoration",
    ]

    print(f"  Found {len(components)} components, expected {len(names)}")
    for i, (box, name) in enumerate(zip(components, names)):
        crop_and_save(img, box, out_dir / f"{name}.png")


def split_icons(img_path: Path) -> None:
    """Split icons and badges sprite sheet."""
    print(f"\n=== Splitting: {img_path.name} ===")
    img = Image.open(img_path).convert("RGBA")
    alpha = np.array(img)[:, :, 3]

    components = find_connected_components(alpha, min_area=300)
    components = merge_close_components(components, gap_threshold=15)
    components = sort_components_grid(components)

    out_dir = UI_DIR / "icons"

    # Expected layout:
    # Row 1: currency, medal, prestige, badge_eliminated, badge_survived
    # Row 2: badge_survived(2nd?), badge_danger, check, lock, unknown_soldier
    # Row 3: number_circle, scrollbar, toast_bg
    names = [
        "icon_currency",
        "icon_medal",
        "icon_prestige",
        "badge_eliminated",
        "badge_survived",
        "badge_survived_alt",
        "badge_danger",
        "icon_check",
        "icon_lock",
        "icon_unknown_soldier",
        "number_circle",
        "scrollbar_indicator",
        "toast_bg",
    ]

    print(f"  Found {len(components)} components, expected {len(names)}")
    for i, (box, name) in enumerate(zip(components, names)):
        crop_and_save(img, box, out_dir / f"{name}.png")

    # Also check for small star at bottom right
    if len(components) > len(names):
        for box in components[len(names) :]:
            w = box[2] - box[0]
            h = box[3] - box[1]
            print(f"  Extra component: {w}x{h} at ({box[0]},{box[1]})")


def split_chatbox_and_cards(img_path: Path) -> None:
    """Split speech bubbles and card frames sprite sheet."""
    print(f"\n=== Splitting: {img_path.name} ===")
    img = Image.open(img_path).convert("RGBA")
    alpha = np.array(img)[:, :, 3]

    components = find_connected_components(alpha, min_area=400)
    components = merge_close_components(components, gap_threshold=20)
    components = sort_components_grid(components)

    # Speech assets go to speech/, card assets to cards/
    speech_dir = UI_DIR / "speech"
    cards_dir = UI_DIR / "cards"

    # Expected layout:
    # Top-left: Speech bubble body | Top-right: Announcement bubble
    # Bottom-left: Tail left, Tail right | Bottom-right: Card back, Locked overlay
    names_and_dirs = [
        ("speech_bubble_body", speech_dir),
        ("speech_announcement", speech_dir),
        ("speech_bubble_tail_left", speech_dir),
        ("speech_bubble_tail_right", speech_dir),
        ("card_back", cards_dir),
        ("overlay_locked", cards_dir),
    ]

    print(f"  Found {len(components)} components, expected {len(names_and_dirs)}")
    for i, (box, (name, out_dir)) in enumerate(zip(components, names_and_dirs)):
        crop_and_save(img, box, out_dir / f"{name}.png")


def split_frozen_foods(img_path: Path) -> None:
    """Split frozen food items sprite sheet."""
    print(f"\n=== Splitting: {img_path.name} ===")
    img = Image.open(img_path).convert("RGBA")
    alpha = np.array(img)[:, :, 3]

    components = find_connected_components(alpha, min_area=2000)
    components = merge_close_components(components, gap_threshold=20)
    components = sort_components_grid(components)

    out_dir = UI_DIR / "food"

    # Expected: ramen, dumpling, kimbap, burger, chicken, pizza, tteokbokki
    names = [
        "frozen_food_ramen",
        "frozen_food_dumpling",
        "frozen_food_kimbap",
        "frozen_food_burger",
        "frozen_food_chicken",
        "frozen_food_pizza",
        "frozen_food_tteokbokki",
    ]

    print(f"  Found {len(components)} components, expected {len(names)}")
    for i, (box, name) in enumerate(zip(components, names)):
        crop_and_save(img, box, out_dir / f"{name}.png")


def main():
    print("=" * 60)
    print("Fall In! Sprite Sheet Splitter")
    print("=" * 60)

    # Mapping of sprite sheet files to their splitting functions
    sheets = {
        "assets_btns.png": split_buttons,
        "assets_huds.png": split_huds,
        "assets_panels.png": split_panels,
        "assets_banners.png": split_banners,
        "assets_icon_and_badges.png": split_icons,
        "assets_chatbox_and_cards.png": split_chatbox_and_cards,
        "assets_frozen_foods.png": split_frozen_foods,
    }

    for filename, splitter in sheets.items():
        path = ASSETS_DIR / filename
        if path.exists():
            splitter(path)
        else:
            print(f"\n⚠ Missing: {filename}")

    print("\n" + "=" * 60)
    print("Done! Check assets/images/ui/ for the split assets.")
    print("=" * 60)


if __name__ == "__main__":
    main()
