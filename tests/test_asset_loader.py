from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QImage
from pet_app.asset_loader import load_sprites
from pet_app.constants import DRAGGED, IDLE, WALK_LEFT, WALK_RIGHT


def write_png(path) -> None:
    image = QImage(8, 8, QImage.Format_ARGB32)
    image.fill(Qt.transparent)
    assert image.save(str(path), "PNG")


def write_opaque_background_png(path) -> None:
    image = QImage(16, 16, QImage.Format_RGB32)
    image.fill(QColor("#f5f5f5"))
    for x in range(4, 12):
        for y in range(4, 12):
            image.setPixelColor(x, y, QColor("#2563eb"))
    assert image.save(str(path), "PNG")


def write_checkerboard_composite_png(path) -> None:
    light = QColor("#fefefe")
    dark = QColor("#e8e8e8")
    foreground = QColor(64, 128, 255)
    image = QImage(16, 16, QImage.Format_RGB32)

    for y in range(16):
        for x in range(16):
            background = light if (x + y) % 2 == 0 else dark
            image.setPixelColor(x, y, background)

    for y in range(4, 12):
        for x in range(4, 12):
            alpha = 96 if x in (4, 11) or y in (4, 11) else 255
            background = light if (x + y) % 2 == 0 else dark
            blended = QColor(
                int(round((foreground.red() * alpha + background.red() * (255 - alpha)) / 255)),
                int(round((foreground.green() * alpha + background.green() * (255 - alpha)) / 255)),
                int(round((foreground.blue() * alpha + background.blue() * (255 - alpha)) / 255)),
            )
            image.setPixelColor(x, y, blended)

    assert image.save(str(path), "PNG")


def test_asset_loader_falls_back_to_mirrored_walk_left(tmp_path, qapp) -> None:
    idle_dir = tmp_path / IDLE
    walk_right_dir = tmp_path / WALK_RIGHT
    idle_dir.mkdir(parents=True)
    walk_right_dir.mkdir(parents=True)
    write_png(idle_dir / "000.png")
    write_png(walk_right_dir / "000.png")

    sprite_set = load_sprites(tmp_path)

    assert IDLE in sprite_set.animations
    assert WALK_LEFT in sprite_set.animations
    assert DRAGGED in sprite_set.animations


def test_asset_loader_removes_opaque_edge_background(tmp_path, qapp) -> None:
    idle_dir = tmp_path / IDLE
    idle_dir.mkdir(parents=True)
    write_opaque_background_png(idle_dir / "000.png")

    sprite_set = load_sprites(tmp_path)
    frame = sprite_set.animations[IDLE][0].toImage()

    assert frame.hasAlphaChannel() is True
    assert frame.pixelColor(0, 0).alpha() == 0
    assert frame.pixelColor(8, 8).alpha() == 255


def test_asset_loader_recovers_checkerboard_composite_background(tmp_path, qapp) -> None:
    idle_dir = tmp_path / IDLE
    idle_dir.mkdir(parents=True)
    write_checkerboard_composite_png(idle_dir / "000.png")

    sprite_set = load_sprites(tmp_path)
    frame = sprite_set.animations[IDLE][0].toImage()

    assert frame.pixelColor(0, 0).alpha() == 0
    assert frame.pixelColor(8, 8).alpha() >= 250
    assert 1 <= frame.pixelColor(4, 4).alpha() < 255
