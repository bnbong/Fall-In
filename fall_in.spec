# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for 헤쳐 모여! (Fall In!)
# Build: pyinstaller fall_in.spec

import sys

block_cipher = None

# Platform-specific icon
if sys.platform == "win32":
    icon_file = "assets/fall_in_icon.ico"
elif sys.platform == "darwin":
    icon_file = "assets/fall_in_icon.icns"
else:
    icon_file = "assets/fall_in_icon.png"

a = Analysis(
    ["src/fall_in/main.py"],
    pathex=[".", "src"],
    binaries=[],
    datas=[
        ("assets", "assets"),  # All game assets
        ("data", "data"),      # Game data (soldiers.json, etc.)
    ],
    hiddenimports=[
        "pygame",
        "pygame.mixer",
        "pygame.font",
        "pygame.image",
        "pygame.display",
        "pygame._sdl2",
        "pygame._sdl2.video",
        "pygame.gfxdraw",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "tkinter",
        "unittest",
        "email",
        "html",
        "http",
        "xml",
        "test",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="fall-in",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,  # No terminal window
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=icon_file,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="fall-in",
)

# macOS: wrap COLLECT into .app bundle
if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name="Fall In.app",
        icon=icon_file,
        bundle_identifier="com.bnbong.fall-in",
        info_plist={
            "NSHighResolutionCapable": True,
            "LSMinimumSystemVersion": "10.13.0",
            "CFBundleName": "헤쳐 모여!",
            "CFBundleDisplayName": "헤쳐 모여! (Fall In!)",
        },
    )
