from __future__ import annotations

import json
from collections import deque
from pathlib import Path
from statistics import multimode

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QImage, QPixmap, QTransform

from .constants import (
    CLICKED,
    DEFAULT_ANCHOR_BOTTOM_OFFSET,
    DEFAULT_FRAME_DURATION_MS,
    DEFAULT_HITBOX_PADDING,
    DEFAULT_SCALE,
    DRAGGED,
    IDLE,
    SUPPORTED_ACTIONS,
    WALK_LEFT,
    WALK_RIGHT,
)
from .models import AnimationSpec, SpriteSet
from .resource_path import get_pet_assets_dir


def _load_manifest(assets_dir: Path) -> AnimationSpec:
    manifest_path = assets_dir / "manifest.json"
    if not manifest_path.exists():
        return AnimationSpec(
            frame_duration_ms=DEFAULT_FRAME_DURATION_MS,
            anchor_bottom_offset=DEFAULT_ANCHOR_BOTTOM_OFFSET,
            default_scale=DEFAULT_SCALE,
            hitbox_padding=DEFAULT_HITBOX_PADDING,
            max_display_size=256,
            auto_remove_background=True,
            background_tolerance=48,
            drag_hold_ms=180,
            click_pause_ms=400,
        )

    raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    return AnimationSpec(
        frame_duration_ms=int(raw.get("frame_duration_ms", DEFAULT_FRAME_DURATION_MS)),
        anchor_bottom_offset=int(
            raw.get("anchor_bottom_offset", DEFAULT_ANCHOR_BOTTOM_OFFSET)
        ),
        default_scale=float(raw.get("default_scale", DEFAULT_SCALE)),
        hitbox_padding=int(raw.get("hitbox_padding", DEFAULT_HITBOX_PADDING)),
        max_display_size=max(32, int(raw.get("max_display_size", 256))),
        auto_remove_background=bool(raw.get("auto_remove_background", True)),
        background_tolerance=max(0, int(raw.get("background_tolerance", 48))),
        drag_hold_ms=max(0, int(raw.get("drag_hold_ms", 180))),
        click_pause_ms=max(0, int(raw.get("click_pause_ms", 400))),
    )


def _color_distance(left: QColor, right: QColor) -> int:
    return max(
        abs(left.red() - right.red()),
        abs(left.green() - right.green()),
        abs(left.blue() - right.blue()),
    )


