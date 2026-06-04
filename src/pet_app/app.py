from __future__ import annotations

import random
import sys
import urllib.error
import urllib.request
import json
from datetime import datetime
from pathlib import Path
import shutil

from PySide6.QtCore import (
    QAbstractAnimation,
    QEvent,
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
    QMessageBox,
    QToolTip,
    QWidget,
    QWidgetAction,
    QVBoxLayout,
)

from .animation_controller import AnimationController
from .asset_loader import load_sprites
from .constants import CLICKED, DRAGGED, IDLE, WALK_LEFT, WALK_RIGHT
from .models import AppSettings
from .movement_controller import MovementController
from .pet_window import PetWindow
from .settings import save_settings
from .tray_controller import TrayController

if sys.platform == "win32":
    import winreg


class DesktopPetApp(QObject):
    SCALE_MIN_PERCENT = 60
    SCALE_MAX_PERCENT = 220
    SCALE_STEP_PERCENT = 5
    POMODORO_MINUTES_MIN = 1
    POMODORO_MINUTES_MAX = 90

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
        self.settings.autostart_enabled = self._is_autostart_enabled_in_system()
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
        self._stable_dialog_bubble = QLabel()
        self._stable_dialog_bubble.setWindowFlags(
            Qt.ToolTip | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
        )
        self._stable_dialog_bubble.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self._stable_dialog_bubble.setStyleSheet(
            "QLabel {"
            "background: rgb(255, 255, 220);"
            "color: rgb(30, 30, 30);"
            "border: 1px solid rgb(120, 120, 120);"
            "border-radius: 6px;"
            "padding: 4px 8px;"
            "}"
        )
        self._focus_display = QWidget()
        self._focus_display.setWindowFlags(
            Qt.ToolTip | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
        )
        self._focus_display.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self._focus_display.setObjectName("FocusPanel")
        self._focus_display.setMinimumSize(430, 312)
        self._focus_display.setStyleSheet(
            "#FocusPanel {"
            "background: qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 rgb(5,16,35), stop:1 rgb(3,10,22));"
            "border: 1px solid rgb(16, 42, 78);"
            "border-radius: 14px;"
            "}"
            "#FocusCard {background: rgb(8,20,42); border: 1px solid rgb(18,46,85); border-radius: 12px;}"
            "#FocusRing {background: rgb(7,18,36); border: 6px solid rgb(88,220,255); border-radius: 110px;}"
            "#FocusTimer {font-family: Consolas, 'Courier New', monospace; font-size: 48px; font-weight: 700; color: rgb(233,245,255); border:none;}"
            "#FocusRingStatus {font-size: 16px; color: rgb(95,193,255); border:none;}"
            "#FocusRingSub {font-size: 14px; color: rgb(170,200,230); border:none;}"
            "#FocusRingCaption {font-size: 15px; color: rgb(144,170,205); border:none;}"
            "#FocusBadge {font-size: 16px; color: rgb(93,242,214); border: 1px solid rgb(36,148,130); border-radius: 10px; background: rgb(5,50,58); padding: 2px 8px;}"
            "#FocusNote {font-size: 13px; color: rgb(172,196,226); border:none;}"
            "#FocusMainButton {font-size: 16px; font-weight: 700; color: rgb(220,240,255); border: 1px solid rgb(59,135,255); border-radius: 16px; background: rgb(29,84,193); padding: 6px 10px;}"
            "#FocusSideButton {font-size: 15px; color: rgb(220,240,255); border: 1px solid rgb(41,78,123); border-radius: 16px; background: rgb(20,44,78); padding: 6px 10px;}"
            "#FocusSectionTitle {font-size: 24px; font-weight: 700; color: rgb(205,231,255); border:none;}"
            "#FocusStatItem {font-size: 19px; color: rgb(176,210,242); border:none;}"
            "#FocusStatValue {font-size: 22px; font-weight: 700; color: rgb(216,239,255); border:none;}"
            "#FocusEnergyValue {font-size: 54px; font-weight: 700; color: rgb(85,245,238); border:none;}"
            "#FocusEnergyLabel {font-size: 15px; color: rgb(119,225,223); border:none;}"
            "#FocusHideButton {font-size: 14px; color: rgb(170,210,250); border: 1px solid rgb(30,70,120); border-radius: 10px; background: rgb(13,34,63); padding: 2px 7px;}"
        )
        root = QVBoxLayout(self._focus_display)
        root.setContentsMargins(10, 8, 10, 8)
        root.setSpacing(6)

        top_row = QHBoxLayout()
        top_row.setContentsMargins(0, 0, 0, 0)
        top_row.addStretch(1)
        self._focus_hide_button = QLabel("隐藏")
        self._focus_hide_button.setObjectName("FocusHideButton")
        self._focus_hide_button.setAlignment(Qt.AlignCenter)
        top_row.addWidget(self._focus_hide_button, alignment=Qt.AlignRight)
        root.addLayout(top_row)

        middle_layout = QHBoxLayout()
        middle_layout.setSpacing(6)
        root.addLayout(middle_layout, 1)

        left_card = QWidget()
        left_card.setObjectName("FocusCard")
        left_layout = QVBoxLayout(left_card)
        left_layout.setContentsMargins(8, 8, 8, 8)
        left_layout.setSpacing(6)
        self._focus_ring = QWidget()
        self._focus_ring.setObjectName("FocusRing")
        self._focus_ring.setFixedSize(206, 206)
        ring_layout = QVBoxLayout(self._focus_ring)
        ring_layout.setContentsMargins(12, 12, 12, 12)
        ring_layout.setSpacing(0)
        ring_layout.setAlignment(Qt.AlignCenter)
        self._focus_ring_status = QLabel("• 专注中 •")
        self._focus_ring_status.setObjectName("FocusRingStatus")
        self._focus_ring_sub = QLabel("深度工作")
        self._focus_ring_sub.setObjectName("FocusRingSub")
        self._focus_timer = QLabel("25:00")
        self._focus_timer.setObjectName("FocusTimer")
        self._focus_timer.setAlignment(Qt.AlignCenter)
        self._focus_ring_caption = QLabel("剩余时间")
        self._focus_ring_caption.setObjectName("FocusRingCaption")
        self._focus_badge = QLabel("进行中")
        self._focus_badge.setObjectName("FocusBadge")
        self._focus_badge.setAlignment(Qt.AlignCenter)
        ring_layout.addWidget(self._focus_ring_status, alignment=Qt.AlignCenter)
        ring_layout.addWidget(self._focus_ring_sub, alignment=Qt.AlignCenter)
        ring_layout.addWidget(self._focus_timer, alignment=Qt.AlignCenter)
        ring_layout.addWidget(self._focus_ring_caption, alignment=Qt.AlignCenter)
        ring_layout.addWidget(self._focus_badge, alignment=Qt.AlignCenter)
        left_layout.addWidget(self._focus_ring, alignment=Qt.AlignCenter)
        self._focus_note = QLabel("保持专注，你正在完成重要的事")
        self._focus_note.setObjectName("FocusNote")
        self._focus_note.setAlignment(Qt.AlignCenter)
        left_layout.addWidget(self._focus_note)
        button_row = QHBoxLayout()
        self._focus_main_button = QLabel("▌▌  暂停专注")
        self._focus_main_button.setObjectName("FocusMainButton")
        self._focus_main_button.setAlignment(Qt.AlignCenter)
        self._focus_side_button = QLabel("■")
        self._focus_side_button.setObjectName("FocusSideButton")
        self._focus_side_button.setAlignment(Qt.AlignCenter)
        self._focus_side_button.setFixedWidth(56)
        button_row.addWidget(self._focus_main_button, 1)
        button_row.addWidget(self._focus_side_button)
        left_layout.addLayout(button_row)
        middle_layout.addWidget(left_card, 3)

        right_col = QVBoxLayout()
        right_col.setSpacing(8)
        middle_layout.addLayout(right_col, 2)

        right_stats = QWidget()
        right_stats.setObjectName("FocusCard")
        right_stats_layout = QVBoxLayout(right_stats)
        right_stats_layout.setContentsMargins(8, 8, 8, 8)
        right_stats_layout.setSpacing(4)
        right_stats_layout.addWidget(self._new_focus_label("今日数据", "FocusSectionTitle"))
        self._focus_weather = self._new_focus_label("天气  --", "FocusStatItem")
        self._focus_stat_total = self._new_focus_label("专注时长  0h 00m", "FocusStatItem")
        self._focus_stat_cycles = self._new_focus_label("专注次数  0次", "FocusStatItem")
        self._focus_stat_avg = self._new_focus_label("平均专注时长  0m", "FocusStatItem")
        self._focus_stat_achieve = self._new_focus_label("今日成就  稳定推进者", "FocusStatValue")
        right_stats_layout.addWidget(self._focus_weather)
        right_stats_layout.addWidget(self._focus_stat_total)
        right_stats_layout.addWidget(self._focus_stat_cycles)
        right_stats_layout.addWidget(self._focus_stat_avg)
        right_stats_layout.addWidget(self._focus_stat_achieve)
        right_col.addWidget(right_stats)

        energy = QWidget()
        energy.setObjectName("FocusCard")
        energy_layout = QVBoxLayout(energy)
        energy_layout.setContentsMargins(8, 8, 8, 8)
        energy_layout.setSpacing(4)
        energy_layout.addWidget(self._new_focus_label("专注力", "FocusSectionTitle"))
        self._focus_energy_value = self._new_focus_label("85", "FocusEnergyValue")
        self._focus_energy_value.setAlignment(Qt.AlignCenter)
        self._focus_energy_label = self._new_focus_label("当前专注力良好", "FocusEnergyLabel")
        self._focus_energy_label.setAlignment(Qt.AlignCenter)
        self._focus_energy_spark = self._new_focus_label("▁▂▃▂▄▅▄▅▆", "FocusStatItem")
        self._focus_energy_spark.setAlignment(Qt.AlignCenter)
        energy_layout.addWidget(self._focus_energy_value)
        energy_layout.addWidget(self._focus_energy_label)
        energy_layout.addWidget(self._focus_energy_spark)
        right_col.addWidget(energy)

        self._focus_display.setToolTip("左键切换：剩余/本轮/累计")
        self._focus_display.installEventFilter(self)
        for widget in self._focus_display.findChildren(QWidget):
            widget.installEventFilter(self)
        self._focus_display.hide()
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
        self._pending_delete_batch: list[tuple[Path, Path]] = []
        self._pending_delete_timer = QTimer(self)
        self._pending_delete_timer.setSingleShot(True)
        self._pending_delete_timer.setInterval(5000)
        self._pending_delete_timer.timeout.connect(self._finalize_pending_delete_batch)
        self._delete_combo_count = 0
        self._delete_combo_timer = QTimer(self)
        self._delete_combo_timer.setSingleShot(True)
        self._delete_combo_timer.setInterval(3000)
        self._delete_combo_timer.timeout.connect(self._reset_delete_combo)
        self.settings.total_deleted_count = max(0, int(self.settings.total_deleted_count))
        self.settings.hourly_reminder_enabled = bool(self.settings.hourly_reminder_enabled)
        self._last_hourly_reminder_hour: int | None = None
        self._hourly_reminder_timer = QTimer(self)
        self._hourly_reminder_timer.setInterval(30000)
        self._hourly_reminder_timer.timeout.connect(self._check_hourly_reminder)
        self._hourly_reminder_timer.start()
        self._cursor_sprite_mode = bool(self.settings.cursor_sprite_mode)
        self._movement_enabled_before_cursor_mode = self.settings.movement_enabled
        self.settings.total_click_count = max(0, int(self.settings.total_click_count))
        self.settings.total_pet_count = max(0, int(self.settings.total_pet_count))
        self.settings.total_feed_count = max(0, int(self.settings.total_feed_count))
        self.settings.pomodoro_enabled = False
        self.settings.pomodoro_focus_minutes = max(
            self.POMODORO_MINUTES_MIN,
            min(self.POMODORO_MINUTES_MAX, int(self.settings.pomodoro_focus_minutes)),
        )
        self.settings.pomodoro_break_minutes = max(
            self.POMODORO_MINUTES_MIN,
            min(self.POMODORO_MINUTES_MAX, int(self.settings.pomodoro_break_minutes)),
        )
        self.settings.pomodoro_cycles_completed = max(
            0,
            int(self.settings.pomodoro_cycles_completed),
        )
        self.settings.total_focus_seconds = max(0, int(self.settings.total_focus_seconds))
        self.settings.focus_panel_visible = False
        self.settings.lucky_sign_last_date = str(self.settings.lucky_sign_last_date or "")
        self.settings.lucky_sign_last_text = str(self.settings.lucky_sign_last_text or "")
        self.settings.lucky_sign_total_count = max(0, int(self.settings.lucky_sign_total_count))
        if not isinstance(self.settings.achievements_unlocked, list):
            self.settings.achievements_unlocked = []
        self._achievement_rules = [
            ("first_click", "初次互动", lambda: self.settings.total_click_count >= 1),
            ("click_30", "连点达人", lambda: self.settings.total_click_count >= 30),
            ("pet_20", "摸摸专家", lambda: self.settings.total_pet_count >= 20),
            ("feed_15", "投喂担当", lambda: self.settings.total_feed_count >= 15),
            ("clean_10", "清理助手", lambda: self.settings.total_deleted_count >= 10),
        ]
        valid_achievement_keys = {key for key, _title, _cond in self._achievement_rules}
        self.settings.achievements_unlocked = [
            key
            for key in self.settings.achievements_unlocked
            if isinstance(key, str) and key in valid_achievement_keys
        ]
        self._speed_boost_multiplier = 1.0
        self._speed_boost_timer = QTimer(self)
        self._speed_boost_timer.setSingleShot(True)
        self._speed_boost_timer.timeout.connect(self._clear_speed_boost)
        self._pomodoro_remaining_ms = 0
        self._pomodoro_duration_ms = max(1, self.settings.pomodoro_focus_minutes) * 60 * 1000
        self._focus_display_mode = "remaining"
        self._weather_text = "天气  获取中..."
        self._weather_timer = QTimer(self)
        self._weather_timer.setInterval(30 * 60 * 1000)
        self._weather_timer.timeout.connect(self._update_weather)
        self._pomodoro_timer = QTimer(self)
        self._pomodoro_timer.setInterval(1000)
        self._pomodoro_timer.timeout.connect(self._on_pomodoro_tick)

        self.window.clicked.connect(self._queue_single_click)
        self.window.double_clicked.connect(self.on_double_clicked)
        self.window.right_clicked.connect(self.on_right_clicked)
        self.window.files_dropped.connect(self.on_files_dropped)
        self.window.files_drag_hover.connect(self.on_files_drag_hover)
        self.window.drag_started.connect(self.on_drag_started)
        self.window.drag_moved.connect(self.on_drag_moved)
        self.window.drag_finished.connect(self.on_drag_finished)
        self.animation.frame_changed.connect(self._on_frame_changed)
        self.movement.base_state_changed.connect(self._on_base_state_changed)

        self._timer = QTimer(self)
        self._timer.setInterval(self.movement.tick_ms)
        self._timer.timeout.connect(self._tick)
        self._timer.start()
        self.qt_app.screenAdded.connect(self._on_screens_changed)
        self.qt_app.screenRemoved.connect(self._on_screens_changed)

        self.tray: TrayController | None = None
        if enable_tray and QSystemTrayIcon.isSystemTrayAvailable():
            self.tray = TrayController(
                on_toggle_visible=self.toggle_visible,
                on_toggle_movement=self.toggle_movement,
                on_toggle_autostart=self.toggle_autostart,
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
            self.tray.update_autostart_label(self.settings.autostart_enabled)
            self.tray.show()

        self._apply_cursor_sprite_mode(self._cursor_sprite_mode, persist=False)
        self._on_frame_changed(self.animation.current_frame())
        self._apply_visibility()
        self._refresh_focus_display()
        self._maybe_prompt_autostart_once()
        self._ensure_window_visible_on_any_screen()

    def _queue_single_click(self) -> None:
        self._single_click_timer.start()

    def _run_single_click(self) -> None:
        if self.movement.dragging:
            return
        self._increment_stat("total_click_count")
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
            stable=True,
        )
        self._play_special_bounce()
        self._click_pause_timer.start(max(400, self.sprites.spec.click_pause_ms))

    def on_right_clicked(self, global_pos: QPoint) -> None:
        menu = QMenu(self.window)
        mood_action = menu.addAction(
            f"当前情绪：{self._mood_state_label()} ({self._mood_points})"
        )
        mood_action.setEnabled(False)
        stats_action = menu.addAction(f"累计吞噬：{self.settings.total_deleted_count}")
        stats_action.setEnabled(False)
        achievements_status_action = menu.addAction(
            f"成就：{len(self.settings.achievements_unlocked)}/{len(self._achievement_rules)}"
        )
        achievements_status_action.setEnabled(False)
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
        lucky_sign_action = menu.addAction("抽今日幸运签")
        item_menu = menu.addMenu("道具箱")
        coffee_item_action = item_menu.addAction("咖啡（30秒加速）")
        snack_item_action = item_menu.addAction("零食（心情+跟随）")
        toy_item_action = item_menu.addAction("玩具（高跳彩蛋）")
        achievement_menu = menu.addMenu("成就进度")
        for line in self._achievement_progress_lines():
            item = achievement_menu.addAction(line)
            item.setEnabled(False)
        autostart_action = menu.addAction(
            "关闭开机自启动" if self.settings.autostart_enabled else "开启开机自启动"
        )
        cursor_mode_action = menu.addAction(
            "关闭鼠标精灵模式" if self._cursor_sprite_mode else "开启鼠标精灵模式"
        )
        follow_action = menu.addAction(
            "结束跟随" if self._follow_mouse_active else "跟随我（5秒）"
        )
        undo_action = menu.addAction("撤销上次删除（5秒内）")
        undo_action.setEnabled(bool(self._pending_delete_batch))
        reminder_action = menu.addAction(
            "关闭整点提醒" if self.settings.hourly_reminder_enabled else "开启整点提醒"
        )
        selected = menu.exec(global_pos)
        if selected == pet_action:
            self._interact_pet()
        elif selected == feed_action:
            self._interact_feed()
        elif selected == lucky_sign_action:
            self._draw_lucky_sign()
        elif selected == coffee_item_action:
            self._use_coffee_item()
        elif selected == snack_item_action:
            self._use_snack_item()
        elif selected == toy_item_action:
            self._use_toy_item()
        elif selected == autostart_action:
            self.toggle_autostart()
        elif selected == cursor_mode_action:
            self.toggle_cursor_sprite_mode()
        elif selected == follow_action:
            self._toggle_follow_mouse()
        elif selected == undo_action:
            self.undo_last_delete()
        elif selected == reminder_action:
            self.toggle_hourly_reminder()

    def on_drag_started(self) -> None:
        self._click_pause_timer.stop()
        self.movement.set_clicked_locked(False)
        self.movement.set_dragging(True)
        self.animation.set_state(DRAGGED)

    def on_drag_moved(self, x: int, y: int) -> None:
        self.movement.move_to(x, y)
        self._update_focus_display_position()
        self._persist_position()

    def on_drag_finished(self) -> None:
        self.movement.set_dragging(False)
        self._active_screen_geometry = self._pick_screen_for_window()
        self._persist_position()
        self._on_base_state_changed(self.movement.base_state())

    def on_files_dropped(self, paths: list[str]) -> None:
        if self._pending_delete_batch:
            self._finalize_pending_delete_batch()
        self._hide_dialogue_bubble()

        deleted = 0
        failed = 0
        moved_batch: list[tuple[Path, Path]] = []
        for raw_path in paths:
            file_path = Path(raw_path)
            if not file_path.exists():
                failed += 1
                continue
            try:
                staged_path = self._next_pending_trash_path(file_path.name)
                shutil.move(str(file_path), str(staged_path))
                moved_batch.append((file_path, staged_path))
                deleted += 1
            except OSError:
                failed += 1

        if moved_batch:
            self._pending_delete_batch = moved_batch
            self._pending_delete_timer.start()
            self.settings.total_deleted_count += deleted
            combo = self._register_delete_combo()
            self._check_achievements()
            self._persist_settings()
            if combo >= 2:
                self._show_dialogue(
                    f"吞噬连击 x{combo}！累计 {self.settings.total_deleted_count}",
                    duration_ms=1600,
                )

        if failed > 0:
            self._show_dialogue(f"删除失败 {failed} 个", duration_ms=1500)

    def on_files_drag_hover(self, hovering: bool) -> None:
        if hovering:
            self._show_dialogue("⚠ 松手永久删除", duration_ms=600000)
        else:
            self._hide_dialogue_bubble()

    def toggle_visible(self) -> None:
        self.settings.visible = not self.window.isVisible()
        self._apply_visibility()
        self._persist_settings()

    def toggle_focus_panel(self) -> None:
        self.settings.focus_panel_visible = not self.settings.focus_panel_visible
        self._refresh_focus_display()
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

    def toggle_autostart(self) -> None:
        target = not self.settings.autostart_enabled
        if not self._set_autostart_enabled_in_system(target):
            self._show_dialogue("开机自启动设置失败", duration_ms=1500)
            return
        self.settings.autostart_enabled = target
        self.settings.autostart_prompted = True
        if self.tray:
            self.tray.update_autostart_label(target)
        self._persist_settings()
        self._show_dialogue(
            "开机自启动已开启" if target else "开机自启动已关闭",
            duration_ms=1400,
        )

    def toggle_cursor_sprite_mode(self) -> None:
        self._apply_cursor_sprite_mode(not self._cursor_sprite_mode, persist=True)

    def toggle_hourly_reminder(self) -> None:
        self.settings.hourly_reminder_enabled = not self.settings.hourly_reminder_enabled
        self._last_hourly_reminder_hour = None
        self._persist_settings()
        self._show_dialogue(
            "整点提醒已开启" if self.settings.hourly_reminder_enabled else "整点提醒已关闭",
            duration_ms=1400,
        )

    def undo_last_delete(self) -> None:
        if not self._pending_delete_batch:
            self._show_dialogue("没有可撤销的删除", duration_ms=1300)
            return

        restored = 0
        failed = 0
        for original_path, staged_path in self._pending_delete_batch:
            if not staged_path.exists():
                failed += 1
                continue
            target_path = original_path
            if target_path.exists():
                target_path = target_path.with_name(f"{target_path.stem}_restored{target_path.suffix}")
            try:
                target_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(staged_path), str(target_path))
                restored += 1
            except OSError:
                failed += 1

        self._pending_delete_timer.stop()
        self._pending_delete_batch = []
        if restored > 0:
            self.settings.total_deleted_count = max(0, self.settings.total_deleted_count - restored)
            self._persist_settings()
            self._show_dialogue(f"已撤销 {restored} 个", duration_ms=1500)
            return
        self._show_dialogue(f"撤销失败 {failed} 个", duration_ms=1400)

    def reset_position(self) -> None:
        self._click_pause_timer.stop()
        self.movement.set_clicked_locked(False)
        bounds = self._movement_bounds()
        x = bounds.right() - self.window.width() - 48
        y = bounds.bottom() - self.window.height()
        self.window.move(x, y)
        self.movement.move_to(x, y)
        self._update_focus_display_position()
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
        self._finalize_pending_delete_batch()
        self._stop_pomodoro(show_dialogue=False)
        self._apply_cursor_sprite_mode(False, persist=False)
        self._hide_dialogue_bubble()
        self._focus_display.hide()
        self._persist_settings()
        if self.tray:
            self.tray.hide()
        self.qt_app.quit()

    def on_window_close_requested(self, event: QCloseEvent) -> None:
        self.settings.visible = False
        self.window.hide()
        self._focus_display.hide()
        self._persist_settings()
        event.ignore()

    def _tick(self) -> None:
        if self._special_anim and self._special_anim.state() == QAbstractAnimation.Running:
            return
        self._ensure_window_visible_on_any_screen()
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
        boosted_x = snapshot.x
        if snapshot.moving and self._speed_boost_multiplier > 1.0:
            current_x = self.window.x()
            delta = snapshot.x - current_x
            boosted_x = current_x + int(round(delta * self._speed_boost_multiplier))
        target_x = min(
            max(boosted_x, bounds.left()),
            bounds.right() - self.window.width() + 1,
        )
        target_y = min(
            max(self.window.y(), bounds.top()),
            bounds.bottom() - self.window.height() + 1,
        )
        self.window.move(target_x, target_y)
        self.settings.position_x = target_x
        self.settings.position_y = target_y
        self._update_focus_display_position()

    def _apply_visibility(self) -> None:
        if self.settings.visible:
            self.window.show()
        else:
            self.window.hide()
        self._refresh_focus_display()

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

    def _on_screens_changed(self, _screen=None) -> None:
        self._active_screen_geometry = None
        self._ensure_window_visible_on_any_screen()

    def _ensure_window_visible_on_any_screen(self) -> None:
        rect = self.window.frameGeometry()
        if any(rect.intersects(screen.availableGeometry()) for screen in self.qt_app.screens()):
            return

        primary = self.qt_app.primaryScreen()
        bounds = primary.availableGeometry() if primary else self._movement_bounds()
        x = bounds.right() - self.window.width() - 48
        y = bounds.bottom() - self.window.height()
        x = min(max(x, bounds.left()), bounds.right() - self.window.width() + 1)
        y = min(max(y, bounds.top()), bounds.bottom() - self.window.height() + 1)
        self.window.move(x, y)
        self.movement.move_to(x, y)
        self.settings.position_x = x
        self.settings.position_y = y

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

    def _show_dialogue(
        self,
        text: str,
        duration_ms: int | None = None,
        stable: bool = False,
    ) -> None:
        if not text:
            return
        timeout = (
            self.sprites.spec.click_dialog_duration_ms
            if duration_ms is None
            else max(1, int(duration_ms))
        )
        tip_pos = self.window.mapToGlobal(QPoint(self.window.width() // 2, 0))
        if not stable:
            QToolTip.showText(tip_pos, text, self.window, QRect(), timeout)
            self._stable_dialog_bubble.hide()
            self._dialog_hide_timer.start(timeout)
            return

        bounds = self._movement_bounds()
        self._stable_dialog_bubble.setText(text)
        self._stable_dialog_bubble.adjustSize()
        x = tip_pos.x() - self._stable_dialog_bubble.width() // 2
        y = tip_pos.y() - self._stable_dialog_bubble.height() - 14
        x = min(max(x, bounds.left() + 8), bounds.right() - self._stable_dialog_bubble.width() - 8)
        y = min(max(y, bounds.top() + 8), bounds.bottom() - self._stable_dialog_bubble.height() - 8)
        self._stable_dialog_bubble.move(x, y)
        self._stable_dialog_bubble.show()
        self._stable_dialog_bubble.raise_()
        self._dialog_hide_timer.start(timeout)

    def _hide_dialogue_bubble(self) -> None:
        self._dialog_hide_timer.stop()
        QToolTip.hideText()
        self._stable_dialog_bubble.hide()

    def _register_delete_combo(self) -> int:
        self._delete_combo_count += 1
        self._delete_combo_timer.start()
        return self._delete_combo_count

    def _reset_delete_combo(self) -> None:
        self._delete_combo_count = 0

    def _pending_trash_dir(self) -> Path:
        path = Path.home() / ".deskpet_pending_delete"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def _next_pending_trash_path(self, name: str) -> Path:
        safe_name = name or "item"
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        base = self._pending_trash_dir() / f"{stamp}_{random.randrange(1000, 9999)}_{safe_name}"
        return base

    def _finalize_pending_delete_batch(self) -> None:
        if not self._pending_delete_batch:
            return
        for _original_path, staged_path in self._pending_delete_batch:
            try:
                if staged_path.is_dir():
                    shutil.rmtree(staged_path, ignore_errors=True)
                elif staged_path.exists():
                    staged_path.unlink(missing_ok=True)
            except OSError:
                pass
        self._pending_delete_batch = []
        self._pending_delete_timer.stop()

    def _check_hourly_reminder(self) -> None:
        if not self.settings.hourly_reminder_enabled:
            return
        now = datetime.now()
        if now.minute != 0:
            return
        if self._last_hourly_reminder_hour == now.hour:
            return
        self._last_hourly_reminder_hour = now.hour
        lines = [
            "整点到啦，记得活动下肩颈~",
            "新的整点，继续稳稳推进！",
            "提醒：喝口水，休息 1 分钟。",
        ]
        self._show_dialogue(random.choice(lines), duration_ms=1600)

    def _toggle_pomodoro(self) -> None:
        if self.settings.pomodoro_enabled:
            self._stop_pomodoro(show_dialogue=True)
            return
        self._start_pomodoro()

    def _start_pomodoro(self) -> None:
        self.settings.pomodoro_enabled = True
        minutes = self.settings.pomodoro_focus_minutes
        self._pomodoro_duration_ms = max(1, minutes) * 60 * 1000
        self._pomodoro_remaining_ms = self._pomodoro_duration_ms
        self._pomodoro_timer.start()
        self._refresh_focus_display()
        self._show_dialogue(f"专注模式开始：{minutes} 分钟", duration_ms=1700)
        self._persist_settings()

    def _stop_pomodoro(self, show_dialogue: bool) -> None:
        was_running = self.settings.pomodoro_enabled
        self.settings.pomodoro_enabled = False
        self._pomodoro_remaining_ms = 0
        self._pomodoro_timer.stop()
        self._refresh_focus_display()
        if show_dialogue and was_running:
            self._show_dialogue("专注模式已停止", duration_ms=1300)
        self._persist_settings()

    def _skip_pomodoro_phase(self) -> None:
        if not self.settings.pomodoro_enabled:
            self._show_dialogue("专注模式未开启", duration_ms=1300)
            return
        self._pomodoro_duration_ms = max(1, self.settings.pomodoro_focus_minutes) * 60 * 1000
        self._pomodoro_remaining_ms = self._pomodoro_duration_ms
        self._refresh_focus_display()
        self._show_dialogue("专注计时已重置", duration_ms=1200)

    def _on_pomodoro_tick(self) -> None:
        if not self.settings.pomodoro_enabled:
            self._pomodoro_timer.stop()
            return
        self.settings.total_focus_seconds += 1
        self._pomodoro_remaining_ms -= 1000
        self._refresh_focus_display()
        if self._pomodoro_remaining_ms > 0:
            return
        self.settings.pomodoro_cycles_completed += 1
        self._check_achievements()
        self._persist_settings()
        self._show_dialogue("本轮专注完成，干得漂亮！", duration_ms=1700)
        self._stop_pomodoro(show_dialogue=False)

    def _current_pomodoro_label(self) -> str:
        if not self.settings.pomodoro_enabled:
            return "未开启"
        return f"进行中 {self._format_focus_remaining()}"

    def _format_focus_remaining(self) -> str:
        seconds = max(0, self._pomodoro_remaining_ms // 1000)
        minutes = seconds // 60
        remain_seconds = seconds % 60
        return f"{minutes:02d}:{remain_seconds:02d}"

    def _format_focus_elapsed(self) -> str:
        elapsed_ms = max(0, self._pomodoro_duration_ms - self._pomodoro_remaining_ms)
        elapsed_seconds = elapsed_ms // 1000
        minutes = elapsed_seconds // 60
        seconds = elapsed_seconds % 60
        return f"{minutes:02d}:{seconds:02d}"

    def _format_focus_total(self) -> str:
        total = max(0, int(self.settings.total_focus_seconds))
        hours = total // 3600
        minutes = (total % 3600) // 60
        seconds = total % 60
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"

    def _new_focus_label(self, text: str, object_name: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName(object_name)
        return label

    def _refresh_focus_display(self) -> None:
        if (
            not self.settings.pomodoro_enabled
            or not self.settings.visible
            or not self.settings.focus_panel_visible
        ):
            self._focus_display.hide()
            return
        if self._focus_display_mode == "total":
            timer_value = self._format_focus_total()
            mode_label = "累计专注时长"
        elif self._focus_display_mode == "elapsed":
            timer_value = self._format_focus_elapsed()
            mode_label = "本轮已专注"
        else:
            timer_value = self._format_focus_remaining()
            mode_label = "剩余时间"

        progress = self._focus_progress_percent()
        total_seconds = max(0, int(self.settings.total_focus_seconds))
        total_hours = total_seconds // 3600
        total_minutes = (total_seconds % 3600) // 60
        cycles = max(0, int(self.settings.pomodoro_cycles_completed))
        avg_minutes = int(total_seconds / cycles / 60) if cycles else 0
        unlocked = len(self.settings.achievements_unlocked)

        self._apply_focus_display_theme(progress)
        self._focus_timer.setText(timer_value)
        self._focus_ring_caption.setText(mode_label)
        self._focus_badge.setText("进行中")
        self._focus_ring_status.setText("• 专注中 •")
        self._focus_ring_sub.setText("深度工作")
        self._focus_note.setText("保持专注，你正在完成重要的事")
        self._focus_main_button.setText("▌▌  暂停专注")
        self._focus_stat_total.setText(f"专注时长  {total_hours}h {total_minutes:02d}m")
        self._focus_stat_cycles.setText(f"专注次数  {cycles}次")
        self._focus_stat_avg.setText(f"平均专注时长  {avg_minutes}m")
        self._focus_weather.setText(self._weather_text)
        self._focus_stat_achieve.setText(
            "今日成就  高效专注者" if progress >= 80 else "今日成就  稳定推进者"
        )
        self._focus_energy_value.setText(f"{max(1, self._mood_points)}")
        self._focus_energy_label.setText(f"当前专注力{self._mood_state_label()}")
        self._focus_energy_spark.setText(self._focus_progress_bar(progress, width=10))
        self._focus_note.setText(
            f"保持专注，你正在完成重要的事  ·  ACH {unlocked}/{len(self._achievement_rules)}"
        )
        self._focus_display.adjustSize()
        self._update_focus_display_position()
        self._focus_display.show()
        self._focus_display.raise_()

    def _update_focus_display_position(self) -> None:
        if not self._focus_display.isVisible():
            return
        bounds = self._movement_bounds()
        preferred_x = self.window.x() + self.window.width() + 18
        preferred_y = self.window.y() - 36
        if preferred_x + self._focus_display.width() > bounds.right() - 8:
            preferred_x = self.window.x() - self._focus_display.width() - 18
        x = preferred_x
        y = preferred_y
        x = min(max(x, bounds.left() + 8), bounds.right() - self._focus_display.width() - 8)
        y = min(max(y, bounds.top() + 8), bounds.bottom() - self._focus_display.height() - 8)
        self._focus_display.move(x, y)

    def _focus_progress_percent(self) -> int:
        if self._pomodoro_duration_ms <= 0:
            return 0
        elapsed = max(0, self._pomodoro_duration_ms - self._pomodoro_remaining_ms)
        return max(0, min(100, int(round(elapsed * 100 / self._pomodoro_duration_ms))))

    def _focus_progress_bar(self, percent: int, width: int = 12) -> str:
        filled = int(round(max(0, min(100, percent)) * width / 100))
        return "█" * filled + "░" * (width - filled)

    def _update_weather(self) -> None:
        fallback = self._fallback_weather_text()
        try:
            request = urllib.request.Request(
                "https://wttr.in/?format=j1",
                headers={"User-Agent": "desk-fun/1.0"},
            )
            with urllib.request.urlopen(request, timeout=3) as response:
                payload = response.read().decode("utf-8", errors="ignore")
            data = json.loads(payload)
            current = (data.get("current_condition") or [{}])[0]
            temp_c = str(current.get("temp_C", "")).strip()
            desc_raw = (
                ((current.get("weatherDesc") or [{}])[0].get("value", "")) or ""
            ).strip()
            desc = self._normalize_weather_desc(desc_raw)
            if temp_c and desc:
                self._weather_text = f"天气  {desc} {temp_c}°C"
            elif desc:
                self._weather_text = f"天气  {desc}"
            else:
                self._weather_text = fallback
        except (OSError, urllib.error.URLError, ValueError, KeyError, TypeError):
            self._weather_text = fallback
        self._refresh_focus_display()

    def _fallback_weather_text(self) -> str:
        hour = datetime.now().hour
        if 6 <= hour < 18:
            return "天气  晴"
        return "天气  夜间"

    def _normalize_weather_desc(self, desc: str) -> str:
        lowered = desc.lower()
        if "rain" in lowered or "shower" in lowered:
            return "雨"
        if "snow" in lowered:
            return "雪"
        if "cloud" in lowered or "overcast" in lowered:
            return "多云"
        if "fog" in lowered or "mist" in lowered or "haze" in lowered:
            return "雾"
        if "sun" in lowered or "clear" in lowered:
            return "晴"
        return "晴"

    def _apply_focus_display_theme(self, progress: int) -> None:
        if progress >= 85:
            accent = "rgb(255, 210, 115)"
            ring = "rgb(255, 200, 90)"
            border = "rgb(136, 94, 44)"
        elif progress >= 60:
            accent = "rgb(150, 232, 255)"
            ring = "rgb(120, 225, 255)"
            border = "rgb(43, 110, 162)"
        else:
            accent = "rgb(115, 248, 214)"
            ring = "rgb(96, 225, 255)"
            border = "rgb(33, 100, 142)"

        self._focus_display.setStyleSheet(
            "#FocusPanel {"
            "background: rgb(10, 14, 16);"
            f"border: 1px solid {border};"
            "border-radius: 14px;"
            "padding: 0px;"
            "}"
            "#FocusCard {background: rgb(8,20,42); border: 1px solid rgb(18,46,85); border-radius: 12px;}"
            f"#FocusRing {{background: rgb(7,18,36); border: 6px solid {ring}; border-radius: 110px;}}"
            "#FocusTimer {font-family: Consolas, 'Courier New', monospace; font-size: 48px; font-weight: 700; color: rgb(233,245,255); border:none;}"
            "#FocusRingStatus {font-size: 16px; color: rgb(95,193,255); border:none;}"
            "#FocusRingSub {font-size: 14px; color: rgb(170,200,230); border:none;}"
            "#FocusRingCaption {font-size: 15px; color: rgb(144,170,205); border:none;}"
            f"#FocusBadge {{font-size: 16px; color: {accent}; border: 1px solid rgb(36,148,130); border-radius: 10px; background: rgb(5,50,58); padding: 2px 8px;}}"
            "#FocusNote {font-size: 13px; color: rgb(172,196,226); border:none;}"
            "#FocusMainButton {font-size: 16px; font-weight: 700; color: rgb(220,240,255); border: 1px solid rgb(59,135,255); border-radius: 16px; background: rgb(29,84,193); padding: 6px 10px;}"
            "#FocusSideButton {font-size: 15px; color: rgb(220,240,255); border: 1px solid rgb(62,96,140); border-radius: 16px; background: rgb(20,44,78); padding: 6px 10px;}"
            "#FocusSectionTitle {font-size: 24px; font-weight: 700; color: rgb(205,231,255); border:none;}"
            "#FocusStatItem {font-size: 19px; color: rgb(176,210,242); border:none;}"
            "#FocusStatValue {font-size: 22px; font-weight: 700; color: rgb(216,239,255); border:none;}"
            f"#FocusEnergyValue {{font-size: 54px; font-weight: 700; color: {accent}; border:none;}}"
            "#FocusEnergyLabel {font-size: 15px; color: rgb(119,225,223); border:none;}"
            "#FocusHideButton {font-size: 14px; color: rgb(170,210,250); border: 1px solid rgb(40,86,150); border-radius: 10px; background: rgb(13,34,63); padding: 2px 7px;}"
        )

    def _set_focus_minutes(self, minutes: int) -> None:
        clamped = max(
            self.POMODORO_MINUTES_MIN,
            min(self.POMODORO_MINUTES_MAX, int(minutes)),
        )
        if self.settings.pomodoro_focus_minutes == clamped and not self.settings.pomodoro_enabled:
            return
        self.settings.pomodoro_focus_minutes = clamped
        if self.settings.pomodoro_enabled:
            self._pomodoro_duration_ms = clamped * 60 * 1000
            self._pomodoro_remaining_ms = self._pomodoro_duration_ms
            self._show_dialogue(f"专注时长已切换：{clamped} 分钟", duration_ms=1300)
            self._refresh_focus_display()
        else:
            self._show_dialogue(f"默认专注时长：{clamped} 分钟", duration_ms=1200)
        self._persist_settings()

    def eventFilter(self, watched, event) -> bool:
        if (
            self._focus_display is not None
            and isinstance(watched, QWidget)
            and (
                watched is self._focus_display
                or self._focus_display.isAncestorOf(watched)
            )
            and event.type() == QEvent.MouseButtonPress
        ):
            if watched is self._focus_hide_button and event.button() == Qt.LeftButton:
                self.settings.focus_panel_visible = False
                self._refresh_focus_display()
                self._persist_settings()
                return True
            if event.button() == Qt.LeftButton and self.settings.pomodoro_enabled:
                if self._focus_display_mode == "remaining":
                    self._focus_display_mode = "elapsed"
                    self._show_dialogue("数显：本轮已专注", duration_ms=1000)
                elif self._focus_display_mode == "elapsed":
                    self._focus_display_mode = "total"
                    self._show_dialogue("数显：累计专注", duration_ms=1000)
                else:
                    self._focus_display_mode = "remaining"
                    self._show_dialogue("数显：剩余时间", duration_ms=1000)
                self._refresh_focus_display()
                return True
        return super().eventFilter(watched, event)

    def _maybe_prompt_autostart_once(self) -> None:
        if self.settings.autostart_prompted:
            return
        if sys.platform != "win32":
            self.settings.autostart_prompted = True
            self._persist_settings()
            return

        answer = QMessageBox.question(
            self.window,
            "DeskPet",
            "是否在开机时自动启动 DeskPet？\n你可以随时在托盘菜单里关闭。",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        enabled = answer == QMessageBox.Yes
        if enabled:
            self._set_autostart_enabled_in_system(True)
        self.settings.autostart_enabled = self._is_autostart_enabled_in_system()
        self.settings.autostart_prompted = True
        if self.tray:
            self.tray.update_autostart_label(self.settings.autostart_enabled)
        self._persist_settings()

    def _is_autostart_enabled_in_system(self) -> bool:
        if sys.platform != "win32":
            return False
        value_name = "DeskPet"
        try:
            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Run",
                0,
                winreg.KEY_READ,
            ) as key:
                value, _ = winreg.QueryValueEx(key, value_name)
                return bool(value)
        except OSError:
            return False

    def _set_autostart_enabled_in_system(self, enabled: bool) -> bool:
        if sys.platform != "win32":
            return False
        value_name = "DeskPet"
        try:
            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Run",
                0,
                winreg.KEY_SET_VALUE,
            ) as key:
                if enabled:
                    winreg.SetValueEx(key, value_name, 0, winreg.REG_SZ, self._autostart_command())
                else:
                    try:
                        winreg.DeleteValue(key, value_name)
                    except OSError:
                        pass
            return True
        except OSError:
            return False

    def _autostart_command(self) -> str:
        if getattr(sys, "frozen", False):
            return f'"{Path(sys.executable)}"'
        main_py = Path(__file__).resolve().parents[2] / "main.py"
        return f'"{Path(sys.executable)}" "{main_py}"'

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
        self._increment_stat("total_pet_count")
        self._change_mood(10)
        self._show_dialogue(random.choice(self.sprites.spec.pet_dialogues))

    def _interact_feed(self) -> None:
        self._increment_stat("total_feed_count")
        self._change_mood(20)
        self._show_dialogue(random.choice(self.sprites.spec.feed_dialogues))

    def _draw_lucky_sign(self) -> None:
        today = datetime.now().strftime("%Y-%m-%d")
        if self.settings.lucky_sign_last_date == today and self.settings.lucky_sign_last_text:
            self._show_dialogue(
                f"今日幸运签：{self.settings.lucky_sign_last_text}",
                duration_ms=2200,
                stable=True,
            )
            return

        tier = random.choices(
            population=["大吉", "中吉", "小吉", "末吉"],
            weights=[12, 32, 36, 20],
            k=1,
        )[0]
        lines = {
            "大吉": [
                "今日行动力爆棚，想做的事马上推进。",
                "好运加成，适合发起关键任务。",
            ],
            "中吉": [
                "节奏稳定的一天，按计划做就会有收获。",
                "耐心执行，结果会比预期更好。",
            ],
            "小吉": [
                "先完成一件小事，状态会慢慢起来。",
                "保持专注，今天适合稳扎稳打。",
            ],
            "末吉": [
                "先别急，整理桌面和思路再出发。",
                "慢一点没关系，今天主打不翻车。",
            ],
        }
        result = f"{tier} · {random.choice(lines[tier])}"
        self.settings.lucky_sign_last_date = today
        self.settings.lucky_sign_last_text = result
        self.settings.lucky_sign_total_count += 1
        self._persist_settings()

        if tier == "大吉":
            self._change_mood(16)
            self._play_special_bounce(lift_px=96, duration_ms=520)
        elif tier == "中吉":
            self._change_mood(10)
            self._play_special_bounce(lift_px=68, duration_ms=420)
        elif tier == "小吉":
            self._change_mood(6)
        else:
            self._change_mood(2)

        self._show_dialogue(
            f"今日幸运签：{result}",
            duration_ms=2500,
            stable=True,
        )

    def _use_coffee_item(self) -> None:
        self._speed_boost_multiplier = 1.8
        self._speed_boost_timer.start(30000)
        self._show_dialogue("咖啡生效：30秒加速巡航！", duration_ms=1500)

    def _use_snack_item(self) -> None:
        self._change_mood(15)
        self._start_follow_mouse(4000)
        self._show_dialogue("零食真香，跟你跑一会儿~", duration_ms=1500)

    def _use_toy_item(self) -> None:
        self._change_mood(8)
        self._show_dialogue("玩具彩蛋触发！", duration_ms=1300)
        self._play_special_bounce(lift_px=108, duration_ms=480)

    def _clear_speed_boost(self) -> None:
        self._speed_boost_multiplier = 1.0
        self._show_dialogue("加速结束，恢复正常速度。", duration_ms=1200)

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

    def _increment_stat(self, field_name: str, amount: int = 1) -> None:
        current = int(getattr(self.settings, field_name, 0))
        setattr(self.settings, field_name, max(0, current + int(amount)))
        self._check_achievements()
        self._persist_settings()

    def _check_achievements(self) -> None:
        unlocked = set(self.settings.achievements_unlocked)
        for key, title, condition in self._achievement_rules:
            if key in unlocked:
                continue
            if not condition():
                continue
            unlocked.add(key)
            self.settings.achievements_unlocked.append(key)
            self._show_dialogue(f"🏅 解锁成就：{title}", duration_ms=1800)

    def _achievement_progress_lines(self) -> list[str]:
        unlocked = set(self.settings.achievements_unlocked)
        lines: list[str] = []
        for key, title, condition in self._achievement_rules:
            if key in unlocked or condition():
                lines.append(f"✓ {title}")
            else:
                lines.append(f"· {title}")
        return lines

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
        self._update_focus_display_position()
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
        self._update_focus_display_position()
        self.settings.position_x = next_x
        self.settings.position_y = next_y
