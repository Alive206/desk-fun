from __future__ import annotations

from PySide6.QtCore import QPoint, Qt, QTimer, Signal
from PySide6.QtGui import QCloseEvent, QMouseEvent, QPixmap
from PySide6.QtWidgets import QWidget


class PetWindow(QWidget):
    clicked = Signal()
    double_clicked = Signal()
    right_clicked = Signal(QPoint)
    drag_started = Signal()
    drag_moved = Signal(int, int)
    drag_finished = Signal()
    close_requested = Signal(QCloseEvent)

    def __init__(
        self,
        hitbox_padding: int = 8,
        max_display_size: int = 256,
        drag_hold_ms: int = 180,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.hitbox_padding = hitbox_padding
        self.max_display_size = max(32, max_display_size)
        self.drag_hold_ms = max(0, drag_hold_ms)
        self.current_frame = QPixmap()
        self._dragging = False
        self._pressing = False
        self._drag_offset = QPoint()
        self._press_global = QPoint()
        self._drag_distance = 0
        self._suppress_next_click = False

        self._drag_timer = QTimer(self)
        self._drag_timer.setSingleShot(True)
        self._drag_timer.timeout.connect(self._activate_drag)

        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setWindowFlags(
            Qt.FramelessWindowHint | Qt.Tool | Qt.WindowStaysOnTopHint
        )
        self.setFocusPolicy(Qt.NoFocus)
        self.resize(128, 128)

    def set_frame(self, frame: QPixmap, scale: float = 1.0) -> None:
        self.current_frame = frame
        if not frame.isNull():
            # First fit the raw frame to base size, then apply user scale steps.
            base_width, base_height = self._fit_to_max_size(frame.width(), frame.height())
            width = max(1, int(base_width * scale))
            height = max(1, int(base_height * scale))
            self.resize(width, height)
        self.update()

    def _fit_to_max_size(self, width: int, height: int) -> tuple[int, int]:
        largest_edge = max(width, height)
        if largest_edge <= self.max_display_size:
            return width, height

        ratio = self.max_display_size / largest_edge
        return (
            max(1, int(width * ratio)),
            max(1, int(height * ratio)),
        )

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.LeftButton:
            self._pressing = True
            self._dragging = False
            self._press_global = event.globalPosition().toPoint()
            self._drag_distance = 0
            self._drag_offset = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            if self.drag_hold_ms == 0:
                self._activate_drag()
            else:
                self._drag_timer.start(self.drag_hold_ms)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._pressing:
            current_global = event.globalPosition().toPoint()
            self._drag_distance = max(
                self._drag_distance,
                (current_global - self._press_global).manhattanLength(),
            )
            if not self._dragging and self._drag_distance >= 6:
                self._activate_drag()
        if self._dragging:
            top_left = event.globalPosition().toPoint() - self._drag_offset
            self.move(top_left)
            self.drag_moved.emit(top_left.x(), top_left.y())
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.RightButton:
            self.right_clicked.emit(event.globalPosition().toPoint())
            event.accept()
            return

        if event.button() == Qt.LeftButton and self._pressing:
            self._drag_timer.stop()
            was_dragging = self._dragging
            self._pressing = False
            self._dragging = False
            if was_dragging:
                self.drag_finished.emit()
            release_distance = max(
                self._drag_distance,
                (event.globalPosition().toPoint() - self._press_global).manhattanLength(),
            )
            if self._suppress_next_click:
                self._suppress_next_click = False
            elif not was_dragging and release_distance < 6:
                self.clicked.emit()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.LeftButton:
            self._suppress_next_click = True
            self.double_clicked.emit()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def paintEvent(self, event) -> None:
        if self.current_frame.isNull():
            return

        from PySide6.QtGui import QPainter

        painter = QPainter(self)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
        painter.drawPixmap(0, 0, self.width(), self.height(), self.current_frame)
        painter.end()

    def closeEvent(self, event: QCloseEvent) -> None:
        self.close_requested.emit(event)

    def _activate_drag(self) -> None:
        if not self._pressing or self._dragging:
            return
        self._dragging = True
        self.drag_started.emit()
