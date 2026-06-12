from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import geopandas as gpd
import numpy as np
import rasterio
from pyproj import CRS, Transformer
from rasterio.enums import Resampling
from rasterio.transform import xy
from rasterio.vrt import WarpedVRT
from shapely.geometry import Polygon
from shapely.ops import transform as transform_geometry

GENERATION_VERSION = "representative-aoi-sampling-v1"


@dataclass(frozen=True)
class AoiSamplingConfig:
    raster_path: Path
    output_path: Path
    count: int
    seed: int = 20260612
    patch_size_km: float = 50.0
    min_elevation_m: float = -30.0
    max_elevation_m: float = 0.0
    sampling_crs: str = "EPSG:6933"
    reverse_geocode: bool = True
    max_attempts_multiplier: int = 200


@dataclass(frozen=True)
class AoiSample:
    aoi_id: str
    aoi_name: str
    center_lon: float
    center_lat: float
    sample_elevation_m: float
    patch_size_km: float
    area_km2: float
    utm_epsg: int
    sampling_crs: str
    seed: int
    source_raster: str
    geometry: Polygon

    def properties(self) -> dict[str, object]:
        return {
            "aoi_id": self.aoi_id,
            "aoi_name": self.aoi_name,
            "pool": "representative",
            "center_lon": self.center_lon,
            "center_lat": self.center_lat,
            "sample_elevation_m": self.sample_elevation_m,
            "patch_size_km": self.patch_size_km,
            "area_km2": self.area_km2,
            "utm_epsg": self.utm_epsg,
            "sampling_crs": self.sampling_crs,
            "seed": self.seed,
            "source_raster": self.source_raster,
            "generation_version": GENERATION_VERSION,
        }


@dataclass(frozen=True)
class _CandidateCells:
    rows: np.ndarray
    cols: np.ndarray
    values: np.ndarray
    transform: object
    crs: CRS


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate representative shallow-marine AOIs from ETOPO/GEBCO.")
    parser.add_argument("--raster", required=True, type=Path, help="ETOPO/GEBCO-like elevation raster.")
    parser.add_argument("--output", required=True, type=Path, help="Output GeoPackage, GeoJSON, or shapefile path.")
    parser.add_argument("--count", required=True, type=int, help="Number of representative AOIs to generate.")
    parser.add_argument("--seed", default=20260612, type=int, help="Deterministic random seed.")
    parser.add_argument("--patch-size-km", default=50.0, type=float, help="Square AOI side length.")
    parser.add_argument("--min-elevation-m", default=-30.0, type=float, help="Minimum eligible elevation.")
    parser.add_argument("--max-elevation-m", default=0.0, type=float, help="Maximum eligible elevation.")
    parser.add_argument("--sampling-crs", default="EPSG:6933", help="Equal-area CRS for raster sampling.")
    parser.add_argument(
        "--existing-aoi",
        action="append",
        default=[],
        type=Path,
        help="Existing AOI vector file to avoid overlapping. May be repeated.",
    )
    parser.add_argument(
        "--coordinate-names",
        action="store_true",
        help="Use coordinate-derived names instead of reverse-geocode names.",
    )
    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    existing_geometries = []
    for path in args.existing_aoi:
        existing_geometries.extend(load_existing_geometries(path))

    config = AoiSamplingConfig(
        raster_path=args.raster,
        output_path=args.output,
        count=args.count,
        seed=args.seed,
        patch_size_km=args.patch_size_km,
        min_elevation_m=args.min_elevation_m,
        max_elevation_m=args.max_elevation_m,
        sampling_crs=args.sampling_crs,
        reverse_geocode=not args.coordinate_names,
    )
    samples = generate_aoi_samples(config, existing_geometries=existing_geometries)
    write_aoi_samples(samples, args.output)
    print(f"Wrote {len(samples)} AOIs to {args.output}")


