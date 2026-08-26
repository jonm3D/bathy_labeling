from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import numpy as np
import pytest
import rasterio
from PIL import Image
from rasterio.transform import from_origin
from shapely.geometry import Point, box

from bathy_labeler.summary_plots import (
    _elevation_norm,
    _read_dem_for_plot,
    collect_manual_bathymetry,
    create_site_summary_plots,
)


def _write_track(path: Path, elevations: list[float]) -> None:
    photons = gpd.GeoDataFrame(
        {
            "elevation_m": elevations or [1.0],
            "class_manual": [40] * len(elevations) or [0],
        },
        geometry=[
            Point(-64.7 + index * 0.001, 17.75)
            for index in range(max(1, len(elevations)))
        ],
        crs="EPSG:4326",
    )
    bathymetry = photons.loc[photons["class_manual"] == 40]
    photons.to_file(path, layer="photons", driver="GPKG")
    bathymetry.to_file(path, layer="bathymetry", driver="GPKG", mode="a")


def test_collect_manual_bathymetry_counts_only_nonempty_tracks(
    tmp_path: Path,
) -> None:
    classified = tmp_path / "classified"
    classified.mkdir()
    _write_track(classified / "track_a.gpkg", [-4.0, -2.0])
    _write_track(classified / "track_b.gpkg", [])

    result = collect_manual_bathymetry(classified)

    assert result.saved_track_count == 2
    assert result.track_count == 1
    assert result.photon_count == 2


def test_elevation_norm_is_symmetric_about_zero() -> None:
    norm = _elevation_norm(np.asarray([-12.0, -2.0]), np.ma.asarray([8.0]))

    assert norm.vmin == -12.0
    assert norm.vcenter == 0.0
    assert norm.vmax == 12.0


def test_reference_dem_must_be_egm2008(tmp_path: Path) -> None:
    path = tmp_path / "native_dem.tif"
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        width=2,
        height=2,
        count=1,
        dtype="float32",
        crs="EPSG:26917",
        transform=from_origin(500_000, 2_900_000, 1, 1),
        nodata=-9999,
    ) as output:
        output.write(np.ones((2, 2), dtype="float32"), 1)
        output.update_tags(vertical_datum="NAVD88")

    with pytest.raises(ValueError, match="transformed to EGM2008"):
        _read_dem_for_plot(path)


def test_summary_plots_have_requested_physical_dimensions(
    tmp_path: Path,
) -> None:
    classified = tmp_path / "classified"
    classified.mkdir()
    _write_track(classified / "track_a.gpkg", [-4.0, -2.0])
    aoi_path = tmp_path / "aoi.gpkg"
    gpd.GeoDataFrame(
        {"name": ["AOI"]},
        geometry=[box(-64.71, 17.74, -64.68, 17.76)],
        crs="EPSG:4326",
    ).to_file(aoi_path)

    result = create_site_summary_plots(
        site_name="Test Site",
        site_slug="test_site",
        aoi_path=aoi_path,
        classified_dir=classified,
        output_dir=tmp_path / "figures",
        add_osm=False,
        dpi=100,
    )

    assert Image.open(result.map_path).size == (800, 800)
    assert Image.open(result.histogram_path).size == (400, 400)
