from __future__ import annotations

from pet_app.models import AppSettings
from pet_app import settings as settings_module


def test_settings_roundtrip(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(settings_module, "get_settings_path", lambda: tmp_path / "settings.json")

    expected = AppSettings(position_x=10, position_y=20, movement_enabled=False)
    settings_module.save_settings(expected)
    actual = settings_module.load_settings()

    assert actual.position_x == 10
    assert actual.position_y == 20
    assert actual.movement_enabled is False
