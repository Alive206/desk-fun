from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from .app import DesktopPetApp
from .settings import load_settings


def main() -> int:
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    settings = load_settings()
    desktop_pet = DesktopPetApp(app, settings)
    desktop_pet.window.show() if settings.visible else desktop_pet.window.hide()

    return app.exec()
