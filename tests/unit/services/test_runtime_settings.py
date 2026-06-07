"""Unit tests for persisted runtime settings."""

import json

from gpstitch.services.runtime_settings import RuntimeSettingsService


def test_render_concurrency_defaults_when_not_persisted(tmp_path):
    service = RuntimeSettingsService(tmp_path / "runtime.json")

    assert service.get_render_concurrency(default=2) == 2


def test_render_concurrency_is_persisted_and_clamped(tmp_path):
    settings_path = tmp_path / "runtime.json"
    service = RuntimeSettingsService(settings_path)

    assert service.set_render_concurrency(3) == 3
    assert service.get_render_concurrency(default=1) == 3

    data = json.loads(settings_path.read_text(encoding="utf-8"))
    assert data["render_concurrency"] == 3
    assert service.set_render_concurrency(99) == 3


def test_shutdown_after_all_tasks_is_persisted(tmp_path):
    settings_path = tmp_path / "runtime.json"
    service = RuntimeSettingsService(settings_path)

    assert service.get_shutdown_after_all_tasks() is False
    assert service.set_shutdown_after_all_tasks(True) is True
    assert service.get_shutdown_after_all_tasks() is True

    data = json.loads(settings_path.read_text(encoding="utf-8"))
    assert data["shutdown_after_all_tasks"] is True
