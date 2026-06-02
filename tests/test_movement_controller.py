from __future__ import annotations

from PySide6.QtCore import QRect

from pet_app.constants import WALK_LEFT, WALK_RIGHT
from pet_app.movement_controller import MovementController


def test_movement_stays_within_bounds() -> None:
    controller = MovementController(initial_x=10, initial_y=10)
    controller.enabled = True
    controller.moving = True
    controller.direction = WALK_LEFT
    controller.speed = 20

    snapshot = controller.tick(QRect(0, 0, 200, 200), pet_width=64)

    assert snapshot.x >= 0
    assert controller.direction == WALK_RIGHT


def test_disabled_movement_reports_idle_snapshot() -> None:
    controller = MovementController(initial_x=50, initial_y=20)
    controller.set_enabled(False)

    snapshot = controller.tick(QRect(0, 0, 200, 200), pet_width=64)

    assert snapshot.x == 50
    assert snapshot.moving is False
