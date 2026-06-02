from __future__ import annotations

import sys
from pathlib import Path

from .constants import ASSETS_DIR


def get_runtime_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS"))
    return ASSETS_DIR.parents[1]


def get_pet_assets_dir() -> Path:
    if getattr(sys, "frozen", False):
        return get_runtime_root() / "assets" / "pet"
    return ASSETS_DIR
