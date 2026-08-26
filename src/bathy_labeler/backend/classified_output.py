from __future__ import annotations

import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Sequence

import geopandas as gpd
import numpy as np
import pandas as pd

BATHY_CLASS = 40
OUTPUT_LAYERS = ("photons", "bathymetry")

_STANDARD_SOURCE_COLUMNS = {
    "class_ph",
    "cycle",
    "geometry",
    "lat_ph",
    "lon_ph",
    "ortho_h",
    "rgt",
    "spot",
    "time_ns",
}


def labeled_utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def canonical_photon_id(
    acquisition_date: str,
    rgt: int,
    cycle: int,
    spot: int,
    track_index: int,
) -> str:
    if len(acquisition_date) != 8 or not acquisition_date.isdigit():
        raise ValueError(f"Acquisition date must be YYYYMMDD: {acquisition_date!r}")
    if not 0 <= rgt <= 9999:
        raise ValueError(f"RGT is outside the four-digit field: {rgt}")
    if not 0 <= cycle <= 999:
        raise ValueError(f"Cycle is outside the three-digit field: {cycle}")
    if not 0 <= spot <= 9:
        raise ValueError(f"Spot is outside the one-digit field: {spot}")
    if track_index < 0:
        raise ValueError(f"Track index must be non-negative: {track_index}")
    return f"{acquisition_date}_{rgt:04d}_{cycle:03d}_{spot:d}_" f"{track_index:08d}"


def build_classified_frame(
    source: gpd.GeoDataFrame,
    *,
    acquisition_dates: Sequence[str],
    track_indices: Sequence[int],
    rgt: int,
    cycle: int,
    spot: int,
    class_manual: Sequence[int],
    time_labeled_utc: str,
    time_utc: Sequence[str] | None = None,
    source_product: str = "atl24",
    height_column: str = "ortho_h",
    source_class_column: str | None = "class_ph",
) -> gpd.GeoDataFrame:
    """Normalize one ICESat-2 track into the classified output schema."""
    if source.crs is None:
        raise ValueError("Classified output source has no CRS")
    frame = source.reset_index(drop=True).to_crs("EPSG:4326")
    count = len(frame)
    sequences = {
        "acquisition_dates": acquisition_dates,
        "track_indices": track_indices,
        "class_manual": class_manual,
    }
    if time_utc is not None:
        sequences["time_utc"] = time_utc
    for name, values in sequences.items():
        if len(values) != count:
            raise ValueError(
                f"{name} length mismatch: expected {count}, found {len(values)}"
            )
    if height_column not in frame:
        raise ValueError(f"{source_product.upper()} output requires {height_column}")
    if source_class_column is not None and source_class_column not in frame:
        raise ValueError(
            f"{source_product.upper()} output requires {source_class_column}"
        )

    atl24_class = pd.Series(pd.NA, index=frame.index, dtype="Int16")
    if source_class_column is not None:
        atl24_class = pd.to_numeric(frame[source_class_column], errors="coerce").astype(
            "Int16"
        )

    dates = [str(value) for value in acquisition_dates]
    indices = [int(value) for value in track_indices]
    output = gpd.GeoDataFrame(
        {
            "photon_id": [
                canonical_photon_id(date, rgt, cycle, spot, index)
                for date, index in zip(dates, indices)
            ],
            "track_index": indices,
            "acquisition_date": dates,
            "rgt": np.full(count, rgt, dtype=np.int16),
            "cycle": np.full(count, cycle, dtype=np.int16),
            "spot": np.full(count, spot, dtype=np.int8),
            "elevation_m": pd.to_numeric(
                frame[height_column], errors="coerce"
            ).to_numpy(),
            "class_manual": np.asarray(class_manual, dtype=np.int16),
            "time_labeled_utc": np.full(count, time_labeled_utc, dtype=object),
            "atl24_class": atl24_class,
        },
        geometry=frame.geometry,
        crs="EPSG:4326",
    )
    if time_utc is not None:
        output.insert(3, "time_utc", [str(value) for value in time_utc])

    for column in frame.columns:
        if column in _STANDARD_SOURCE_COLUMNS or column.startswith("_"):
            continue
        output_name = (
            column
            if column.startswith(f"{source_product}_")
            else f"{source_product}_{column}"
        )
        if output_name in output:
            raise ValueError(f"Duplicate classified output field: {output_name}")
        output[output_name] = _gpkg_safe_series(frame[column])
    return output


def write_classified_geopackage(
    output_path: Path,
    photons: gpd.GeoDataFrame,
) -> Path | None:
    """Atomically write all photons and a bathymetry subset to one GPKG."""
    required = {"photon_id", "class_manual", "geometry"}
    missing = sorted(required - set(photons.columns))
    if missing:
        raise ValueError(f"Classified output is missing fields: {', '.join(missing)}")
    if photons["photon_id"].duplicated().any():
        raise ValueError("Classified output contains duplicate photon IDs")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    backup_path = _backup_existing(output_path)
    temporary = output_path.with_name(
        f".{output_path.stem}.{uuid.uuid4().hex}.tmp.gpkg"
    )
    try:
        photons.to_file(temporary, layer="photons", driver="GPKG")
        bathymetry = photons.loc[photons["class_manual"] == BATHY_CLASS]
        bathymetry.to_file(
            temporary,
            layer="bathymetry",
            driver="GPKG",
            mode="a",
        )
        temporary.replace(output_path)
    except Exception:
        if temporary.exists():
            temporary.unlink()
        raise
    return backup_path


def read_manual_classes(
    output_path: Path,
    expected_photon_ids: Iterable[str],
) -> list[int]:
    photons = gpd.read_file(output_path, layer="photons")
    required = {"photon_id", "class_manual"}
    missing = sorted(required - set(photons.columns))
    if missing:
        raise ValueError(
            f"Classified GeoPackage is missing fields: {', '.join(missing)}"
        )
    if photons["photon_id"].duplicated().any():
        raise ValueError("Classified GeoPackage contains duplicate photon IDs")
    actual = {
        str(photon_id): int(class_manual)
        for photon_id, class_manual in zip(
            photons["photon_id"], photons["class_manual"]
        )
    }
    expected = [str(value) for value in expected_photon_ids]
    if set(actual) != set(expected):
        raise ValueError(
            "Classified GeoPackage photon IDs do not match the frozen input track"
        )
    return [actual[photon_id] for photon_id in expected]


def output_is_valid(
    output_path: Path,
    expected_photon_ids: Iterable[str],
) -> bool:
    try:
        read_manual_classes(output_path, expected_photon_ids)
        return set(gpd.list_layers(output_path)["name"]) == set(OUTPUT_LAYERS)
    except (OSError, RuntimeError, ValueError):
        return False


def _backup_existing(output_path: Path) -> Path | None:
    if not output_path.exists():
        return None
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    backup_path = (
        output_path.parent
        / ".bathy_labeler_backups"
        / output_path.stem
        / timestamp
        / output_path.name
    )
    backup_path.parent.mkdir(parents=True, exist_ok=False)
    shutil.copy2(output_path, backup_path)
    return backup_path


def _gpkg_safe_series(series: pd.Series) -> pd.Series:
    if pd.api.types.is_unsigned_integer_dtype(series.dtype):
        return series.astype(np.int64)
    if pd.api.types.is_bool_dtype(series.dtype):
        return series.astype(np.int8)
    if pd.api.types.is_datetime64_any_dtype(series.dtype):
        return series.astype(str)
    if series.dtype == object:
        return series.map(
            lambda value: (
                value.decode("utf-8", errors="replace")
                if isinstance(value, bytes)
                else value
            )
        )
    return series
