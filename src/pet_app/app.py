from __future__ import annotations

import random

from PySide6.QtCore import QObject, QTimer
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import QApplication, QSystemTrayIcon

from .animation_controller import AnimationController
from .asset_loader import load_sprites
from .constants import CLICKED, DRAGGED, IDLE
from .models import AppSettings
from .movement_controller import MovementController
from .pet_window import PetWindow
from .settings import save_settings
from .tray_controller import TrayController


class DesktopPetApp(QObject):
    def __init__(
        self,
        qt_app: QApplication,
        settings: AppSettings,
        enable_tray: bool = True,
    ) -> None:
        super().__init__()
        self.qt_app = qt_app
        self.settings = settings
        self.sprites = load_sprites()

        self.window = PetWindow(
            hitbox_padding=self.sprites.spec.hitbox_padding,
            max_display_size=self.sprites.spec.max_display_size,
            drag_hold_ms=self.sprites.spec.drag_hold_ms,
        )
        self.window.close_requested.connect(self.on_window_close_requested)
        self.window.move(settings.position_x, settings.position_y)

        self.movement = MovementController(
            initial_x=settings.position_x,
            initial_y=settings.position_y,
        )
        self.movement.set_enabled(settings.movement_enabled)

        self.animation = AnimationController(self.sprites)
        self.animation.bind_base_state_getter(self.movement.base_state)
        self._click_pause_timer = QTimer(self)
        self._click_pause_timer.setSingleShot(True)
        self._click_pause_timer.timeout.connect(self._release_clicked_state)

        self.window.clicked.connect(self.on_clicked)
        self.window.drag_started.connect(self.on_drag_started)
        self.window.drag_moved.connect(self.on_drag_moved)
        self.window.drag_finished.connect(self.on_drag_finished)
        self.animation.frame_changed.connect(self._on_frame_changed)
        self.movement.base_state_changed.connect(self._on_base_state_changed)

        self._timer = QTimer(self)
        self._timer.setInterval(self.movement.tick_ms)
        self._timer.timeout.connect(self._tick)
        self._timer.start()

        self.tray: TrayController | None = None
        if enable_tray and QSystemTrayIcon.isSystemTrayAvailable():
            self.tray = TrayController(
                on_toggle_visible=self.toggle_visible,
                on_toggle_movement=self.toggle_movement,
                on_reset_position=self.reset_position,
                on_quit=self.quit,
            )
            self.tray.update_movement_label(self.settings.movement_enabled)
            self.tray.show()

        self._on_frame_changed(self.animation.current_frame())
        self._apply_visibility()

    def on_clicked(self) -> None:
        if self.movement.dragging:
            return
        self._click_pause_timer.stop()
        self.movement.set_clicked_locked(True)
        clicked_frames = self.sprites.animations.get(CLICKED) or []
        frame_index = random.randrange(len(clicked_frames)) if clicked_frames else 0
        self.animation.freeze_on_frame(CLICKED, frame_index)
        self._click_pause_timer.start(self.sprites.spec.click_pause_ms)

    def on_drag_started(self) -> None:
        self._click_pause_timer.stop()
        self.movement.set_clicked_locked(False)
        self.movement.set_dragging(True)
        self.animation.set_state(DRAGGED)

    def on_drag_moved(self, x: int, y: int) -> None:
        self.movement.move_to(x, y)
        self._persist_position()

    def on_drag_finished(self) -> None:
        self.movement.set_dragging(False)
        self._persist_position()
        self._on_base_state_changed(self.movement.base_state())

    def toggle_visible(self) -> None:
        self.settings.visible = not self.window.isVisible()
        self._apply_visibility()
        self._persist_settings()

    def toggle_movement(self) -> None:
        self.settings.movement_enabled = not self.settings.movement_enabled
        if self.settings.movement_enabled:
            self.movement.set_clicked_locked(False)
            self._click_pause_timer.stop()
        self.movement.set_enabled(self.settings.movement_enabled)
        if self.tray:
            self.tray.update_movement_label(self.settings.movement_enabled)
        self._persist_settings()

    def reset_position(self) -> None:
        self._click_pause_timer.stop()
        self.movement.set_clicked_locked(False)
        bounds = self.qt_app.primaryScreen().availableGeometry()
        x = bounds.right() - self.window.width() - 48
        y = bounds.bottom() - self.window.height()
        self.window.move(x, y)
        self.movement.move_to(x, y)
        self._persist_position()

    def quit(self) -> None:
        self._persist_settings()
        if self.tray:
            self.tray.hide()
        self.qt_app.quit()

    def on_window_close_requested(self, event: QCloseEvent) -> None:
        self.settings.visible = False
        self.window.hide()
        self._persist_settings()
        event.ignore()

    def _tick(self) -> None:
        bounds = self.qt_app.primaryScreen().availableGeometry()
        snapshot = self.movement.tick(bounds, self.window.width())
        clamped_y = min(
            max(self.window.y(), bounds.top()),
            bounds.bottom() - self.window.height() + 1,
        )
        self.window.move(snapshot.x, clamped_y)
        self.settings.position_x = snapshot.x
        self.settings.position_y = clamped_y

    def _apply_visibility(self) -> None:
        if self.settings.visible:
            self.window.show()
        else:
            self.window.hide()

    def _on_base_state_changed(self, state: str) -> None:
        if self.animation.state == CLICKED and self.movement.clicked_locked:
            return
        self.animation.set_state(state or IDLE)

    def _on_frame_changed(self, frame) -> None:
        self.window.set_frame(frame, self.settings.scale or self.sprites.spec.default_scale)

    def _persist_position(self) -> None:
        self.settings.position_x = self.window.x()
        self.settings.position_y = self.window.y()
        self._persist_settings()

    def _persist_settings(self) -> None:
        save_settings(self.settings)

    def _release_clicked_state(self) -> None:
        if not self.movement.clicked_locked:
            return
        self.movement.set_clicked_locked(False)
        self._on_base_state_changed(self.movement.base_state())
