from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QIcon, QColor, QPainter, QPixmap
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMenu,
    QSlider,
    QSystemTrayIcon,
    QWidget,
    QWidgetAction,
)


class TrayController:
    def __init__(
        self,
        on_toggle_visible: Callable[[], None],
        on_toggle_movement: Callable[[], None],
        on_toggle_cursor_sprite_mode: Callable[[], None],
        on_reset_position: Callable[[], None],
        on_quit: Callable[[], None],
        on_set_scale_percent: Callable[[int], None],
        initial_scale_percent: int,
        scale_min_percent: int,
        scale_max_percent: int,
        scale_step_percent: int,
        cursor_sprite_mode_enabled: bool,
    ) -> None:
        self._tray = QSystemTrayIcon()
        self._tray.setToolTip("DeskPet")
        self._tray.setIcon(QIcon(self._make_icon()))
        self._on_set_scale_percent = on_set_scale_percent
        self._scale_min_percent = scale_min_percent
        self._scale_max_percent = scale_max_percent
        self._scale_step_percent = max(1, scale_step_percent)

        menu = QMenu()

        self._toggle_visible_action = QAction("显示/隐藏")
        self._toggle_visible_action.triggered.connect(on_toggle_visible)
        menu.addAction(self._toggle_visible_action)

        self._toggle_movement_action = QAction("暂停移动")
        self._toggle_movement_action.triggered.connect(on_toggle_movement)
        menu.addAction(self._toggle_movement_action)

        self._toggle_cursor_sprite_action = QAction()
        self._toggle_cursor_sprite_action.triggered.connect(on_toggle_cursor_sprite_mode)
        menu.addAction(self._toggle_cursor_sprite_action)
        self.update_cursor_sprite_mode_label(cursor_sprite_mode_enabled)

        scale_menu = menu.addMenu("缩放比例")
        self._scale_value_label = QLabel("")
        self._scale_slider = QSlider(Qt.Horizontal)
        self._scale_slider.setMinimum(self._scale_min_percent)
        self._scale_slider.setMaximum(self._scale_max_percent)
        self._scale_slider.setSingleStep(self._scale_step_percent)
        self._scale_slider.setPageStep(self._scale_step_percent)
        self._scale_slider.setTickInterval(self._scale_step_percent)
        self._scale_slider.setTickPosition(QSlider.TicksBelow)
        self._scale_slider.valueChanged.connect(self._on_scale_slider_changed)

        scale_container = QWidget()
        scale_layout = QHBoxLayout(scale_container)
        scale_layout.setContentsMargins(8, 4, 8, 4)
        scale_layout.setSpacing(8)
        scale_layout.addWidget(QLabel("缩放"))
        scale_layout.addWidget(self._scale_slider, 1)
        scale_layout.addWidget(self._scale_value_label)

        scale_widget_action = QWidgetAction(scale_menu)
        scale_widget_action.setDefaultWidget(scale_container)
        scale_menu.addAction(scale_widget_action)
        self.update_scale_percent(initial_scale_percent)

        reset_action = QAction("重置位置")
        reset_action.triggered.connect(on_reset_position)
        menu.addAction(reset_action)

        exit_action = QAction("退出")
        exit_action.triggered.connect(on_quit)
        menu.addAction(exit_action)

        self._tray.setContextMenu(menu)

    def show(self) -> None:
        self._tray.show()

    def hide(self) -> None:
        self._tray.hide()

    def update_movement_label(self, enabled: bool) -> None:
        self._toggle_movement_action.setText("暂停移动" if enabled else "继续移动")

    def update_cursor_sprite_mode_label(self, enabled: bool) -> None:
        self._toggle_cursor_sprite_action.setText(
            "关闭鼠标精灵模式" if enabled else "开启鼠标精灵模式"
        )

    def update_scale_percent(self, percent: int) -> None:
        snapped = self._snap_percent(percent)
        self._scale_slider.blockSignals(True)
        self._scale_slider.setValue(snapped)
        self._scale_slider.blockSignals(False)
        self._scale_value_label.setText(f"{snapped}%")

    def _on_scale_slider_changed(self, value: int) -> None:
        snapped = self._snap_percent(value)
        if snapped != value:
            self._scale_slider.blockSignals(True)
            self._scale_slider.setValue(snapped)
            self._scale_slider.blockSignals(False)
        self._scale_value_label.setText(f"{snapped}%")
        self._on_set_scale_percent(snapped)

    def _snap_percent(self, value: int) -> int:
        clamped = max(self._scale_min_percent, min(self._scale_max_percent, int(value)))
        steps = round((clamped - self._scale_min_percent) / self._scale_step_percent)
        return self._scale_min_percent + steps * self._scale_step_percent

    def _make_icon(self) -> QPixmap:
        pixmap = QPixmap(32, 32)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setBrush(QColor("#f59e0b"))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(4, 4, 24, 24)
        painter.end()
        return pixmap
