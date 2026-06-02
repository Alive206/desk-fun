from __future__ import annotations

import random

from PySide6.QtCore import QObject, QRect, Signal

from .constants import (
    CLICKED,
    DEFAULT_IDLE_RANGE_MS,
    DEFAULT_SPEED_RANGE,
    DEFAULT_TICK_MS,
    DEFAULT_WALK_RANGE_MS,
    IDLE,
    WALK_LEFT,
    WALK_RIGHT,
)
from .models import MotionPlan, MovementSnapshot


class MovementController(QObject):
    movement_changed = Signal(MovementSnapshot)
    base_state_changed = Signal(str)

    def __init__(
        self,
        initial_x: int,
        initial_y: int,
        tick_ms: int = DEFAULT_TICK_MS,
        idle_range_ms: tuple[int, int] = DEFAULT_IDLE_RANGE_MS,
        walk_range_ms: tuple[int, int] = DEFAULT_WALK_RANGE_MS,
        speed_range: tuple[int, int] = DEFAULT_SPEED_RANGE,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self.tick_ms = tick_ms
        self.idle_range_ms = idle_range_ms
        self.walk_range_ms = walk_range_ms
        self.speed_range = speed_range

        self.x = initial_x
        self.y = initial_y
        self.direction = WALK_RIGHT
        self.moving = False
        self.speed = 0
        self.enabled = True
        self.dragging = False
        self.clicked_locked = False
        self._remaining_ms = 0
        self._choose_next_plan()

    def base_state(self) -> str:
        if self.dragging:
            return IDLE
        if self.clicked_locked:
            return CLICKED
        if not self.enabled or not self.moving:
            return IDLE
        return self.direction

    def set_enabled(self, enabled: bool) -> None:
        self.enabled = enabled
        if not enabled:
            self.moving = False
            self.speed = 0
            self.base_state_changed.emit(IDLE)
        else:
            self._choose_next_plan()

    def set_dragging(self, dragging: bool) -> None:
        self.dragging = dragging
        self.base_state_changed.emit(self.base_state())

    def set_clicked_locked(self, locked: bool) -> None:
        self.clicked_locked = locked
        if locked:
            self.moving = False
            self.speed = 0
        self.base_state_changed.emit(self.base_state())

    def move_to(self, x: int, y: int) -> None:
        self.x = x
        self.y = y
        self.movement_changed.emit(self.snapshot())

    def tick(self, bounds: QRect, pet_width: int) -> MovementSnapshot:
        if self.dragging or not self.enabled or self.clicked_locked:
            return self.snapshot()

        self._remaining_ms -= self.tick_ms
        if self._remaining_ms <= 0:
            self._choose_next_plan()

        if self.moving:
            delta = self.speed if self.direction == WALK_RIGHT else -self.speed
            next_x = self.x + delta
            min_x = bounds.left()
            max_x = bounds.right() - pet_width + 1

            if next_x <= min_x:
                next_x = min_x
                self.direction = WALK_RIGHT
            elif next_x >= max_x:
                next_x = max_x
                self.direction = WALK_LEFT

            self.x = next_x

        self.movement_changed.emit(self.snapshot())
        self.base_state_changed.emit(self.base_state())
        return self.snapshot()

    def snapshot(self) -> MovementSnapshot:
        return MovementSnapshot(
            x=self.x,
            y=self.y,
            direction=self.direction,
            moving=self.moving and self.enabled and not self.dragging,
        )

    def _choose_next_plan(self) -> None:
        plan = self._random_plan()
        self.moving = plan.moving
        self.direction = plan.direction
        self.speed = plan.speed
        self._remaining_ms = plan.duration_ms
        self.base_state_changed.emit(self.base_state())

    def _random_plan(self) -> MotionPlan:
        moving = random.choice((False, True))
        if not moving:
            return MotionPlan(
                moving=False,
                direction=self.direction,
                duration_ms=random.randint(*self.idle_range_ms),
                speed=0,
            )

        direction = random.choice((WALK_LEFT, WALK_RIGHT))
        return MotionPlan(
            moving=True,
            direction=direction,
            duration_ms=random.randint(*self.walk_range_ms),
            speed=random.randint(*self.speed_range),
        )
