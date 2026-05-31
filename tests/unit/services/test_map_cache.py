"""Tests for project-local map cache warmup."""

from gpstitch.models.schemas import FileRole
from gpstitch.services.map_cache import MapCacheService, MovingMapWarmupSpec, RoutePoint


def test_map_cache_service_creates_cache_dir(temp_dir):
    cache_dir = temp_dir / "maps"

    service = MapCacheService(cache_dir=cache_dir)

    assert service.cache_dir == cache_dir
    assert cache_dir.exists()


def test_get_session_route_points_from_gpx(clean_file_manager, temp_dir, monkeypatch):
    gpx_path = temp_dir / "track.gpx"
    gpx_path.write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
<gpx><trk><trkseg>
<trkpt lat="1.0" lon="2.0"></trkpt>
<trkpt lat="3.0" lon="4.0"></trkpt>
</trkseg></trk></gpx>
""",
        encoding="utf-8",
    )
    session_id = clean_file_manager.create_local_session()
    clean_file_manager.add_file(
        session_id=session_id,
        filename=gpx_path.name,
        file_path=str(gpx_path),
        file_type="gpx",
        role=FileRole.PRIMARY,
    )
    monkeypatch.setattr("gpstitch.services.map_cache.file_manager", clean_file_manager)

    points = MapCacheService(cache_dir=temp_dir / "maps").get_session_route_points(session_id)

    assert points == [RoutePoint(lat=1.0, lon=2.0), RoutePoint(lat=3.0, lon=4.0)]


def test_warm_session_cache_is_bounded(temp_dir, monkeypatch):
    service = MapCacheService(cache_dir=temp_dir / "maps")
    points = [RoutePoint(lat=float(i), lon=float(i)) for i in range(20)]
    moving_windows = []

    monkeypatch.setattr(service, "get_session_route_points", lambda session_id: points)
    monkeypatch.setattr(service, "_render_route_extent", lambda route, style, size=256: 1)

    def render_moving_window(point, style, spec=MovingMapWarmupSpec()):
        moving_windows.append(point)
        return 1

    monkeypatch.setattr(service, "_render_moving_window", render_moving_window)
    monkeypatch.setattr("gpstitch.services.map_cache.settings.map_cache_warmup_max_tiles", 27)

    result = service.warm_session_cache("session", map_style="osm", language="en")

    assert result.success is True
    assert result.rendered_maps == 3
    assert result.capped is True
    assert len(moving_windows) == 2


def test_warm_session_cache_accepts_call_specific_tile_limit(temp_dir, monkeypatch):
    service = MapCacheService(cache_dir=temp_dir / "maps")
    points = [RoutePoint(lat=float(i), lon=float(i)) for i in range(20)]
    moving_windows = []

    monkeypatch.setattr(service, "get_session_route_points", lambda session_id: points)
    monkeypatch.setattr(service, "_render_route_extent", lambda route, style, size=256: 1)
    monkeypatch.setattr(
        service,
        "_render_moving_window",
        lambda point, style, spec=MovingMapWarmupSpec(): moving_windows.append(point) or 1,
    )
    monkeypatch.setattr("gpstitch.services.map_cache.settings.map_cache_warmup_max_tiles", 512)

    result = service.warm_session_cache("session", map_style="osm", language="en", max_tiles=27)

    assert result.success is True
    assert result.rendered_maps == 3
    assert result.capped is True
    assert len(moving_windows) == 2


def test_warm_session_cache_uses_layout_map_dimensions(temp_dir, monkeypatch):
    service = MapCacheService(cache_dir=temp_dir / "maps")
    points = [RoutePoint(lat=30.0 + i * 0.001, lon=100.0 + i * 0.001) for i in range(3)]
    moving_specs = []
    route_sizes = []

    monkeypatch.setattr(service, "get_session_route_points", lambda session_id: points)

    def render_route_extent(route, style, size=256):
        route_sizes.append(size)
        return 1

    def render_moving_window(point, style, spec=MovingMapWarmupSpec()):
        moving_specs.append(spec)
        return 1

    monkeypatch.setattr(service, "_render_route_extent", render_route_extent)
    monkeypatch.setattr(service, "_render_moving_window", render_moving_window)
    monkeypatch.setattr("gpstitch.services.map_cache.settings.map_cache_warmup_max_tiles", 512)

    result = service.warm_session_cache("session", map_style="osm", layout="default-3840x2160", language="en")

    assert result.success is True
    assert route_sizes == [512]
    assert moving_specs
    assert moving_specs[0].size == 512
    assert moving_specs[0].render_size == 724