def utm_epsg_for_lonlat(lon: float, lat: float) -> int:
    lon_for_zone = min(max(lon, -180.0), 179.999999999)
    zone = int((lon_for_zone + 180.0) // 6.0) + 1
    zone = min(max(zone, 1), 60)
    return (32600 if lat >= 0.0 else 32700) + zone


def patch_geometry_wgs84(center_lon: float, center_lat: float, patch_size_km: float = 50.0) -> Polygon:
    utm_epsg = utm_epsg_for_lonlat(center_lon, center_lat)
    to_utm = Transformer.from_crs("EPSG:4326", f"EPSG:{utm_epsg}", always_xy=True)
    to_wgs84 = Transformer.from_crs(f"EPSG:{utm_epsg}", "EPSG:4326", always_xy=True)
    center_x, center_y = to_utm.transform(center_lon, center_lat)
    half_size_m = patch_size_km * 1000.0 / 2.0
    patch_utm = Polygon(
        [
            (center_x - half_size_m, center_y - half_size_m),
            (center_x + half_size_m, center_y - half_size_m),
            (center_x + half_size_m, center_y + half_size_m),
            (center_x - half_size_m, center_y + half_size_m),
            (center_x - half_size_m, center_y - half_size_m),
        ]
    )
    return transform_geometry(to_wgs84.transform, patch_utm)


def has_overlap(candidate: Polygon, existing_geometries: Iterable[Polygon]) -> bool:
    for existing in existing_geometries:
        if existing.is_empty:
            continue
        intersection = candidate.intersection(existing)
        if not intersection.is_empty and intersection.area > 0.0:
            return True
    return False


def load_existing_geometries(path: Path) -> list[Polygon]:
    frame = gpd.read_file(path)
    if frame.crs is None:
        frame = frame.set_crs("EPSG:4326")
    else:
        frame = frame.to_crs("EPSG:4326")
    return [geometry for geometry in frame.geometry if geometry is not None and not geometry.is_empty]


def generate_aoi_samples(
    config: AoiSamplingConfig,
    existing_geometries: Iterable[Polygon] | None = None,
) -> list[AoiSample]:
    if config.count < 1:
        raise ValueError("count must be at least 1")
    if config.patch_size_km <= 0:
        raise ValueError("patch_size_km must be positive")
    if config.min_elevation_m > config.max_elevation_m:
        raise ValueError("min_elevation_m must be <= max_elevation_m")

    candidates = _candidate_cells(config)
    if len(candidates.rows) == 0:
        raise ValueError(
            f"No raster cells found in elevation range "
            f"[{config.min_elevation_m}, {config.max_elevation_m}]"
        )

    selected: list[AoiSample] = []
    blocked_geometries = list(existing_geometries or [])
    rng = np.random.default_rng(config.seed)
    max_attempts = max(config.count * config.max_attempts_multiplier, config.count)
    to_wgs84 = Transformer.from_crs(candidates.crs, "EPSG:4326", always_xy=True)
    used_indices: set[int] = set()

    for _ in range(max_attempts):
        if len(selected) == config.count:
            break
        if len(used_indices) == len(candidates.rows):
            break

        candidate_index = int(rng.integers(0, len(candidates.rows)))
        if candidate_index in used_indices:
            continue
        used_indices.add(candidate_index)

        row = int(candidates.rows[candidate_index])
        col = int(candidates.cols[candidate_index])
        sample_x, sample_y = xy(candidates.transform, row, col, offset="center")
        lon, lat = to_wgs84.transform(sample_x, sample_y)
        if not np.isfinite(lon) or not np.isfinite(lat):
            continue

        geometry = patch_geometry_wgs84(lon, lat, config.patch_size_km)
        if not geometry.is_valid or geometry.is_empty:
            continue
        if has_overlap(geometry, blocked_geometries):
            continue

        sample_number = len(selected) + 1
        aoi_id = f"rep_{sample_number:04d}"
        sample = AoiSample(
            aoi_id=aoi_id,
            aoi_name=_coordinate_name(aoi_id, lon, lat),
            center_lon=float(lon),
            center_lat=float(lat),
            sample_elevation_m=float(candidates.values[candidate_index]),
            patch_size_km=config.patch_size_km,
            area_km2=config.patch_size_km * config.patch_size_km,
            utm_epsg=utm_epsg_for_lonlat(lon, lat),
            sampling_crs=str(candidates.crs),
            seed=config.seed,
            source_raster=str(config.raster_path),
            geometry=geometry,
        )
        selected.append(sample)
        blocked_geometries.append(geometry)

    if len(selected) != config.count:
        raise RuntimeError(
            f"Generated {len(selected)} AOIs after {max_attempts} attempts; "
            f"requested {config.count}. Existing AOIs or patch size may be too restrictive."
        )

    if config.reverse_geocode:
        selected = _with_reverse_geocode_names(selected)
    return selected


def write_aoi_samples(samples: list[AoiSample], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    frame = gpd.GeoDataFrame(
        [sample.properties() for sample in samples],
        geometry=[sample.geometry for sample in samples],
        crs="EPSG:4326",
    )
    if output_path.suffix.lower() in {".json", ".geojson"}:
        frame.to_file(output_path, driver="GeoJSON")
    else:
        frame.to_file(output_path)


def _candidate_cells(config: AoiSamplingConfig) -> _CandidateCells:
    rows: list[np.ndarray] = []
    cols: list[np.ndarray] = []
    values: list[np.ndarray] = []
    with rasterio.open(config.raster_path) as source:
        with WarpedVRT(source, crs=config.sampling_crs, resampling=Resampling.nearest) as vrt:
            for _, window in vrt.block_windows(1):
                data = vrt.read(1, window=window, masked=True)
                valid_data = np.asarray(data.filled(np.nan), dtype=np.float32)
                eligible = (
                    np.isfinite(valid_data)
                    & (valid_data >= config.min_elevation_m)
                    & (valid_data <= config.max_elevation_m)
                )
                local_rows, local_cols = np.nonzero(eligible)
                if len(local_rows) == 0:
                    continue
                rows.append((local_rows + int(window.row_off)).astype(np.int32))
                cols.append((local_cols + int(window.col_off)).astype(np.int32))
                values.append(valid_data[eligible].astype(np.float32))

            if not rows:
                return _CandidateCells(
                    rows=np.array([], dtype=np.int32),
                    cols=np.array([], dtype=np.int32),
                    values=np.array([], dtype=np.float32),
                    transform=vrt.transform,
                    crs=CRS.from_user_input(vrt.crs),
                )

            return _CandidateCells(
                rows=np.concatenate(rows),
                cols=np.concatenate(cols),
                values=np.concatenate(values),
                transform=vrt.transform,
                crs=CRS.from_user_input(vrt.crs),
            )


def _with_reverse_geocode_names(samples: list[AoiSample]) -> list[AoiSample]:
    import dataclasses

    import reverse_geocode

    coordinates = [(sample.center_lat, sample.center_lon) for sample in samples]
    geocodes = reverse_geocode.search(coordinates)
    named_samples = []
    for sample, geocode in zip(samples, geocodes):
        named_samples.append(dataclasses.replace(sample, aoi_name=_geocode_name(sample.aoi_id, geocode)))
    return named_samples


def _geocode_name(aoi_id: str, geocode: dict[str, object]) -> str:
    parts = [
        str(geocode.get("city") or ""),
        str(geocode.get("state") or geocode.get("country") or geocode.get("country_code") or ""),
    ]
    slug = _slugify("_".join(part for part in parts if part))
    return f"{aoi_id}_{slug}" if slug else aoi_id


def _coordinate_name(aoi_id: str, lon: float, lat: float) -> str:
    lat_suffix = "N" if lat >= 0 else "S"
    lon_suffix = "E" if lon >= 0 else "W"
    return f"{aoi_id}_{abs(lat):05.2f}{lat_suffix}_{abs(lon):06.2f}{lon_suffix}"


def _slugify(value: str) -> str:
    safe = [character.lower() if character.isalnum() else "_" for character in value]
    collapsed = "_".join(part for part in "".join(safe).split("_") if part)
    return collapsed[:80]


if __name__ == "__main__":
    main()
