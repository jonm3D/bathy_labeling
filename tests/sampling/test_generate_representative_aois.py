from __future__ import annotations

import importlib.util
import math
import sys
from pathlib import Path

import pytest

pytest.importorskip("geopandas")
pytest.importorskip("rasterio")
pytest.importorskip("shapely")
pytest.importorskip("pyproj")

import numpy as np
import rasterio
from pyproj import Transformer
from rasterio.transform import from_origin
from shapely.ops import transform as transform_geometry


SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "generate_representative_aois.py"
SPEC = importlib.util.spec_from_file_location("generate_representative_aois", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
sampler = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = sampler
SPEC.loader.exec_module(sampler)


def test_utm_epsg_for_lonlat_selects_zone_and_hemisphere() -> None:
    assert sampler.utm_epsg_for_lonlat(-123.1, 45.0) == 32610
    assert sampler.utm_epsg_for_lonlat(151.2, -33.8) == 32756
    assert sampler.utm_epsg_for_lonlat(-180.0, 5.0) == 32601
    assert sampler.utm_epsg_for_lonlat(179.9, 5.0) == 32660


def test_patch_geometry_wgs84_builds_50_km_square_in_local_utm() -> None:
    center_lon = -70.0
    center_lat = 41.0
    patch = sampler.patch_geometry_wgs84(center_lon=center_lon, center_lat=center_lat, patch_size_km=50.0)
    transformer = Transformer.from_crs(
        "EPSG:4326",
        f"EPSG:{sampler.utm_epsg_for_lonlat(center_lon, center_lat)}",
        always_xy=True,
    )
    patch_utm = transform_geometry(transformer.transform, patch)

    minx, miny, maxx, maxy = patch_utm.bounds

    assert math.isclose(maxx - minx, 50_000.0, rel_tol=0.002)
    assert math.isclose(maxy - miny, 50_000.0, rel_tol=0.002)
    assert math.isclose(patch_utm.area, 2_500_000_000.0, rel_tol=0.004)


def test_has_overlap_detects_existing_aoi_intersections() -> None:
    existing = [sampler.patch_geometry_wgs84(center_lon=-70.0, center_lat=41.0, patch_size_km=50.0)]

    overlapping = sampler.patch_geometry_wgs84(center_lon=-70.1, center_lat=41.0, patch_size_km=50.0)
    separate = sampler.patch_geometry_wgs84(center_lon=-71.2, center_lat=41.0, patch_size_km=50.0)

    assert sampler.has_overlap(overlapping, existing)
    assert not sampler.has_overlap(separate, existing)


def test_generate_aoi_samples_is_deterministic_and_uses_depth_range(tmp_path: Path) -> None:
    raster_path = tmp_path / "toy_etopo.tif"
    data = np.array(
        [
            [5.0, -10.0, -20.0, 30.0],
            [-40.0, -15.0, -5.0, 1.0],
            [10.0, -25.0, -1.0, 12.0],
            [20.0, -35.0, 2.0, -8.0],
        ],
        dtype=np.float32,
    )
    with rasterio.open(
        raster_path,
        "w",
        driver="GTiff",
        height=data.shape[0],
        width=data.shape[1],
        count=1,
        dtype=data.dtype,
        crs="EPSG:4326",
        transform=from_origin(-72.0, 42.0, 1.0, 1.0),
        nodata=-9999.0,
    ) as dataset:
        dataset.write(data, 1)

    config = sampler.AoiSamplingConfig(
        raster_path=raster_path,
        count=3,
        seed=17,
        patch_size_km=50.0,
        sampling_crs="EPSG:6933",
        output_path=tmp_path / "samples.geojson",
        reverse_geocode=False,
    )

    first = sampler.generate_aoi_samples(config)
    second = sampler.generate_aoi_samples(config)

    assert [sample.aoi_id for sample in first] == ["rep_0001", "rep_0002", "rep_0003"]
    assert [(round(sample.center_lon, 6), round(sample.center_lat, 6)) for sample in first] == [
        (round(sample.center_lon, 6), round(sample.center_lat, 6)) for sample in second
    ]
    assert all(-30.0 <= sample.sample_elevation_m <= 0.0 for sample in first)
    assert all(
        not sampler.has_overlap(sample.geometry, [other.geometry for other in first[:index]])
        for index, sample in enumerate(first)
    )


def test_parser_exposes_sampling_options() -> None:
    help_text = sampler.build_parser().format_help()

    assert "--raster" in help_text
    assert "--count" in help_text
    assert "--output" in help_text
