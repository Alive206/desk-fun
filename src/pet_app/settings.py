from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from .constants import APP_NAME, SETTINGS_FILE_NAME
from .models import AppSettings


def get_settings_path() -> Path:
    base_dir = Path.home() / f".{APP_NAME.lower()}"
    base_dir.mkdir(parents=True, exist_ok=True)
    return base_dir / SETTINGS_FILE_NAME


def load_settings() -> AppSettings:
    path = get_settings_path()
    if not path.exists():
        return AppSettings()

    raw = json.loads(path.read_text(encoding="utf-8"))
    defaults = asdict(AppSettings())
    merged = {**defaults, **raw}
    return AppSettings(**merged)


def save_settings(settings: AppSettings) -> None:
    path = get_settings_path()
    path.write_text(
        json.dumps(asdict(settings), ensure_ascii=True, indent=2),
        encoding="utf-8",
    )
