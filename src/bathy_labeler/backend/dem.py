from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import numpy as np
import rasterio
from pyproj import Transformer


def sample_dem_along_track(
    dem_path: str | Path,
    lon: list[float],
    lat: list[float],
    x_atc_m: list[float],
) -> dict[str, object]:
    path = Path(dem_path).expanduser().resolve()
    if not path.exists():
        raise FileNotFoundError(f"DEM GeoTIFF does not exist: {path}")
    if not path.is_file():
        raise FileNotFoundError(f"DEM GeoTIFF is not a file: {path}")
    if len(lon) != len(lat) or len(lon) != len(x_atc_m):
        raise ValueError("DEM sampling inputs must have matching lengths")

    with rasterio.open(path) as dataset:
        if dataset.crs is None:
            raise ValueError(f"DEM GeoTIFF has no CRS: {path}")
        transformer = Transformer.from_crs("EPSG:4326", dataset.crs, always_xy=True)
        raster_x, raster_y = transformer.transform(lon, lat)
        values = _sample_ordered(dataset, raster_x, raster_y)
        return {
            "dem_path": str(path),
            "dem_name": path.name,
            "crs": str(dataset.crs),
            "x_atc_m": [float(value) for value in x_atc_m],
            "dem_h_m": values,
            "sample_count": len(values),
            "valid_count": sum(value is not None for value in values),
            "sampling_method": "nearest",
        }


def _sample_ordered(dataset: Any, raster_x: list[float], raster_y: list[float]) -> list[float | None]:
    values: list[float | None] = [None] * len(raster_x)
    finite_entries = [
        (index, float(x), float(y))
        for index, (x, y) in enumerate(zip(raster_x, raster_y))
        if math.isfinite(float(x)) and math.isfinite(float(y))
    ]
    sorted_entries = sorted(finite_entries, key=lambda entry: (entry[1], entry[2]))
    sorted_coords = [(x, y) for _, x, y in sorted_entries]
    for (index, _, _), sample in zip(sorted_entries, dataset.sample(sorted_coords, indexes=1, masked=True)):
        values[index] = _sample_value(sample, dataset.nodata)
    return values


def _sample_value(sample: Any, nodata: float | int | None) -> float | None:
    masked = np.ma.asarray(sample)
    if masked.size == 0 or bool(np.ma.is_masked(masked[0])):
        return None
    value = float(masked[0])
    if not math.isfinite(value):
        return None
    if nodata is not None and math.isclose(value, float(nodata), rel_tol=0.0, abs_tol=1e-12):
        return None
    return value
