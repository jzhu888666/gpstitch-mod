"""Tests for AMap settings and map style metadata APIs."""

from gpstitch.models.schemas import AMapSettingsUpdateRequest, AMapValidationRequest
from gpstitch.services.amap_settings import AMapSettingsService


async def test_amap_settings_api_redacts_credentials(monkeypatch, temp_dir):
    from gpstitch.api import settings as settings_api

    service = AMapSettingsService(temp_dir / "amap.json")
    monkeypatch.setattr(settings_api, "amap_settings_service", service)

    saved = await settings_api.save_amap_settings(
        AMapSettingsUpdateRequest(key="api-key", security_js_code="api-security")
    )
    runtime = await settings_api.get_amap_runtime_config()
    validated = await settings_api.record_amap_validation(AMapValidationRequest(success=True))

    assert saved.configured is True
    assert saved.validated is False
    assert "api-key" not in saved.model_dump_json()
    assert runtime.key == "api-key"
    assert runtime.security_js_code == "api-security"
    assert validated.validated is True


async def test_map_styles_include_amap_metadata(monkeypatch, temp_dir):
    from gpstitch.api import options

    service = AMapSettingsService(temp_dir / "amap.json")
    service.save_credentials("api-key", "api-security")
    service.record_validation(True)
    monkeypatch.setattr(options, "amap_settings_service", service)

    response = await options.get_map_styles(language="en")

    amap = next(style for style in response.styles if style.name == "amap-jsapi")
    satellite = next(style for style in response.styles if style.name == "amap-jsapi-satellite")
    mixed = next(style for style in response.styles if style.name == "amap-jsapi-mixed")
    assert amap.provider == "amap"
    assert amap.requires_api_key is True
    assert amap.requires_security_js_code is True
    assert amap.configured is True
    assert amap.validated is True
    assert amap.key_fingerprint is not None
    assert satellite.provider == "amap"
    assert satellite.requires_api_key is True
    assert satellite.requires_security_js_code is True
    assert satellite.configured is True
    assert satellite.validated is True
    assert satellite.key_fingerprint == amap.key_fingerprint
    assert mixed.provider == "amap"
    assert mixed.requires_api_key is True
    assert mixed.requires_security_js_code is True
    assert mixed.configured is True
    assert mixed.validated is True
    assert mixed.key_fingerprint == amap.key_fingerprint
