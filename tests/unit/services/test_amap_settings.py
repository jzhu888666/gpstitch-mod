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
