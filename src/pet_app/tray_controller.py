from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QIcon, QColor, QPainter, QPixmap
from PySide6.QtWidgets import QMenu, QSystemTrayIcon


class TrayController:
    def __init__(
        self,
        on_toggle_visible: Callable[[], None],
        on_toggle_movement: Callable[[], None],
        on_reset_position: Callable[[], None],
        on_quit: Callable[[], None],
    ) -> None:
        self._tray = QSystemTrayIcon()
        self._tray.setToolTip("DeskPet")
        self._tray.setIcon(QIcon(self._make_icon()))

        menu = QMenu()

        self._toggle_visible_action = QAction("显示/隐藏")
        self._toggle_visible_action.triggered.connect(on_toggle_visible)
        menu.addAction(self._toggle_visible_action)

        self._toggle_movement_action = QAction("暂停移动")
        self._toggle_movement_action.triggered.connect(on_toggle_movement)
        menu.addAction(self._toggle_movement_action)

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
