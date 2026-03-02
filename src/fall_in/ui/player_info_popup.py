"""
PlayerInfoPopup - Overlay popup for player profile, stats, and medals.

Displays player information in a Korean Air Force service dress uniform-inspired
layout: profile & stats on the left, earned medals on the right (like medals
pinned to the left chest of a uniform).

Can be used from any scene by composing it into the scene class.
"""

import pygame

from fall_in.utils.asset_loader import get_font
from fall_in.config import (
    SCREEN_WIDTH,
    SCREEN_HEIGHT,
    LIGHT_BLUE,
    WHITE,
    PLAYER_INFO_POPUP_WIDTH,
    PLAYER_INFO_POPUP_HEIGHT,
    PLAYER_INFO_PROFILE_RADIUS,
)


class PlayerInfoPopup:
    """Modal popup showing player profile, game stats, and earned medals."""

    # Medal grid layout (supports up to 20 medals)
    MEDAL_COLS = 5
    MEDAL_ROWS = 4
    MEDAL_ICON_SIZE = 40
    MEDAL_GAP = 8

    # Profile change button
    PROFILE_BTN_WIDTH = 60
    PROFILE_BTN_HEIGHT = 22

    def __init__(self) -> None:
        self.visible = False

        # Popup rect (centered on screen)
        self.rect = pygame.Rect(
            (SCREEN_WIDTH - PLAYER_INFO_POPUP_WIDTH) // 2,
            (SCREEN_HEIGHT - PLAYER_INFO_POPUP_HEIGHT) // 2,
            PLAYER_INFO_POPUP_WIDTH,
            PLAYER_INFO_POPUP_HEIGHT,
        )

        # Close button rect (top-right of popup)
        self._close_btn = pygame.Rect(self.rect.right - 36, self.rect.top + 8, 28, 28)

        # Hovered medal index (for tooltip)
        self._hovered_medal_idx: int | None = None

        # UI images cache
        self._ui_images: dict[str, pygame.Surface] | None = None
        self._hud_images: dict[str, pygame.Surface] | None = None

    def _ensure_images_loaded(self) -> None:
        """Lazy-load UI images from the manifest cache."""
        if self._ui_images is not None:
            return
        from fall_in.utils.asset_manifest import AssetManifest

        self._ui_images = {}
        for category in ("panels", "icons"):
            self._ui_images.update(AssetManifest.get_loaded(category))
        self._hud_images = AssetManifest.get_loaded("hud")

    def toggle(self) -> None:
        """Toggle popup visibility."""
        self.visible = not self.visible
        if self.visible:
            self._hovered_medal_idx = None

    def show(self) -> None:
        self.visible = True
        self._hovered_medal_idx = None

    def hide(self) -> None:
        self.visible = False

    # ------------------------------------------------------------------
    # Event handling
    # ------------------------------------------------------------------

    def handle_event(self, event: pygame.event.Event) -> bool:
        """Handle event. Returns True if the event was consumed."""
        if not self.visible:
            return False

        if event.type == pygame.MOUSEBUTTONDOWN:
            pos = event.pos

            # Close button
            if self._close_btn.collidepoint(pos):
                self.hide()
                return True

            # Click inside popup = consume but do nothing
            if self.rect.collidepoint(pos):
                return True

            # Click outside popup = close
            self.hide()
            return True

        elif event.type == pygame.MOUSEMOTION:
            # Update hovered medal for tooltip
            self._update_hovered_medal(event.pos)

        elif event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                self.hide()
                return True

        return self.visible  # consume all events while visible

    def _update_hovered_medal(self, pos: tuple[int, int]) -> None:
        """Check if mouse is hovering over any medal icon."""
        from fall_in.core.medal_manager import MedalManager

        all_medals = MedalManager().get_all_medals()
        if not all_medals:
            self._hovered_medal_idx = None
            return

        medal_area_x, medal_area_y = self._get_medal_area_origin()

        for i, _medal in enumerate(all_medals):
            row = i // self.MEDAL_COLS
            col = i % self.MEDAL_COLS
            if row >= self.MEDAL_ROWS:
                break

            icon_x = medal_area_x + col * (self.MEDAL_ICON_SIZE + self.MEDAL_GAP)
            icon_y = medal_area_y + row * (self.MEDAL_ICON_SIZE + self.MEDAL_GAP)
            icon_rect = pygame.Rect(
                icon_x, icon_y, self.MEDAL_ICON_SIZE, self.MEDAL_ICON_SIZE
            )

            if icon_rect.collidepoint(pos):
                self._hovered_medal_idx = i
                return

        self._hovered_medal_idx = None

    def _get_medal_area_origin(self) -> tuple[int, int]:
        """Return (x, y) for the top-left of the medal grid."""
        # Right portion of popup (60% area)
        divider_x = self.rect.x + int(PLAYER_INFO_POPUP_WIDTH * 0.40)
        medal_area_x = divider_x + 20
        medal_area_y = self.rect.y + 75
        return medal_area_x, medal_area_y

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------

    def render(self, screen: pygame.Surface) -> None:
        """Render the player info popup overlay."""
        if not self.visible:
            return

        self._ensure_images_loaded()

        # Dim overlay
        overlay = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 140))
        screen.blit(overlay, (0, 0))

        # Popup background
        self._draw_background(screen)

        # Close button (X)
        pygame.draw.rect(screen, (180, 60, 60), self._close_btn, border_radius=6)
        close_font = get_font(16, "bold")
        x_text = close_font.render("✕", True, WHITE)
        screen.blit(x_text, x_text.get_rect(center=self._close_btn.center))

        # Title
        title_font = get_font(22, "bold")
        title = title_font.render("플레이어 정보", True, WHITE)
        screen.blit(
            title,
            title.get_rect(centerx=self.rect.centerx, top=self.rect.top + 14),
        )

        # Divider line (40% from left)
        divider_x = self.rect.x + int(PLAYER_INFO_POPUP_WIDTH * 0.40)
        pygame.draw.line(
            screen,
            (*WHITE, 80),
            (divider_x, self.rect.y + 50),
            (divider_x, self.rect.bottom - 20),
            1,
        )

        # Left side: profile & stats
        self._draw_profile_and_stats(screen, divider_x)

        # Right side: medals
        self._draw_medals(screen)

        # Medal tooltip (drawn last, on top)
        if self._hovered_medal_idx is not None:
            self._draw_medal_tooltip(screen)

    def _draw_background(self, screen: pygame.Surface) -> None:
        """Draw popup background — uses asset image or fallback."""
        if self._ui_images and "panel_player_info" in self._ui_images:
            bg_img = pygame.transform.smoothscale(
                self._ui_images["panel_player_info"],
                (self.rect.width, self.rect.height),
            )
            screen.blit(bg_img, self.rect.topleft)
        else:
            # Fallback: military uniform-inspired background
            popup_surf = pygame.Surface(
                (self.rect.width, self.rect.height), pygame.SRCALPHA
            )

            # Base: dark navy uniform color
            base_color = (25, 40, 65, 240)
            pygame.draw.rect(
                popup_surf,
                base_color,
                (0, 0, self.rect.width, self.rect.height),
                border_radius=14,
            )

            # Subtle horizontal stripes (uniform fabric texture hint)
            for y in range(0, self.rect.height, 6):
                stripe_alpha = 15 if y % 12 == 0 else 8
                pygame.draw.line(
                    popup_surf,
                    (255, 255, 255, stripe_alpha),
                    (8, y),
                    (self.rect.width - 8, y),
                    1,
                )

            # Shoulder/lapel accent line (top border)
            pygame.draw.rect(
                popup_surf,
                (50, 75, 110, 200),
                (0, 0, self.rect.width, 6),
                border_radius=14,
            )

            # Pocket flap hint on right side
            pocket_x = int(self.rect.width * 0.42)
            pocket_y = 55
            pocket_w = int(self.rect.width * 0.54)
            pocket_h = self.rect.height - 75
            pygame.draw.rect(
                popup_surf,
                (30, 50, 78, 80),
                (pocket_x, pocket_y, pocket_w, pocket_h),
                border_radius=6,
            )
            pygame.draw.rect(
                popup_surf,
                (60, 85, 120, 60),
                (pocket_x, pocket_y, pocket_w, pocket_h),
                width=1,
                border_radius=6,
            )

            # Border
            pygame.draw.rect(
                popup_surf,
                (60, 90, 130),
                (0, 0, self.rect.width, self.rect.height),
                width=2,
                border_radius=14,
            )

            screen.blit(popup_surf, self.rect.topleft)

    def _draw_profile_and_stats(self, screen: pygame.Surface, divider_x: int) -> None:
        """Draw player profile photo and game stats on the left side."""
        from fall_in.core.game_manager import GameManager
        from fall_in.core.prestige_manager import PrestigeManager

        game = GameManager()
        prestige_count = PrestigeManager().get_prestige_count()

        # Load player data
        player_data = game.load_player_data()

        left_center_x = self.rect.x + int(PLAYER_INFO_POPUP_WIDTH * 0.20)
        profile_y = self.rect.y + 90

        # Profile picture (circular)
        profile_radius = PLAYER_INFO_PROFILE_RADIUS
        profile_center = (left_center_x, profile_y)

        # Black background circle (prevents background bleed-through)
        pygame.draw.circle(screen, (0, 0, 0), profile_center, profile_radius)

        # Draw portrait photo (player_portrait_unknown as default photo)
        portrait_key = "player_portrait_unknown"
        if self._ui_images and portrait_key in self._ui_images:
            avatar_size = profile_radius * 2
            portrait_img = pygame.transform.smoothscale(
                self._ui_images[portrait_key], (avatar_size, avatar_size)
            )
            # Circular mask
            mask = pygame.Surface((avatar_size, avatar_size), pygame.SRCALPHA)
            pygame.draw.circle(
                mask,
                (255, 255, 255, 255),
                (profile_radius, profile_radius),
                profile_radius,
            )
            portrait_img.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MIN)
            screen.blit(
                portrait_img,
                (
                    profile_center[0] - profile_radius,
                    profile_center[1] - profile_radius,
                ),
            )
        else:
            # Fallback placeholder circle
            pygame.draw.circle(screen, (80, 100, 130), profile_center, profile_radius)
            icon_font = get_font(28)
            icon_text = icon_font.render("👤", True, WHITE)
            screen.blit(icon_text, icon_text.get_rect(center=profile_center))

        # Draw border frame (player_avatar is the border asset)
        if self._hud_images and "player_avatar" in self._hud_images:
            frame_size = profile_radius * 2 + 8  # slightly larger than portrait
            frame_img = pygame.transform.smoothscale(
                self._hud_images["player_avatar"], (frame_size, frame_size)
            )
            screen.blit(
                frame_img,
                (
                    profile_center[0] - frame_size // 2,
                    profile_center[1] - frame_size // 2,
                ),
            )
        else:
            pygame.draw.circle(screen, WHITE, profile_center, profile_radius, 2)

        # "변경" button below profile
        btn_x = left_center_x - self.PROFILE_BTN_WIDTH // 2
        btn_y = profile_y + profile_radius + 8
        btn_rect = pygame.Rect(
            btn_x, btn_y, self.PROFILE_BTN_WIDTH, self.PROFILE_BTN_HEIGHT
        )
        pygame.draw.rect(screen, (60, 80, 110, 180), btn_rect, border_radius=4)
        pygame.draw.rect(screen, LIGHT_BLUE, btn_rect, width=1, border_radius=4)
        btn_font = get_font(11)
        btn_text = btn_font.render("변경", True, WHITE)
        screen.blit(btn_text, btn_text.get_rect(center=btn_rect.center))

        # Stats section
        stats_y = btn_y + self.PROFILE_BTN_HEIGHT + 16
        stat_font = get_font(13)
        line_height = 22

        win_count = player_data.get("win_count", 0)
        max_survived = player_data.get("max_survived_rounds", 0)
        currency = player_data.get("currency", 0)

        stats = [
            f"💰 보유 수당: {currency}원",
            f"🏆 승리: {win_count}회",
            f"⏱ 최대 생존: {max_survived} 라운드",
        ]

        if prestige_count > 0:
            stats.append(f"⭐ Prestige: x{prestige_count}")

        for i, stat_text in enumerate(stats):
            text_surf = stat_font.render(stat_text, True, (200, 210, 225))
            text_rect = text_surf.get_rect(
                centerx=left_center_x, top=stats_y + i * line_height
            )
            screen.blit(text_surf, text_rect)

    def _draw_medals(self, screen: pygame.Surface) -> None:
        """Draw earned medals grid on the right side."""
        from fall_in.core.medal_manager import MedalManager

        medal_mgr = MedalManager()
        all_medals = medal_mgr.get_all_medals()
        player_medals = set(medal_mgr.get_player_medals())

        if not all_medals:
            return

        # Section title
        medal_area_x, medal_area_y = self._get_medal_area_origin()
        section_font = get_font(16, "bold")
        section_title = section_font.render("🎖 획득 훈장", True, WHITE)
        screen.blit(section_title, (medal_area_x, medal_area_y - 30))

        icon_font = get_font(20)
        lock_font = get_font(16)
        small_font = get_font(10)

        for i, medal in enumerate(all_medals):
            row = i // self.MEDAL_COLS
            col = i % self.MEDAL_COLS
            if row >= self.MEDAL_ROWS:
                break

            icon_x = medal_area_x + col * (self.MEDAL_ICON_SIZE + self.MEDAL_GAP)
            icon_y = medal_area_y + row * (self.MEDAL_ICON_SIZE + self.MEDAL_GAP)
            icon_rect = pygame.Rect(
                icon_x, icon_y, self.MEDAL_ICON_SIZE, self.MEDAL_ICON_SIZE
            )

            earned = medal["id"] in player_medals
            is_hovered = self._hovered_medal_idx == i

            if earned:
                # Earned medal: golden background
                bg_color = (
                    (180, 150, 50, 180) if not is_hovered else (210, 180, 60, 220)
                )
                pygame.draw.rect(screen, bg_color, icon_rect, border_radius=8)
                pygame.draw.rect(
                    screen, (220, 190, 80), icon_rect, width=2, border_radius=8
                )
                # Medal icon (emoji placeholder)
                medal_text = icon_font.render("🏅", True, WHITE)
                screen.blit(
                    medal_text,
                    medal_text.get_rect(
                        center=(
                            icon_x + self.MEDAL_ICON_SIZE // 2,
                            icon_y + self.MEDAL_ICON_SIZE // 2 - 4,
                        )
                    ),
                )
                # Medal name below icon
                name_text = small_font.render(medal["name"][:6], True, (240, 230, 200))
                screen.blit(
                    name_text,
                    name_text.get_rect(
                        centerx=icon_x + self.MEDAL_ICON_SIZE // 2,
                        top=icon_y + self.MEDAL_ICON_SIZE - 14,
                    ),
                )
            else:
                # Locked medal: dark/gray
                bg_color = (40, 50, 65, 150) if not is_hovered else (55, 65, 80, 180)
                pygame.draw.rect(screen, bg_color, icon_rect, border_radius=8)
                pygame.draw.rect(
                    screen, (80, 90, 110), icon_rect, width=1, border_radius=8
                )
                lock_text = lock_font.render("🔒", True, (120, 130, 140))
                screen.blit(
                    lock_text,
                    lock_text.get_rect(
                        center=(
                            icon_x + self.MEDAL_ICON_SIZE // 2,
                            icon_y + self.MEDAL_ICON_SIZE // 2,
                        )
                    ),
                )

        # Extra medals indicator (if more than grid can show)
        max_visible = self.MEDAL_ROWS * self.MEDAL_COLS
        if len(all_medals) > max_visible:
            extra_font = get_font(12)
            extra_text = extra_font.render(
                f"+{len(all_medals) - max_visible} more",
                True,
                (150, 160, 175),
            )
            extra_y = medal_area_y + self.MEDAL_ROWS * (
                self.MEDAL_ICON_SIZE + self.MEDAL_GAP
            )
            screen.blit(extra_text, (medal_area_x, extra_y))

    def _draw_medal_tooltip(self, screen: pygame.Surface) -> None:
        """Draw tooltip for hovered medal."""
        from fall_in.core.medal_manager import MedalManager

        all_medals = MedalManager().get_all_medals()
        if self._hovered_medal_idx is None or self._hovered_medal_idx >= len(
            all_medals
        ):
            return

        medal = all_medals[self._hovered_medal_idx]
        player_medals = set(MedalManager().get_player_medals())
        earned = medal["id"] in player_medals

        # Tooltip content
        name = medal.get("name", "???")
        description = medal.get("description", "")
        status = "✅ 획득" if earned else "🔒 미획득"

        name_font = get_font(14, "bold")
        desc_font = get_font(12)
        status_font = get_font(11)

        name_surf = name_font.render(name, True, WHITE)
        desc_surf = desc_font.render(description, True, (200, 210, 220))
        status_surf = status_font.render(
            status, True, (160, 200, 160) if earned else (180, 140, 140)
        )

        # Calculate tooltip size
        padding = 10
        tooltip_w = (
            max(name_surf.get_width(), desc_surf.get_width(), status_surf.get_width())
            + padding * 2
        )
        tooltip_h = (
            name_surf.get_height()
            + desc_surf.get_height()
            + status_surf.get_height()
            + padding * 2
            + 8
        )

        # Position tooltip near mouse
        mouse_pos = pygame.mouse.get_pos()
        tooltip_x = mouse_pos[0] + 15
        tooltip_y = mouse_pos[1] - tooltip_h - 5

        # Keep within screen bounds
        if tooltip_x + tooltip_w > SCREEN_WIDTH:
            tooltip_x = mouse_pos[0] - tooltip_w - 5
        if tooltip_y < 0:
            tooltip_y = mouse_pos[1] + 20

        tooltip_rect = pygame.Rect(tooltip_x, tooltip_y, tooltip_w, tooltip_h)

        # Draw tooltip background
        tooltip_surf = pygame.Surface((tooltip_w, tooltip_h), pygame.SRCALPHA)
        pygame.draw.rect(
            tooltip_surf,
            (20, 30, 50, 230),
            (0, 0, tooltip_w, tooltip_h),
            border_radius=6,
        )
        pygame.draw.rect(
            tooltip_surf,
            (80, 100, 140),
            (0, 0, tooltip_w, tooltip_h),
            width=1,
            border_radius=6,
        )
        screen.blit(tooltip_surf, tooltip_rect.topleft)

        # Draw tooltip text
        y = tooltip_rect.y + padding
        screen.blit(name_surf, (tooltip_rect.x + padding, y))
        y += name_surf.get_height() + 4
        screen.blit(desc_surf, (tooltip_rect.x + padding, y))
        y += desc_surf.get_height() + 4
        screen.blit(status_surf, (tooltip_rect.x + padding, y))
