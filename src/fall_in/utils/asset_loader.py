"""
Asset Loader - Handles loading of fonts, images, and sounds
"""

from typing import Optional

import pygame

from fall_in.config import FONTS_DIR, IMAGES_DIR, SOUNDS_DIR


class AssetLoader:
    """
    Singleton asset loader for managing game resources.
    Handles font loading with Korean language support.
    """

    _instance: Optional["AssetLoader"] = None

    def __new__(cls) -> "AssetLoader":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        self._initialized = True
        self._fonts: dict[tuple[str, int], pygame.font.Font] = {}
        self._images: dict[str, pygame.Surface] = {}
        self._sounds: dict[str, pygame.mixer.Sound] = {}

        # Default Korean font path
        self._korean_font_path = FONTS_DIR / "ROKAF Sans Bold.ttf"

    def get_font(self, size: int, font_name: str = "korean") -> pygame.font.Font:
        """
        Get a font of the specified size.
        Uses ROKAF (Korean Air Force) fonts by default for proper styling.

        Args:
            size: Font size in pixels
            font_name: "korean", "bold", or specific font filename

        Returns:
            pygame.font.Font object
        """
        cache_key = (font_name, size)

        if cache_key not in self._fonts:
            font = None

            if font_name in ("korean", "bold"):
                # ROKAF fonts for primary display
                if font_name == "bold":
                    rokaf_fonts = [
                        "ROKAF Sans Bold.otf",
                        "ROKAF Slab Serif Bold.otf",
                    ]
                else:
                    rokaf_fonts = [
                        "ROKAF Sans Medium.otf",
                        "ROKAF Slab Serif Medium.otf",
                    ]

                # Try ROKAF fonts first
                for font_file in rokaf_fonts:
                    font_path = FONTS_DIR / font_file
                    if font_path.exists():
                        try:
                            font = pygame.font.Font(str(font_path), size)
                            # Test Korean rendering
                            test_surface = font.render("테스트", True, (0, 0, 0))
                            if test_surface.get_width() > 0:
                                break
                        except Exception as e:
                            print(f"Error loading font {font_path}: {e}")
                            font = None
                            continue

                # Fallback to system fonts if ROKAF doesn't work
                if font is None:
                    korean_fonts = [
                        "AppleGothic",
                        "Apple SD Gothic Neo",
                        "NanumGothic",
                        "Malgun Gothic",
                    ]

                    for sys_font in korean_fonts:
                        try:
                            font = pygame.font.SysFont(sys_font, size)
                            test_surface = font.render("테스트", True, (0, 0, 0))
                            if test_surface.get_width() > 0:
                                break
                        except Exception as e:
                            print(f"Error loading font {font_path}: {e}")
                            font = None
                            continue
            else:
                # Specific font file requested
                font_path = FONTS_DIR / font_name
                if font_path.exists():
                    try:
                        font = pygame.font.Font(str(font_path), size)
                    except Exception as e:
                        print(f"Error loading font {font_path}: {e}")
                        font = None

            # Fallback to any working font
            if font is None:
                font = pygame.font.Font(None, size)

            self._fonts[cache_key] = font

        return self._fonts[cache_key]

    def load_image(self, path: str, convert_alpha: bool = True) -> pygame.Surface:
        """
        Load an image from the assets/images directory.

        Args:
            path: Relative path from assets/images/
            convert_alpha: Whether to convert with alpha channel

        Returns:
            pygame.Surface
        """
        if path not in self._images:
            full_path = IMAGES_DIR / path

            if full_path.exists():
                image = pygame.image.load(str(full_path))
                if convert_alpha:
                    image = image.convert_alpha()
                else:
                    image = image.convert()
                self._images[path] = image
            else:
                # Return a placeholder surface
                placeholder = pygame.Surface((64, 64))
                placeholder.fill((255, 0, 255))  # Magenta for missing texture
                self._images[path] = placeholder

        return self._images[path]

    def load_sound(self, path: str) -> Optional[pygame.mixer.Sound]:
        """
        Load a sound from the assets/sounds directory.

        Args:
            path: Relative path from assets/sounds/

        Returns:
            pygame.mixer.Sound or None if not found
        """
        if path not in self._sounds:
            full_path = SOUNDS_DIR / path

            if full_path.exists():
                self._sounds[path] = pygame.mixer.Sound(str(full_path))
            else:
                return None

        return self._sounds[path]

    def clear_cache(self) -> None:
        """Clear all cached assets"""
        self._fonts.clear()
        self._images.clear()
        self._sounds.clear()


# Convenience function
def get_font(size: int, font_name: str = "korean") -> pygame.font.Font:
    """Get a font from the asset loader"""
    return AssetLoader().get_font(size, font_name)
