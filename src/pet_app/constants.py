from __future__ import annotations

from pathlib import Path

APP_NAME = "DeskPet"
SETTINGS_FILE_NAME = "settings.json"
DEFAULT_FRAME_DURATION_MS = 120
DEFAULT_SCALE = 1.0
DEFAULT_HITBOX_PADDING = 8
DEFAULT_ANCHOR_BOTTOM_OFFSET = 0
WINDOW_FLAGS_DOC = "Frameless + Tool + AlwaysOnTop"

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ASSETS_DIR = PROJECT_ROOT / "assets" / "pet"

DEFAULT_TICK_MS = 24
DEFAULT_IDLE_RANGE_MS = (2000, 6000)
DEFAULT_WALK_RANGE_MS = (1500, 4000)
DEFAULT_SPEED_RANGE = (2, 4)

IDLE = "idle"
WALK_LEFT = "walk_left"
WALK_RIGHT = "walk_right"
DRAGGED = "dragged"
CLICKED = "clicked"

SUPPORTED_ACTIONS = (
    IDLE,
    WALK_LEFT,
    WALK_RIGHT,
    DRAGGED,
    CLICKED,
)
