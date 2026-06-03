from __future__ import annotations

import random
from datetime import datetime

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
from PySide6.QtGui import QCloseEvent, QCursor
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QMenu,
    QSlider,
    QSystemTrayIcon,
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
        self._single_click_timer = QTimer(self)
        self._single_click_timer.setSingleShot(True)
        self._single_click_timer.setInterval(220)
        self._single_click_timer.timeout.connect(self._run_single_click)
        self._dialog_hide_timer = QTimer(self)
        self._dialog_hide_timer.setSingleShot(True)
        self._dialog_hide_timer.timeout.connect(self._hide_dialogue_bubble)
        self._special_anim: QPropertyAnimation | None = None

        self._mood_points = 55
        self._mood_decay_timer = QTimer(self)
        self._mood_decay_timer.setInterval(5000)
        self._mood_decay_timer.timeout.connect(self._decay_mood)
        self._mood_decay_timer.start()
        self._active_screen_geometry: QRect | None = None
        self._click_streak_count = 0
        self._click_streak_timer = QTimer(self)
        self._click_streak_timer.setSingleShot(True)
        self._click_streak_timer.setInterval(1200)
        self._click_streak_timer.timeout.connect(self._reset_click_streak)
        self._follow_mouse_active = False
        self._follow_mouse_timer = QTimer(self)
        self._follow_mouse_timer.setSingleShot(True)
        self._follow_mouse_timer.timeout.connect(self._stop_follow_mouse)
        self._cursor_sprite_mode = bool(self.settings.cursor_sprite_mode)
        self._movement_enabled_before_cursor_mode = self.settings.movement_enabled
        self._dialog_bubble = QLabel()
        self._dialog_bubble.setWindowFlags(
            Qt.ToolTip | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
        )
        self._dialog_bubble.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self._apply_dialog_bubble_theme()

        self.window.clicked.connect(self._queue_single_click)
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
                on_toggle_cursor_sprite_mode=self.toggle_cursor_sprite_mode,
                on_reset_position=self.reset_position,
                on_quit=self.quit,
                on_set_scale_percent=self.set_scale_percent,
                initial_scale_percent=self._current_scale_percent(),
                scale_min_percent=self.SCALE_MIN_PERCENT,
                scale_max_percent=self.SCALE_MAX_PERCENT,
                scale_step_percent=self.SCALE_STEP_PERCENT,
                cursor_sprite_mode_enabled=self._cursor_sprite_mode,
            )
            self.tray.update_movement_label(self.settings.movement_enabled)
            self.tray.show()

        self._apply_cursor_sprite_mode(self._cursor_sprite_mode, persist=False)
        self._on_frame_changed(self.animation.current_frame())
        self._apply_visibility()

    def _queue_single_click(self) -> None:
        self._single_click_timer.start()

    def _run_single_click(self) -> None:
        if self.movement.dragging:
            return
        self._click_pause_timer.stop()
        self.movement.set_clicked_locked(True)
        clicked_frames = self.sprites.animations.get(CLICKED) or []
        frame_index = random.randrange(len(clicked_frames)) if clicked_frames else 0
        self.animation.freeze_on_frame(CLICKED, frame_index)
        self._register_click_streak()
        if self._click_streak_count >= 3:
            self._trigger_click_combo()
        else:
            self._change_mood(6)
            self._show_dialogue(self._pick_click_dialogue())
        self._click_pause_timer.start(self.sprites.spec.click_pause_ms)

    def on_double_clicked(self) -> None:
        if self.movement.dragging:
            return
        self._single_click_timer.stop()
        self._click_pause_timer.stop()
        self.movement.set_clicked_locked(True)
        clicked_frames = self.sprites.animations.get(CLICKED) or []
        frame_index = random.randrange(len(clicked_frames)) if clicked_frames else 0
        self.animation.freeze_on_frame(CLICKED, frame_index)
        self._change_mood(12)
        self._show_dialogue(
            random.choice(self.sprites.spec.special_dialogues),
            duration_ms=self.sprites.spec.special_dialog_duration_ms,
        )
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
        cursor_mode_action = menu.addAction(
            "关闭鼠标精灵模式" if self._cursor_sprite_mode else "开启鼠标精灵模式"
        )
        follow_action = menu.addAction(
            "结束跟随" if self._follow_mouse_active else "跟随我（5秒）"
        )
        selected = menu.exec(global_pos)
        if selected == pet_action:
            self._interact_pet()
        elif selected == feed_action:
            self._interact_feed()
        elif selected == cursor_mode_action:
            self.toggle_cursor_sprite_mode()
        elif selected == follow_action:
            self._toggle_follow_mouse()

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
        if self._cursor_sprite_mode:
            self._movement_enabled_before_cursor_mode = self.settings.movement_enabled
            if self.tray:
                self.tray.update_movement_label(self.settings.movement_enabled)
            self._persist_settings()
            return
        if self.settings.movement_enabled:
            self.movement.set_clicked_locked(False)
            self._click_pause_timer.stop()
        self.movement.set_enabled(self.settings.movement_enabled)
        if self.tray:
            self.tray.update_movement_label(self.settings.movement_enabled)
        self._persist_settings()

    def toggle_cursor_sprite_mode(self) -> None:
        self._apply_cursor_sprite_mode(not self._cursor_sprite_mode, persist=True)

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
        self._apply_cursor_sprite_mode(False, persist=False)
        self._hide_dialogue_bubble()
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
        if self._cursor_sprite_mode:
            self._cursor_sprite_follow_step()
            return
        if self.movement.dragging:
            # Do not clamp while user is dragging; allow free cross-screen drag.
            self.settings.position_x = self.window.x()
            self.settings.position_y = self.window.y()
            return
        if self._follow_mouse_active:
            self._follow_mouse_step()
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

    def _show_dialogue(self, text: str, duration_ms: int | None = None) -> None:
        if not text:
            return
        self._apply_dialog_bubble_theme()
        timeout = (
            self.sprites.spec.click_dialog_duration_ms
            if duration_ms is None
            else max(1, int(duration_ms))
        )
        self._dialog_bubble.setText(text)
        self._dialog_bubble.adjustSize()
        tip_pos = self.window.mapToGlobal(QPoint(self.window.width() // 2, 0))
        x = tip_pos.x() - self._dialog_bubble.width() // 2
        y = tip_pos.y() - self._dialog_bubble.height() - 14
        bounds = self._movement_bounds()
        x = min(max(x, bounds.left()), bounds.right() - self._dialog_bubble.width() + 1)
        y = min(max(y, bounds.top()), bounds.bottom() - self._dialog_bubble.height() + 1)
        self._dialog_bubble.move(x, y)
        self._dialog_bubble.show()
        self._dialog_bubble.raise_()
        self._dialog_hide_timer.start(timeout)

    def _hide_dialogue_bubble(self) -> None:
        self._dialog_hide_timer.stop()
        self._dialog_bubble.hide()

    def _apply_dialog_bubble_theme(self) -> None:
        window_color = self.qt_app.palette().window().color()
        is_dark = window_color.lightness() < 128
        if is_dark:
            style = (
                "QLabel {"
                "background: rgba(30, 30, 30, 220);"
                "color: white;"
                "border: 1px solid rgba(255, 255, 255, 60);"
                "border-radius: 8px;"
                "padding: 6px 10px;"
                "}"
            )
        else:
            style = (
                "QLabel {"
                "background: rgba(255, 250, 245, 235);"
                "color: rgb(45, 45, 45);"
                "border: 1px solid rgba(120, 120, 120, 90);"
                "border-radius: 8px;"
                "padding: 6px 10px;"
                "}"
            )
        self._dialog_bubble.setStyleSheet(style)

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
        time_pool = self._pick_time_click_dialogues()
        if time_pool:
            return random.choice(time_pool)

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

    def _play_special_bounce(self, lift_px: int = 28, duration_ms: int = 280) -> None:
        start_pos = self.window.pos()
        peak_pos = QPoint(start_pos.x(), start_pos.y() - lift_px)
        anim = QPropertyAnimation(self.window, b"pos", self)
        anim.setDuration(duration_ms)
        anim.setEasingCurve(QEasingCurve.InOutQuad)
        anim.setKeyValueAt(0.0, start_pos)
        anim.setKeyValueAt(0.5, peak_pos)
        anim.setKeyValueAt(1.0, start_pos)
        anim.finished.connect(self._persist_position)
        anim.start()
        self._special_anim = anim

    def _pick_time_click_dialogues(self) -> list[str]:
        hour = datetime.now().hour
        if 5 <= hour < 12:
            return self.sprites.spec.morning_click_dialogues
        if 12 <= hour < 18:
            return self.sprites.spec.afternoon_click_dialogues
        return self.sprites.spec.evening_click_dialogues

    def _register_click_streak(self) -> None:
        self._click_streak_count += 1
        self._click_streak_timer.start()

    def _reset_click_streak(self) -> None:
        self._click_streak_count = 0

    def _trigger_click_combo(self) -> None:
        self._change_mood(18)
        combo_lines = ["三连击彩蛋触发！", "手速很快嘛！", "这波操作我给满分！"]
        self._show_dialogue(random.choice(combo_lines))
        self._play_special_bounce(lift_px=84, duration_ms=420)
        self._reset_click_streak()
        self._click_streak_timer.stop()

    def _toggle_follow_mouse(self) -> None:
        if self._follow_mouse_active:
            self._stop_follow_mouse()
        else:
            self._start_follow_mouse(5000)

    def _start_follow_mouse(self, duration_ms: int) -> None:
        self._follow_mouse_active = True
        self._show_dialogue("跟上你啦，5秒！")
        self._follow_mouse_timer.start(max(500, duration_ms))

    def _stop_follow_mouse(self) -> None:
        self._follow_mouse_active = False
        self._follow_mouse_timer.stop()

    def _follow_mouse_step(self) -> None:
        cursor = QCursor.pos()
        current = self.window.pos()
        target_x = cursor.x() - self.window.width() // 2
        target_y = cursor.y() - self.window.height() // 2
        max_step = 28
        dx = max(-max_step, min(max_step, target_x - current.x()))
        dy = max(-max_step, min(max_step, target_y - current.y()))
        next_x = current.x() + dx
        next_y = current.y() + dy
        bounds = self._movement_bounds()
        next_x = min(max(next_x, bounds.left()), bounds.right() - self.window.width() + 1)
        next_y = min(max(next_y, bounds.top()), bounds.bottom() - self.window.height() + 1)
        self.window.move(next_x, next_y)
        self.movement.move_to(next_x, next_y)
        self.settings.position_x = next_x
        self.settings.position_y = next_y

    def _apply_cursor_sprite_mode(self, enabled: bool, persist: bool) -> None:
        if enabled == self._cursor_sprite_mode and not persist:
            return

        self._cursor_sprite_mode = enabled
        self.settings.cursor_sprite_mode = enabled
        if enabled:
            self._movement_enabled_before_cursor_mode = self.settings.movement_enabled
            self.settings.movement_enabled = False
            self.movement.set_enabled(False)
            self._click_pause_timer.stop()
            self.movement.set_clicked_locked(False)
            self._follow_mouse_active = False
            self._follow_mouse_timer.stop()
            self.qt_app.setOverrideCursor(Qt.BlankCursor)
            self._show_dialogue("鼠标精灵模式已开启")
        else:
            if self.qt_app.overrideCursor() is not None:
                self.qt_app.restoreOverrideCursor()
            self.settings.movement_enabled = self._movement_enabled_before_cursor_mode
            self.movement.set_enabled(self.settings.movement_enabled)
            self._show_dialogue("鼠标精灵模式已关闭")

        if self.tray:
            self.tray.update_movement_label(self.settings.movement_enabled)
            self.tray.update_cursor_sprite_mode_label(enabled)
        if persist:
            self._persist_settings()

    def _cursor_sprite_follow_step(self) -> None:
        cursor = QCursor.pos()
        bounds = self._movement_bounds()
        next_x = cursor.x() - self.window.width() // 2
        next_y = cursor.y() - self.window.height() // 2
        next_x = min(max(next_x, bounds.left()), bounds.right() - self.window.width() + 1)
        next_y = min(max(next_y, bounds.top()), bounds.bottom() - self.window.height() + 1)
        self.window.move(next_x, next_y)
        self.movement.move_to(next_x, next_y)
        self.settings.position_x = next_x
        self.settings.position_y = next_y
