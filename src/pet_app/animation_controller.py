from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtGui import QPixmap

from .constants import CLICKED, DRAGGED, IDLE
from .models import SpriteSet


class AnimationController(QObject):
    frame_changed = Signal(QPixmap)
    transient_finished = Signal(str)

    def __init__(self, sprite_set: SpriteSet, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._sprite_set = sprite_set
        self._state = IDLE
        self._frame_index = 0
        self._transient_state: str | None = None
        self._frozen = False
        self._base_state_getter: Callable[[], str] | None = None

        self._timer = QTimer(self)
        self._timer.setInterval(sprite_set.spec.frame_duration_ms)
        self._timer.timeout.connect(self._advance_frame)
        if sprite_set.spec.enable_frame_animation:
            self._timer.start()

        self.emit_current_frame()

    @property
    def state(self) -> str:
        return self._state

    def bind_base_state_getter(self, getter: Callable[[], str]) -> None:
        self._base_state_getter = getter

    def emit_current_frame(self) -> None:
        self.frame_changed.emit(self.current_frame())

    def current_frame(self) -> QPixmap:
        frames = self._get_frames(self._state)
        if not frames:
            frames = self._get_frames(IDLE)
        return frames[self._frame_index % len(frames)]

    def set_state(self, state: str) -> None:
        self._frozen = False
        if state == self._state and self._frame_index == 0:
            return
        self._state = state
        self._frame_index = 0
        self.emit_current_frame()

    def play_transient(self, state: str) -> None:
        self._frozen = False
        if state == DRAGGED:
            self.set_state(state)
            return
        self._transient_state = state
        self._state = state
        self._frame_index = 0
        self.emit_current_frame()

    def freeze_on_last_frame(self, state: str) -> None:
        frames = self._get_frames(state)
        self._transient_state = None
        self._frozen = True
        self._state = state
        self._frame_index = max(0, len(frames) - 1)
        self.emit_current_frame()

    def freeze_on_frame(self, state: str, frame_index: int) -> None:
        frames = self._get_frames(state)
        self._transient_state = None
        self._frozen = True
        self._state = state
        self._frame_index = max(0, min(frame_index, len(frames) - 1))
        self.emit_current_frame()

    def _advance_frame(self) -> None:
        if not self._sprite_set.spec.enable_frame_animation:
            return
        if self._frozen:
            return
        frames = self._get_frames(self._state)
        if not frames:
            return

        self._frame_index += 1

        if self._transient_state:
            if self._frame_index >= len(frames):
                finished_state = self._transient_state
                self._transient_state = None
                fallback = self._base_state_getter() if self._base_state_getter else IDLE
                self._state = fallback
                self._frame_index = 0
                self.transient_finished.emit(finished_state)
            self.emit_current_frame()
            return

        self._frame_index %= len(frames)
        self.emit_current_frame()

    def _get_frames(self, state: str) -> list[QPixmap]:
        return self._sprite_set.animations.get(state) or self._sprite_set.animations[IDLE]
