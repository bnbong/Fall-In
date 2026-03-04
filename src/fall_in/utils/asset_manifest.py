"""
Asset Manifest — Declarative registry of all game assets.

Centralized source of truth for asset paths, organized by category.
Used by AssetLoader.preload_all() to pre-cache everything at startup,
and by scenes/entities to look up assets by logical key.
"""

from __future__ import annotations

from typing import Optional

import pygame


# ---------------------------------------------------------------------------
# Manifest: category -> {key: relative_path_from_images_dir}
# ---------------------------------------------------------------------------

ASSET_MANIFEST: dict[str, dict[str, str]] = {
    # === HUD (in-game top bar and overlays) ===
    "hud": {
        "top_bar": "ui/hud/hud_top_bar.png",
        "gauge_bg": "ui/hud/gauge_bg.png",
        "gauge_safe": "ui/hud/gauge_fill_safe.png",
        "gauge_extra": "ui/hud/gauge_fill_extra.png",
        "gauge_warning": "ui/hud/gauge_fill_warning.png",
        "gauge_danger": "ui/hud/gauge_fill_danger.png",
        "gauge_critical": "ui/hud/gauge_fill_critical.png",
        "round_indicator": "ui/hud/round_indicator.png",
        "hangar_icon": "ui/hud/hud_hangar_icon.png",
        "player_panel": "ui/hud/panel_player.png",
        "danger_warning": "ui/hud/icon_danger_warning.png",
        "player_avatar": "ui/hud/icon_player_avatar.png",
        "turn_log": "ui/panels/panel_turn_log.png",
        "box": "ui/hud/box.png",
    },
    # === Buttons ===
    "buttons": {
        "btn_large_normal": "ui/buttons/btn_large_normal.png",
        "btn_large_hover": "ui/buttons/btn_large_hover.png",
        "btn_large_pressed": "ui/buttons/btn_large_pressed.png",
        "btn_small_normal": "ui/buttons/btn_small_normal.png",
        "btn_small_hover": "ui/buttons/btn_small_hover.png",
        "btn_small_pressed": "ui/buttons/btn_small_pressed.png",
        "btn_circle_normal": "ui/buttons/btn_circle_normal.png",
        "btn_circle_hover": "ui/buttons/btn_circle_hover.png",
        "btn_close_normal": "ui/buttons/btn_close_normal.png",
        "btn_close_hover": "ui/buttons/btn_close_hover.png",
    },
    # === Panels & Popups ===
    "panels": {
        "panel_player": "ui/panels/panel_player.png",
        "panel_turn_log": "ui/panels/panel_turn_log.png",
        "panel_result_table": "ui/panels/panel_result_table.png",
        "panel_stats_box": "ui/panels/panel_stats_box.png",
        "panel_rankings": "ui/panels/panel_rankings.png",
        "panel_notes": "ui/panels/panel_notes.png",
        "panel_soldier_detail": "ui/panels/panel_soldier_detail.png",
        "panel_currency_info": "ui/panels/panel_currency_info.png",
        "panel_currency_info_sm": "ui/panels/panel_currency_info_sm.png",
        "panel_player_info": "ui/panels/panel_player_info.png",
        "popup_dev_info": "ui/panels/popup_dev_info.png",
        "popup_message": "ui/panels/popup_message.png",
        "panel_settings": "ui/panels/panel_settings.png",
    },
    # === Banners ===
    "banners": {
        "banner_victory": "ui/banners/banner_victory.png",
        "banner_defeat": "ui/banners/banner_defeat.png",
        "banner_coup": "ui/banners/banner_coup.png",
        "star_decoration": "ui/banners/star_decoration.png",
    },
    # === Icons & Badges ===
    "icons": {
        "badge_danger": "ui/icons/badge_danger.png",
        "badge_eliminated": "ui/icons/badge_eliminated.png",
        "badge_survived": "ui/icons/badge_survived.png",
        "icon_check": "ui/icons/icon_check.png",
        "icon_currency": "ui/icons/icon_currency.png",
        "icon_lock": "ui/icons/icon_lock.png",
        "icon_medal": "ui/icons/icon_medal.png",
        "icon_prestige": "ui/icons/icon_prestige.png",
        "number_circle": "ui/icons/number_circle.png",
        "player_portrait_unknown": "ui/icons/player_portrait_unknown.png",
        "toast_bg": "ui/icons/toast_bg.png",
        "icon_info": "ui/icons/icon_info.png",
        "icon_replay": "ui/icons/icon_replay.png",
        "icon_settings_gear": "ui/icons/icon_settings_gear.png",
        "icon_tutorial": "ui/icons/icon_tutorial.png",
    },
    # === Speech Bubbles ===
    "speech": {
        "speech_announcement": "ui/speech/speech_announcement.png",
        "speech_bubble_body": "ui/speech/speech_bubble_body.png",
        "speech_bubble_tail_left": "ui/speech/speech_bubble_tail_left.png",
        "speech_bubble_tail_right": "ui/speech/speech_bubble_tail_right.png",
    },
    # === Frozen Food ===
    "food": {
        "frozen_food_ramen": "ui/food/frozen_food_ramen.png",
        "frozen_food_dumpling": "ui/food/frozen_food_dumpling.png",
        "frozen_food_kimbap": "ui/food/frozen_food_kimbap.png",
        "frozen_food_burger": "ui/food/frozen_food_burger.png",
        "frozen_food_chicken": "ui/food/frozen_food_chicken.png",
        "frozen_food_pizza": "ui/food/frozen_food_pizza.png",
        "frozen_food_tteokbokki": "ui/food/frozen_food_tteokbokki.png",
    },
    # === Cards ===
    "cards": {
        "card_back": "cards/batallion_card_back.png",
        "card_base": "cards/battalion_card_base_single.png",
        "card_base_sheet": "cards/battalion_card_base.png",
        "ui_card_back": "ui/cards/card_back.png",
        "overlay_locked": "ui/cards/overlay_locked.png",
    },
    # === Backgrounds ===
    "backgrounds": {
        "ingame": "ui/backgrounds/ingame_background.png",
        "meetingroom": "ui/backgrounds/meetingroom_background.png",
    },
    # === Tiles ===
    "tiles": {
        "tile_empty": "entity/tile_1.png",
        "tile_safe": "entity/tile_2.png",
        "tile_warning": "entity/tile_3.png",
        "tile_danger": "entity/tile_4.png",
    },
    # === Logos ===
    "logos": {
        "logo": "fall_in_logo.png",
        "logo_text": "fall_in_logo_text.png",
    },
    # === Characters (commander) ===
    "characters": {
        "commander": "characters/commander/commander.png",
    },
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


class AssetManifest:
    """
    Static interface for reading the asset manifest.
    """

    @staticmethod
    def get_all_paths() -> list[str]:
        """Return a flat list of every asset path in the manifest."""
        paths: list[str] = []
        for category in ASSET_MANIFEST.values():
            paths.extend(category.values())
        return paths

    @staticmethod
    def get_path(category: str, key: str) -> Optional[str]:
        """Look up a single asset path.  Returns None if not found."""
        cat = ASSET_MANIFEST.get(category)
        if cat is None:
            return None
        return cat.get(key)

    @staticmethod
    def get_category(category: str) -> dict[str, str]:
        """Return the full {key: path} dict for a category."""
        return ASSET_MANIFEST.get(category, {})

    @staticmethod
    def get_loaded(category: str) -> dict[str, pygame.Surface]:
        """
        Return already-loaded surfaces for a category.

        Looks up each path in the AssetLoader cache.  Missing images
        (magenta placeholders or load errors) are silently skipped.
        """
        from fall_in.utils.asset_loader import AssetLoader

        loader = AssetLoader()
        result: dict[str, pygame.Surface] = {}
        for key, path in AssetManifest.get_category(category).items():
            if path in loader._images:
                img = loader._images[path]
                # Skip magenta placeholder (64×64 = missing asset)
                if img.get_width() == 64 and img.get_height() == 64:
                    continue
                result[key] = img
        return result

    @staticmethod
    def categories() -> list[str]:
        """Return list of all category names."""
        return list(ASSET_MANIFEST.keys())
