from __future__ import annotations

import random

from PySide6.QtCore import (
    QAbstractAnimation,
    QEasingCurve,
    QPropertyAnimation,
    QObject,
    QPoint,
    QRect,
    Qt,
    QTimer,
)
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QMenu,
    QSlider,
    QSystemTrayIcon,
    QToolTip,
    QWidget,
    QWidgetAction,
)

from .animation_controller import AnimationController
from .asset_loader import load_sprites
from .constants import CLICKED, DRAGGED, IDLE, WALK_LEFT, WALK_RIGHT
from .models import AppSettings
from .movement_controller import MovementController
from .pet_window import PetWindow
from .settings import save_settings
from .tray_controller import TrayController


class DesktopPetApp(QObject):
    SCALE_MIN_PERCENT = 60
    SCALE_MAX_PERCENT = 220
    SCALE_STEP_PERCENT = 5

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
        self.settings.scale = self._snap_scale_percent(
            int(round((self.settings.scale or self.sprites.spec.default_scale) * 100))
        ) / 100.0

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
        self._special_anim: QPropertyAnimation | None = None

        self._mood_points = 55
        self._mood_decay_timer = QTimer(self)
        self._mood_decay_timer.setInterval(5000)
        self._mood_decay_timer.timeout.connect(self._decay_mood)
        self._mood_decay_timer.start()
        self._active_screen_geometry: QRect | None = None

        self.window.clicked.connect(self.on_clicked)
        self.window.double_clicked.connect(self.on_double_clicked)
        self.window.right_clicked.connect(self.on_right_clicked)
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
                on_set_scale_percent=self.set_scale_percent,
                initial_scale_percent=self._current_scale_percent(),
                scale_min_percent=self.SCALE_MIN_PERCENT,
                scale_max_percent=self.SCALE_MAX_PERCENT,
                scale_step_percent=self.SCALE_STEP_PERCENT,
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
        self._change_mood(6)
        self._show_dialogue(self._pick_click_dialogue())
        self._click_pause_timer.start(self.sprites.spec.click_pause_ms)

    def on_double_clicked(self) -> None:
        if self.movement.dragging:
            return
        self._click_pause_timer.stop()
        self.movement.set_clicked_locked(True)
        clicked_frames = self.sprites.animations.get(CLICKED) or []
        frame_index = random.randrange(len(clicked_frames)) if clicked_frames else 0
        self.animation.freeze_on_frame(CLICKED, frame_index)
        self._change_mood(12)
        self._show_dialogue(random.choice(self.sprites.spec.special_dialogues))
        self._play_special_bounce()
        self._click_pause_timer.start(max(400, self.sprites.spec.click_pause_ms))

    def on_right_clicked(self, global_pos: QPoint) -> None:
        menu = QMenu(self.window)
        mood_action = menu.addAction(
            f"当前情绪：{self._mood_state_label()} ({self._mood_points})"
        )
        mood_action.setEnabled(False)
        menu.addSeparator()

        scale_menu = menu.addMenu("缩放比例")
        scale_value_label = QLabel(f"{self._current_scale_percent()}%")
        scale_slider = QSlider(Qt.Horizontal)
        scale_slider.setMinimum(self.SCALE_MIN_PERCENT)
        scale_slider.setMaximum(self.SCALE_MAX_PERCENT)
        scale_slider.setSingleStep(self.SCALE_STEP_PERCENT)
        scale_slider.setPageStep(self.SCALE_STEP_PERCENT)
        scale_slider.setTickInterval(self.SCALE_STEP_PERCENT)
        scale_slider.setTickPosition(QSlider.TicksBelow)
        scale_slider.setValue(self._current_scale_percent())
        scale_slider.valueChanged.connect(self.set_scale_percent)

        scale_container = QWidget(menu)
        scale_layout = QHBoxLayout(scale_container)
        scale_layout.setContentsMargins(8, 4, 8, 4)
        scale_layout.setSpacing(8)
        scale_layout.addWidget(QLabel("缩放"))
        scale_layout.addWidget(scale_slider, 1)
        scale_layout.addWidget(scale_value_label)

        def _sync_scale_label(value: int) -> None:
            scale_value_label.setText(f"{self._snap_scale_percent(value)}%")

        scale_slider.valueChanged.connect(_sync_scale_label)
        scale_action = QWidgetAction(scale_menu)
        scale_action.setDefaultWidget(scale_container)
        scale_menu.addAction(scale_action)

        pet_action = menu.addAction("摸摸")
        feed_action = menu.addAction("投喂")
        selected = menu.exec(global_pos)
        if selected == pet_action:
            self._interact_pet()
        elif selected == feed_action:
            self._interact_feed()

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
        self._active_screen_geometry = self._pick_screen_for_window()
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
        bounds = self._movement_bounds()
        x = bounds.right() - self.window.width() - 48
        y = bounds.bottom() - self.window.height()
        self.window.move(x, y)
        self.movement.move_to(x, y)
        self._persist_position()

    def set_scale(self, scale: float) -> None:
        self.settings.scale = self._snap_scale_percent(int(round(float(scale) * 100))) / 100.0
        self._on_frame_changed(self.animation.current_frame())
        if self.tray:
            self.tray.update_scale_percent(self._current_scale_percent())
        self._persist_settings()

    def set_scale_percent(self, percent: int) -> None:
        snapped = self._snap_scale_percent(percent)
        self.settings.scale = snapped / 100.0
        self._on_frame_changed(self.animation.current_frame())
        if self.tray:
            self.tray.update_scale_percent(snapped)
        self._persist_settings()

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
        if self._special_anim and self._special_anim.state() == QAbstractAnimation.Running:
            return
        if self.movement.dragging:
            # Do not clamp while user is dragging; allow free cross-screen drag.
            self.settings.position_x = self.window.x()
            self.settings.position_y = self.window.y()
            return
        if self._active_screen_geometry is None:
            self._active_screen_geometry = self._pick_screen_for_window()

        self._maybe_handoff_screen()
        bounds = self._active_screen_geometry or self._movement_bounds()
        snapshot = self.movement.tick(bounds, self.window.width())
        target_x = min(
            max(snapshot.x, bounds.left()),
            bounds.right() - self.window.width() + 1,
        )
        target_y = min(
            max(self.window.y(), bounds.top()),
            bounds.bottom() - self.window.height() + 1,
        )
        self.window.move(target_x, target_y)
        self.settings.position_x = target_x
        self.settings.position_y = target_y

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
        self.window.set_frame(frame, self._current_scale())

    def _persist_position(self) -> None:
        self.settings.position_x = self.window.x()
        self.settings.position_y = self.window.y()
        self._persist_settings()

    def _persist_settings(self) -> None:
        save_settings(self.settings)

    def _current_scale(self) -> float:
        return self._current_scale_percent() / 100.0

    def _current_scale_percent(self) -> int:
        return self._snap_scale_percent(
            int(round((self.settings.scale or self.sprites.spec.default_scale) * 100))
        )

    def _snap_scale_percent(self, percent: int) -> int:
        clamped = max(self.SCALE_MIN_PERCENT, min(self.SCALE_MAX_PERCENT, int(percent)))
        steps = round((clamped - self.SCALE_MIN_PERCENT) / self.SCALE_STEP_PERCENT)
        return self.SCALE_MIN_PERCENT + steps * self.SCALE_STEP_PERCENT

    def _movement_bounds(self) -> QRect:
        screens = self.qt_app.screens()
        if not screens:
            return self.qt_app.primaryScreen().availableGeometry()

        union = QRect(screens[0].availableGeometry())
        for screen in screens[1:]:
            union = union.united(screen.availableGeometry())
        return union

    def _pick_screen_for_window(self) -> QRect:
        screens = self.qt_app.screens()
        if not screens:
            return self.qt_app.primaryScreen().availableGeometry()

        center = self.window.geometry().center()
        containing = [screen.availableGeometry() for screen in screens if screen.availableGeometry().contains(center)]
        if containing:
            return QRect(containing[0])

        return QRect(
            min(
                (screen.availableGeometry() for screen in screens),
                key=lambda g: abs(g.center().x() - center.x()) + abs(g.center().y() - center.y()),
            )
        )

    def _maybe_handoff_screen(self) -> None:
        if not self._active_screen_geometry:
            return

        current = self._active_screen_geometry
        width = self.window.width()
        height = self.window.height()
        x = self.window.x()
        y = self.window.y()
        direction = self.movement.direction

        target: QRect | None = None
        if direction == WALK_RIGHT and x + width >= current.right():
            target = self._find_neighbor_screen(current, WALK_RIGHT, y, height)
            if target:
                x = target.left()
        elif direction == WALK_LEFT and x <= current.left():
            target = self._find_neighbor_screen(current, WALK_LEFT, y, height)
            if target:
                x = target.right() - width + 1

        if not target:
            return

        y = min(max(y, target.top()), target.bottom() - height + 1)
        self._active_screen_geometry = target
        self.window.move(x, y)
        self.movement.move_to(x, y)

    def _find_neighbor_screen(
        self,
        current: QRect,
        direction: str,
        y: int,
        height: int,
    ) -> QRect | None:
        screens = [screen.availableGeometry() for screen in self.qt_app.screens()]
        if not screens:
            return None

        vertical_overlap = lambda g: min(y + height, g.bottom() + 1) - max(y, g.top()) > 0
        if direction == WALK_RIGHT:
            candidates = [g for g in screens if g.left() > current.right() and vertical_overlap(g)]
            if not candidates:
                candidates = [g for g in screens if g.left() > current.right()]
            return min(candidates, key=lambda g: g.left(), default=None)

        candidates = [g for g in screens if g.right() < current.left() and vertical_overlap(g)]
        if not candidates:
            candidates = [g for g in screens if g.right() < current.left()]
        return max(candidates, key=lambda g: g.right(), default=None)

    def _release_clicked_state(self) -> None:
        if not self.movement.clicked_locked:
            return
        self.movement.set_clicked_locked(False)
        self._on_base_state_changed(self.movement.base_state())

    def _show_dialogue(self, text: str) -> None:
        if not text:
            return
        tip_pos = self.window.mapToGlobal(QPoint(self.window.width() // 2, 0))
        QToolTip.showText(
            tip_pos,
            text,
            self.window,
            self.window.rect(),
            self.sprites.spec.click_dialog_duration_ms,
        )

    def _change_mood(self, delta: int) -> None:
        self._mood_points = max(0, min(100, self._mood_points + delta))

    def _decay_mood(self) -> None:
        self._change_mood(-2)

    def _mood_state(self) -> str:
        if self._mood_points >= 70:
            return "happy"
        if self._mood_points <= 30:
            return "sleepy"
        return "bored"

    def _mood_state_label(self) -> str:
        mood = self._mood_state()
        if mood == "happy":
            return "开心"
        if mood == "sleepy":
            return "困困"
        return "一般"

    def _pick_click_dialogue(self) -> str:
        mood = self._mood_state()
        if mood == "happy":
            pool = self.sprites.spec.happy_click_dialogues
        elif mood == "sleepy":
            pool = self.sprites.spec.sleepy_click_dialogues
        else:
            pool = self.sprites.spec.bored_click_dialogues
        if not pool:
            pool = self.sprites.spec.click_dialogues
        return random.choice(pool) if pool else ""

    def _interact_pet(self) -> None:
        self._change_mood(10)
        self._show_dialogue(random.choice(self.sprites.spec.pet_dialogues))

    def _interact_feed(self) -> None:
        self._change_mood(20)
        self._show_dialogue(random.choice(self.sprites.spec.feed_dialogues))

    def _play_special_bounce(self) -> None:
        start_pos = self.window.pos()
        peak_pos = QPoint(start_pos.x(), start_pos.y() - 28)
        anim = QPropertyAnimation(self.window, b"pos", self)
        anim.setDuration(280)
        anim.setEasingCurve(QEasingCurve.InOutQuad)
        anim.setKeyValueAt(0.0, start_pos)
        anim.setKeyValueAt(0.5, peak_pos)
        anim.setKeyValueAt(1.0, start_pos)
        anim.finished.connect(self._persist_position)
        anim.start()
        self._special_anim = anim