def _sample_background_colors(image: QImage) -> list[QColor]:
    width = image.width()
    height = image.height()
    points = {
        (0, 0),
        (width - 1, 0),
        (0, height - 1),
        (width - 1, height - 1),
        (width // 2, 0),
        (width // 2, height - 1),
        (0, height // 2),
        (width - 1, height // 2),
    }
    return [image.pixelColor(x, y) for x, y in points]


def _detect_checkerboard_background(
    image: QImage,
) -> tuple[QColor, QColor] | None:
    width = image.width()
    height = image.height()
    samples = [
        image.pixelColor(0, 0),
        image.pixelColor(width - 1, 0),
        image.pixelColor(0, height - 1),
        image.pixelColor(width - 1, height - 1),
        image.pixelColor(width // 2, 0),
        image.pixelColor(width // 2, height - 1),
        image.pixelColor(0, height // 2),
        image.pixelColor(width - 1, height // 2),
    ]

    clustered: list[QColor] = []
    for color in samples:
        if not clustered:
            clustered.append(color)
            continue

        if any(_color_distance(color, seen) <= 10 for seen in clustered):
            continue
        clustered.append(color)

    if len(clustered) != 2:
        return None

    light, dark = sorted(
        clustered,
        key=lambda color: color.red() + color.green() + color.blue(),
        reverse=True,
    )
    if _color_distance(light, dark) < 8:
        return None
    return light, dark


def _estimate_alpha(channel_value: int, background_value: int) -> float:
    if channel_value == background_value:
        return 0.0
    if channel_value > background_value:
        return (channel_value - background_value) / max(1, 255 - background_value)
    return (background_value - channel_value) / max(1, background_value)


def _recover_foreground_from_background(
    image: QImage,
    background_a: QColor,
    background_b: QColor,
) -> QImage:
    recovered = QImage(image.size(), QImage.Format_ARGB32)
    recovered.fill(Qt.transparent)

    for y in range(image.height()):
        for x in range(image.width()):
            pixel = image.pixelColor(x, y)
            if pixel.alpha() < 255:
                recovered.setPixelColor(x, y, pixel)
                continue

            background = (
                background_a
                if _color_distance(pixel, background_a) <= _color_distance(pixel, background_b)
                else background_b
            )
            alpha = max(
                _estimate_alpha(pixel.red(), background.red()),
                _estimate_alpha(pixel.green(), background.green()),
                _estimate_alpha(pixel.blue(), background.blue()),
            )

            if alpha <= 0.01:
                recovered.setPixelColor(x, y, QColor(0, 0, 0, 0))
                continue

            alpha = min(1.0, alpha)

            def restore_channel(source: int, bg: int) -> int:
                restored = (source - (1.0 - alpha) * bg) / max(alpha, 1e-6)
                return max(0, min(255, int(round(restored))))

            recovered.setPixelColor(
                x,
                y,
                QColor(
                    restore_channel(pixel.red(), background.red()),
                    restore_channel(pixel.green(), background.green()),
                    restore_channel(pixel.blue(), background.blue()),
                    max(0, min(255, int(round(alpha * 255)))),
                ),
            )

    return recovered


def _remove_edge_connected_background(image: QImage, tolerance: int) -> QImage:
    width = image.width()
    height = image.height()
    background_samples = _sample_background_colors(image)
    visited: set[tuple[int, int]] = set()
    queue: deque[tuple[int, int]] = deque()

    def enqueue_if_background(x: int, y: int) -> None:
        if (x, y) in visited:
            return
        color = image.pixelColor(x, y)
        if any(_color_distance(color, sample) <= tolerance for sample in background_samples):
            visited.add((x, y))
            queue.append((x, y))

    for x in range(width):
        enqueue_if_background(x, 0)
        enqueue_if_background(x, height - 1)
    for y in range(height):
        enqueue_if_background(0, y)
        enqueue_if_background(width - 1, y)

    while queue:
        x, y = queue.popleft()
        color = image.pixelColor(x, y)
        color.setAlpha(0)
        image.setPixelColor(x, y, color)

        for next_x, next_y in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
            if 0 <= next_x < width and 0 <= next_y < height:
                enqueue_if_background(next_x, next_y)

    return image


def _prepare_pixmap(path: Path, spec: AnimationSpec) -> QPixmap:
    image = QImage(str(path))
    if image.isNull():
        return QPixmap()

    if spec.auto_remove_background and not image.hasAlphaChannel():
        image = image.convertToFormat(QImage.Format_ARGB32)
        checkerboard = _detect_checkerboard_background(image)
        if checkerboard:
            image = _recover_foreground_from_background(
                image,
                checkerboard[0],
                checkerboard[1],
            )
        else:
            image = _remove_edge_connected_background(image, spec.background_tolerance)

    return QPixmap.fromImage(image)


def _load_frames(action_dir: Path, spec: AnimationSpec) -> list[QPixmap]:
    frames: list[QPixmap] = []
    for path in sorted(action_dir.glob("*.png")):
        pixmap = _prepare_pixmap(path, spec)
        if not pixmap.isNull():
            frames.append(pixmap)
    return frames


def _mirror_frames(frames: list[QPixmap]) -> list[QPixmap]:
    transform = QTransform().scale(-1, 1)
    return [frame.transformed(transform, Qt.SmoothTransformation) for frame in frames]


def load_sprites(assets_dir: Path | None = None) -> SpriteSet:
    assets_dir = assets_dir or get_pet_assets_dir()
    spec = _load_manifest(assets_dir)
    animations: dict[str, list[QPixmap]] = {}

    for action in SUPPORTED_ACTIONS:
        action_dir = assets_dir / action
        if action_dir.exists():
            animations[action] = _load_frames(action_dir, spec)

    if WALK_LEFT not in animations and WALK_RIGHT in animations:
        animations[WALK_LEFT] = _mirror_frames(animations[WALK_RIGHT])

    if DRAGGED not in animations and IDLE in animations:
        animations[DRAGGED] = animations[IDLE]

    if CLICKED not in animations and IDLE in animations:
        animations[CLICKED] = animations[IDLE]

    if IDLE not in animations or not animations[IDLE]:
        raise FileNotFoundError(
            "Idle animation requires at least one valid PNG under assets/pet/idle"
        )

    for action, frames in list(animations.items()):
        if not frames and action != IDLE:
            animations.pop(action)

    return SpriteSet(animations=animations, spec=spec)
