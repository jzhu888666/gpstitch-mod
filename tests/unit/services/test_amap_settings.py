"""Tests for AMap JS API settings helpers."""

import pytest

from gpstitch.services.amap_settings import AMapSettingsService, backend_map_style, is_amap_style


def test_amap_settings_redacts_saved_credentials(temp_dir):
    service = AMapSettingsService(temp_dir / "amap.json")

    response = service.save_credentials("test-key", "test-security")

    assert response.configured is True
    assert response.validated is False
    assert response.key_fingerprint is not None
    assert "test-key" not in response.model_dump_json()
    assert "test-security" not in response.model_dump_json()


def test_amap_runtime_config_is_explicit(temp_dir):
    service = AMapSettingsService(temp_dir / "amap.json")
    service.save_credentials("test-key", "test-security")

    runtime = service.get_runtime_config()

    assert runtime.configured is True
    assert runtime.key == "test-key"
    assert runtime.security_js_code == "test-security"


def test_amap_settings_persist_across_service_instances(temp_dir):
    path = temp_dir / "persistent" / "amap.json"

    service = AMapSettingsService(path)
    service.save_credentials("test-key", "test-security")
    service.record_validation(True)

    restarted = AMapSettingsService(path)
    runtime = restarted.get_runtime_config()

    assert runtime.configured is True
    assert runtime.validated is True
    assert runtime.key == "test-key"
    assert runtime.security_js_code == "test-security"


def test_amap_settings_migrate_from_legacy_cache_path(temp_dir):
    path = temp_dir / "settings" / "amap.json"
    legacy_path = temp_dir / "cache" / "settings" / "amap.json"

    legacy = AMapSettingsService(legacy_path)
    legacy.save_credentials("legacy-key", "legacy-security")
    legacy.record_validation(True)

    service = AMapSettingsService(path, legacy_settings_path=legacy_path)
    runtime = service.get_runtime_config()

    assert runtime.configured is True
    assert runtime.validated is True
    assert runtime.key == "legacy-key"
    assert runtime.security_js_code == "legacy-security"
    assert path.exists()


def test_amap_save_and_clear_remove_legacy_copy(temp_dir):
    path = temp_dir / "settings" / "amap.json"
    legacy_path = temp_dir / "cache" / "settings" / "amap.json"

    legacy = AMapSettingsService(legacy_path)
    legacy.save_credentials("old-key", "old-security")

    service = AMapSettingsService(path, legacy_settings_path=legacy_path)
    service.save_credentials("new-key", "new-security")
    assert not legacy_path.exists()

    legacy_path.parent.mkdir(parents=True, exist_ok=True)
    legacy_path.write_text("{}", encoding="utf-8")
    service.clear()

    assert not path.exists()
    assert not legacy_path.exists()


def test_amap_settings_fall_back_to_legacy_when_primary_is_unwritable(temp_dir):
    blocked_parent = temp_dir / "blocked"
    blocked_parent.write_text("not a directory", encoding="utf-8")
    path = blocked_parent / "amap.json"
    legacy_path = temp_dir / "cache" / "settings" / "amap.json"

    service = AMapSettingsService(path, legacy_settings_path=legacy_path)
    service.save_credentials("fallback-key", "fallback-security")
    service.record_validation(True)

    runtime = service.get_runtime_config()

    assert runtime.configured is True
    assert runtime.validated is True
    assert runtime.key == "fallback-key"
    assert legacy_path.exists()


def test_amap_validation_sanitizes_secret_values(temp_dir):
    service = AMapSettingsService(temp_dir / "amap.json")
    service.save_credentials("test-key", "test-security")

    response = service.record_validation(False, "bad key=test-key and test-security")

    assert response.validated is False
    assert "test-key" not in response.last_error
    assert "test-security" not in response.last_error
    assert "[redacted]" in response.last_error


def test_amap_backend_style_falls_back_to_osm():
    assert is_amap_style("amap-jsapi") is True
    assert backend_map_style("amap-jsapi") == "osm"
    assert backend_map_style("osm") == "osm"


def test_amap_validation_requires_configured_credentials(temp_dir):
    service = AMapSettingsService(temp_dir / "amap.json")

    with pytest.raises(ValueError):
        service.record_validation(True)
