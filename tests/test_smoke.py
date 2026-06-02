from __future__ import annotations

from PySide6.QtWidgets import QApplication

from pet_app.app import DesktopPetApp
from pet_app.models import AppSettings


def test_app_smoke(qtbot) -> None:
    app = QApplication.instance() or QApplication([])
    pet_app = DesktopPetApp(app, AppSettings(position_x=10, position_y=10), enable_tray=False)

    qtbot.addWidget(pet_app.window)
    assert pet_app.window is not None
