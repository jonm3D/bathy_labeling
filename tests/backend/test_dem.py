from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

rasterio = pytest.importorskip("rasterio")
pytest.importorskip("pyproj")

from pyproj import Transformer
from rasterio.transform import from_origin

from bathy_labeler.backend.dem import sample_dem_along_track


def write_projected_dem(path: Path) -> tuple[list[float], list[float]]:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = np.asarray(
        [
            [0.0, 1.0, 2.0],
            [10.0, 11.0, 12.0],
            [20.0, 21.0, -9999.0],
        ],
        dtype=np.float32,
    )
    transform = from_origin(-150.0, 150.0, 100.0, 100.0)
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        width=data.shape[1],
        height=data.shape[0],
        count=1,
        dtype=data.dtype,
        crs="EPSG:3857",
        transform=transform,
        nodata=-9999.0,
        tiled=True,
        blockxsize=16,
        blockysize=16,
    ) as dataset:
        dataset.write(data, 1)

    transformer = Transformer.from_crs("EPSG:3857", "EPSG:4326", always_xy=True)
    raster_x = [0.0, 100.0, 100.0, 10_000.0]
    raster_y = [0.0, 0.0, -100.0, 10_000.0]
    lon, lat = transformer.transform(raster_x, raster_y)
    return list(lon), list(lat)


def test_sample_dem_along_track_transforms_coordinates_and_preserves_order(tmp_path: Path) -> None:
    dem_path = tmp_path / "reference_dem.tif"
    lon, lat = write_projected_dem(dem_path)

    payload = sample_dem_along_track(
        dem_path=dem_path,
        lon=lon,
        lat=lat,
        x_atc_m=[0.0, 100.0, 200.0, 300.0],
    )

    assert payload["dem_name"] == "reference_dem.tif"
    assert payload["crs"] == "EPSG:3857"
    assert payload["x_atc_m"] == [0.0, 100.0, 200.0, 300.0]
    assert payload["dem_h_m"] == [11.0, 12.0, None, None]
    assert payload["sample_count"] == 4
    assert payload["valid_count"] == 2


def test_sample_dem_rejects_missing_path(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        sample_dem_along_track(
            dem_path=tmp_path / "missing.tif",
            lon=[0.0],
            lat=[0.0],
            x_atc_m=[0.0],
        )
