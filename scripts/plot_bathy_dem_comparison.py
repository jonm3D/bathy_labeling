#!/usr/bin/env python3
from __future__ import annotations

import argparse
import math
import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

import h5py
import numpy as np
import rasterio
from pyproj import Transformer

try:
    from bathy_labeler.backend.models import BEAM_NAMES
except (
    ImportError
):  # pragma: no cover - keeps the script usable outside editable installs.
    BEAM_NAMES = ("gt1l", "gt1r", "gt2l", "gt2r", "gt3l", "gt3r")


DEFAULT_BATHY_CLASS = 40
DEFAULT_MAX_PLOT_POINTS = 200_000
DEFAULT_RMSE_BIN_WIDTH_M = 1.0
RMSE_AXIS_COLOR = "#7a7a7a"
COUNT_AXIS_COLOR = "#111111"
ATL24_COLOR = "#2675a6"
MANUAL_COLOR = "#d7852f"
WGS84_CRS = "EPSG:4326"
REQUIRED_PHOTON_DATASETS = ("lon_ph", "lat_ph", "ortho_h", "class_ph")
MANUAL_BEAM_PATTERN = re.compile(r"_(gt[123][lr])_manual\.h5$", re.IGNORECASE)
LOCATION_DATE_RANGES = {
    "duck": ("Duck", "2019-06-18 to 2019-06-25"),
    "guam": ("Guam", "2020-01-20 to 2020-02-15"),
}


@dataclass(frozen=True)
class PhotonCollection:
    lon: np.ndarray
    lat: np.ndarray
    elevation: np.ndarray
    file_count: int
    beam_count: int
    sources: list[str]
    warnings: list[str]

    @property
    def photon_count(self) -> int:
        return int(self.elevation.size)


@dataclass(frozen=True)
class ComparisonDataset:
    label: str
    dem_elevation: np.ndarray
    photon_elevation: np.ndarray
    bathy_count: int
    valid_count: int
    invalid_dem_count: int
    file_count: int
    beam_count: int
    warnings: list[str]

    @property
    def residuals(self) -> np.ndarray:
        return self.photon_elevation - self.dem_elevation


def manual_beam_from_filename(path: str | Path) -> str | None:
    match = MANUAL_BEAM_PATTERN.search(Path(path).name)
    if match is None:
        return None
    return match.group(1).lower()


def collect_bathy_photons(
    h5_dir: str | Path,
    *,
    bathy_class: int = DEFAULT_BATHY_CLASS,
    elevation_dataset: str = "ortho_h",
) -> PhotonCollection:
    root = Path(h5_dir).expanduser().resolve()
    if not root.exists():
        raise FileNotFoundError(f"H5 folder does not exist: {root}")
    if not root.is_dir():
        raise NotADirectoryError(f"H5 path is not a folder: {root}")

    required = ("lon_ph", "lat_ph", elevation_dataset, "class_ph")
    lon_parts: list[np.ndarray] = []
    lat_parts: list[np.ndarray] = []
    elevation_parts: list[np.ndarray] = []
    sources: list[str] = []
    warnings: list[str] = []
    file_count = 0
    beam_count = 0

    for path in sorted(
        root.rglob("*.h5"), key=lambda item: item.relative_to(root).as_posix()
    ):
        relative_path = path.relative_to(root)
        if ".bathy_labeler_backups" in relative_path.parts:
            continue
        try:
            with h5py.File(path, "r") as h5:
                beams = _beams_to_read(path, h5)
                if not beams:
                    warnings.append(
                        f"{path.relative_to(root).as_posix()}: no ATL24 beam groups found"
                    )
                    continue
                file_used = False
                for beam in beams:
                    relative_source = (
                        f"{path.relative_to(root).as_posix()}/{beam}"
                    )
                    if beam not in h5:
                        warnings.append(
                            f"{relative_source}: beam group missing"
                        )
                        continue
                    group = h5[beam]
                    missing = [name for name in required if name not in group]
                    if missing:
                        warnings.append(
                            f"{relative_source}: missing datasets: {', '.join(missing)}"
                        )
                        continue
                    try:
                        lon = _read_1d_dataset(group, "lon_ph")
                        lat = _read_1d_dataset(group, "lat_ph")
                        elevation = _read_1d_dataset(group, elevation_dataset)
                        class_ph = _read_1d_dataset(group, "class_ph")
                    except ValueError as exc:
                        warnings.append(f"{relative_source}: {exc}")
                        continue
                    lengths = {
                        lon.size,
                        lat.size,
                        elevation.size,
                        class_ph.size,
                    }
                    if len(lengths) != 1:
                        warnings.append(
                            f"{relative_source}: dataset lengths differ "
                            f"(lon={lon.size}, lat={lat.size}, elevation={elevation.size}, class_ph={class_ph.size})"
                        )
                        continue

                    mask = (
                        (class_ph.astype(np.int64) == int(bathy_class))
                        & np.isfinite(lon)
                        & np.isfinite(lat)
                        & np.isfinite(elevation)
                    )
                    if np.any(mask):
                        lon_parts.append(lon[mask])
                        lat_parts.append(lat[mask])
                        elevation_parts.append(elevation[mask])
                    sources.append(relative_source)
                    beam_count += 1
                    file_used = True
                if file_used:
                    file_count += 1
        except OSError as exc:
            warnings.append(
                f"{path.relative_to(root).as_posix()}: unable to read HDF5 file: {exc}"
            )

    return PhotonCollection(
        lon=_concat_or_empty(lon_parts),
        lat=_concat_or_empty(lat_parts),
        elevation=_concat_or_empty(elevation_parts),
        file_count=file_count,
        beam_count=beam_count,
        sources=sources,
        warnings=warnings,
    )


def sample_dem_at_photons(
    dem_path: str | Path, lon: np.ndarray, lat: np.ndarray
) -> np.ndarray:
    path = Path(dem_path).expanduser().resolve()
    if not path.exists():
        raise FileNotFoundError(f"DEM GeoTIFF does not exist: {path}")
    if not path.is_file():
        raise FileNotFoundError(f"DEM path is not a file: {path}")
    if lon.shape != lat.shape:
        raise ValueError("lon and lat arrays must have matching shapes")

    dem_values = np.full(lon.shape, np.nan, dtype=float)
    finite = np.isfinite(lon) & np.isfinite(lat)
    if not np.any(finite):
        return dem_values

    with rasterio.open(path) as dataset:
        if dataset.crs is None:
            raise ValueError(f"DEM GeoTIFF has no CRS: {path}")
        transformer = Transformer.from_crs(
            WGS84_CRS, dataset.crs, always_xy=True
        )
        raster_x, raster_y = transformer.transform(
            lon[finite].tolist(), lat[finite].tolist()
        )
        raster_x = np.asarray(raster_x, dtype=float)
        raster_y = np.asarray(raster_y, dtype=float)
        finite_raster = np.isfinite(raster_x) & np.isfinite(raster_y)
        finite_indices = np.flatnonzero(finite)
        sample_indices = finite_indices[finite_raster]
        coords = list(
            zip(
                raster_x[finite_raster].tolist(),
                raster_y[finite_raster].tolist(),
            )
        )
        for index, sample in zip(
            sample_indices,
            dataset.sample(coords, indexes=1, masked=True),
            strict=True,
        ):
            value = _sample_value(sample, dataset.nodata)
            if value is not None:
                dem_values[index] = value
    return dem_values


def build_comparison_dataset(
    label: str, photons: PhotonCollection, dem_path: str | Path
) -> ComparisonDataset:
    dem_elevation = sample_dem_at_photons(dem_path, photons.lon, photons.lat)
    valid = np.isfinite(dem_elevation) & np.isfinite(photons.elevation)
    valid_count = int(np.count_nonzero(valid))
    return ComparisonDataset(
        label=label,
        dem_elevation=dem_elevation[valid],
        photon_elevation=photons.elevation[valid],
        bathy_count=photons.photon_count,
        valid_count=valid_count,
        invalid_dem_count=photons.photon_count - valid_count,
        file_count=photons.file_count,
        beam_count=photons.beam_count,
        warnings=photons.warnings,
    )


def plot_comparison(
    original: ComparisonDataset,
    relabeled: ComparisonDataset,
    output_path: str | Path,
    *,
    location: str = "Location",
    lidar_date_range: str = "Date to go here",
    max_points: int = DEFAULT_MAX_PLOT_POINTS,
    seed: int = 42,
    dpi: int = 300,
) -> Path:
    _configure_plot_cache()
    plt = _plotting_module()

    target = Path(output_path).expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)

    fig, axes = plt.subplots(1, 2, figsize=(12.0, 5.8), constrained_layout=True)
    limits = _shared_axis_limits([original, relabeled])
    for ax, dataset in zip(axes, [original, relabeled], strict=True):
        _draw_scatter_panel(
            ax, dataset, limits=limits, max_points=max_points, seed=seed
        )
    fig.suptitle(_figure_title(location, lidar_date_range), fontsize=14)
    fig.savefig(target, dpi=dpi)
    plt.close(fig)
    return target


def plot_depth_summary(
    original: ComparisonDataset,
    relabeled: ComparisonDataset,
    output_path: str | Path,
    *,
    location: str = "Location",
    lidar_date_range: str = "Date to go here",
    dpi: int = 300,
) -> Path:
    _configure_plot_cache()
    plt = _plotting_module()

    target = Path(output_path).expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    fig, count_ax = plt.subplots(figsize=(8.2, 5.1), constrained_layout=True)
    rmse_ax = count_ax.twinx()
    edges = _shared_reference_bin_edges([original, relabeled])
    for dataset in (original, relabeled):
        centers, counts = binned_photon_counts_by_reference(
            dataset.dem_elevation,
            edges=edges,
            include_empty=True,
        )
        if centers.size:
            count_ax.plot(
                centers,
                counts,
                **_depth_summary_line_style(dataset.label, "count"),
                label=f"{dataset.label} photons",
            )
        rmse_centers, rmse = binned_rmse_by_reference(
            dataset.dem_elevation,
            dataset.photon_elevation,
            edges=edges,
            include_empty=True,
        )
        if rmse_centers.size:
            rmse_ax.plot(
                rmse_centers,
                rmse,
                **_depth_summary_line_style(dataset.label, "rmse"),
                label=f"{dataset.label} RMSE",
            )
    _format_depth_summary_axes(
        count_ax,
        rmse_ax,
        title=None,
    )
    count_ax.set_xlim(float(edges[0]), float(edges[-1]))
    count_ax.set_ylim(bottom=1)
    rmse_ax.set_ylim(bottom=0)
    count_handles, count_labels = count_ax.get_legend_handles_labels()
    rmse_handles, rmse_labels = rmse_ax.get_legend_handles_labels()
    count_ax.legend(
        count_handles + rmse_handles,
        count_labels + rmse_labels,
        frameon=False,
        ncol=2,
        loc="upper center",
        bbox_to_anchor=(0.5, -0.16),
    )
    fig.suptitle(_figure_title(location, lidar_date_range), fontsize=13)
    fig.savefig(target, dpi=dpi)
    plt.close(fig)
    return target


def plot_site_figures(
    original: ComparisonDataset,
    relabeled: ComparisonDataset,
    output_path: str | Path,
    *,
    location: str = "Location",
    lidar_date_range: str = "Date to go here",
    max_points: int = DEFAULT_MAX_PLOT_POINTS,
    seed: int = 42,
    dpi: int = 300,
) -> dict[str, Path]:
    scatter_path = Path(output_path).expanduser().resolve()
    depth_summary_path = _sibling_output_path(scatter_path, "Depth_Summary")
    return {
        "scatter": plot_comparison(
            original,
            relabeled,
            scatter_path,
            location=location,
            lidar_date_range=lidar_date_range,
            max_points=max_points,
            seed=seed,
            dpi=dpi,
        ),
        "depth_summary": plot_depth_summary(
            original,
            relabeled,
            depth_summary_path,
            location=location,
            lidar_date_range=lidar_date_range,
            dpi=dpi,
        ),
    }


def _plotting_module() -> object:
    import matplotlib

    matplotlib.use("Agg")
    matplotlib.rcParams["svg.fonttype"] = "none"
    import matplotlib.pyplot as plt

    return plt


def _sibling_output_path(path: Path, suffix: str) -> Path:
    return path.with_name(f"{path.stem}_{suffix}{path.suffix}")


def _configure_plot_cache() -> None:
    cache_root = Path(tempfile.gettempdir()) / "bathy_dem_comparison_cache"
    matplotlib_cache = cache_root / "matplotlib"
    xdg_cache = cache_root / "xdg"
    matplotlib_cache.mkdir(parents=True, exist_ok=True)
    xdg_cache.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("MPLCONFIGDIR", str(matplotlib_cache))
    os.environ.setdefault("XDG_CACHE_HOME", str(xdg_cache))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Create ATL24 bathy photon vs. reference DEM QA/QC figures. "
            "Both the 1:1 comparison and depth-summary figures are always generated."
        )
    )
    parser.add_argument(
        "original_h5_dir",
        type=Path,
        help="Folder containing original ATL24 H5 files",
    )
    parser.add_argument(
        "relabeled_h5_dir",
        type=Path,
        help="Folder containing relabeled/manual ATL24 H5 files",
    )
    parser.add_argument(
        "reference_dem", type=Path, help="Reference DEM GeoTIFF"
    )
    parser.add_argument(
        "output_figure",
        type=Path,
        help="Output 1:1 comparison figure path. A depth-summary sibling figure is always written next to it.",
    )
    parser.add_argument(
        "--bathy-class",
        type=int,
        default=DEFAULT_BATHY_CLASS,
        help="ATL24 class_ph value for bathy",
    )
    parser.add_argument(
        "--elevation-dataset",
        default="ortho_h",
        help="Photon elevation dataset to plot",
    )
    parser.add_argument(
        "--max-points",
        type=int,
        default=DEFAULT_MAX_PLOT_POINTS,
        help="Maximum points plotted per panel",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Random seed used when downsampling points for plotting",
    )
    parser.add_argument(
        "--dpi", type=int, default=300, help="Output figure DPI"
    )
    parser.add_argument(
        "--location", help="Location name to use in the figure title"
    )
    parser.add_argument(
        "--lidar-date-range",
        help="Lidar DEM date range to use in the figure title",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    original_photons = collect_bathy_photons(
        args.original_h5_dir,
        bathy_class=args.bathy_class,
        elevation_dataset=args.elevation_dataset,
    )
    relabeled_photons = collect_bathy_photons(
        args.relabeled_h5_dir,
        bathy_class=args.bathy_class,
        elevation_dataset=args.elevation_dataset,
    )
    original = build_comparison_dataset(
        "ATL24", original_photons, args.reference_dem
    )
    relabeled = build_comparison_dataset(
        "Manual", relabeled_photons, args.reference_dem
    )
    inferred_location, inferred_date_range = infer_plot_metadata(
        args.output_figure,
        args.original_h5_dir,
        args.relabeled_h5_dir,
        args.reference_dem,
    )
    outputs = plot_site_figures(
        original,
        relabeled,
        args.output_figure,
        location=args.location or inferred_location,
        lidar_date_range=args.lidar_date_range or inferred_date_range,
        max_points=args.max_points,
        seed=args.seed,
        dpi=args.dpi,
    )
    for label, output in outputs.items():
        print(f"Wrote {label}: {output}")
    for dataset in (original, relabeled):
        print(
            f"{dataset.label}: {dataset.valid_count:,} valid DEM samples from "
            f"{dataset.bathy_count:,} bathy photons across {dataset.file_count} files / {dataset.beam_count} beams"
        )
        for warning in dataset.warnings[:10]:
            print(f"  warning: {warning}")
        if len(dataset.warnings) > 10:
            print(
                f"  warning: {len(dataset.warnings) - 10} additional warnings omitted"
            )
    return 0


def _beams_to_read(path: Path, h5: h5py.File) -> list[str]:
    manual_beam = manual_beam_from_filename(path)
    if manual_beam is not None:
        return [manual_beam]
    return [beam for beam in BEAM_NAMES if beam in h5]


def _read_1d_dataset(group: h5py.Group, name: str) -> np.ndarray:
    dataset = group[name]
    if len(dataset.shape) != 1:
        raise ValueError(f"{name} must be one-dimensional")
    return np.asarray(dataset[:], dtype=float)


def _concat_or_empty(parts: list[np.ndarray]) -> np.ndarray:
    if not parts:
        return np.asarray([], dtype=float)
    return np.concatenate(parts).astype(float, copy=False)


def _sample_value(sample: object, nodata: float | int | None) -> float | None:
    masked = np.ma.asarray(sample)
    if masked.size == 0 or bool(np.ma.is_masked(masked[0])):
        return None
    value = float(masked[0])
    if not math.isfinite(value):
        return None
    if nodata is not None and math.isclose(
        value, float(nodata), rel_tol=0.0, abs_tol=1e-12
    ):
        return None
    return value


def _shared_axis_limits(
    datasets: Sequence[ComparisonDataset],
) -> tuple[float, float]:
    values = [
        array
        for dataset in datasets
        for array in (dataset.dem_elevation, dataset.photon_elevation)
        if array.size
    ]
    if not values:
        return (-1.0, 1.0)
    combined = np.concatenate(values)
    finite = combined[np.isfinite(combined)]
    if finite.size == 0:
        return (-1.0, 1.0)
    low = float(np.nanpercentile(finite, 0.5))
    high = float(np.nanpercentile(finite, 99.5))
    if (
        not math.isfinite(low)
        or not math.isfinite(high)
        or math.isclose(low, high)
    ):
        low = float(np.nanmin(finite))
        high = float(np.nanmax(finite))
    if math.isclose(low, high):
        low -= 1.0
        high += 1.0
    padding = max((high - low) * 0.05, 0.5)
    return (low - padding, high + padding)


def _draw_scatter_panel(
    ax: object,
    dataset: ComparisonDataset,
    *,
    limits: tuple[float, float],
    max_points: int,
    seed: int,
) -> None:
    low, high = limits
    if dataset.valid_count:
        indices = _plot_indices(
            dataset.valid_count, max_points=max_points, seed=seed
        )
        hexbin = ax.hexbin(
            dataset.dem_elevation[indices],
            dataset.photon_elevation[indices],
            gridsize=52,
            extent=(low, high, low, high),
            mincnt=1,
            bins="log",
            cmap="viridis",
            linewidths=0.0,
        )
        colorbar = ax.figure.colorbar(hexbin, ax=ax, pad=0.02, fraction=0.048)
        colorbar.set_label("Photons per hexbin", fontsize=8.5)
        colorbar.ax.tick_params(labelsize=7.5)
    else:
        ax.text(
            0.5,
            0.5,
            "No valid bathy photons",
            ha="center",
            va="center",
            transform=ax.transAxes,
        )
    ax.plot(
        [low, high],
        [low, high],
        color="black",
        linewidth=1.0,
        alpha=0.75,
        label="1:1",
    )
    ax.set_xlim(low, high)
    ax.set_ylim(low, high)
    ax.set_box_aspect(1)
    ax.grid(True, color="#d8d8d8", linewidth=0.6, alpha=0.8)
    ax.set_title(_panel_title(dataset), fontsize=10)
    ax.text(
        0.03,
        0.97,
        _stats_text(dataset),
        ha="left",
        va="top",
        transform=ax.transAxes,
        fontsize=8.5,
        bbox={
            "boxstyle": "round,pad=0.25",
            "facecolor": "white",
            "edgecolor": "#cfcfcf",
            "alpha": 0.82,
        },
    )
    ax.set_xlabel("Reference Elevation (m)")
    ax.set_ylabel("ICESat-2 Elevation (m)")


def _format_depth_summary_axes(
    count_ax: object, rmse_ax: object, *, title: str | None
) -> None:
    if title:
        count_ax.set_title(title, fontsize=11)
    count_ax.set_xlabel("Reference Elevation (m)")
    count_ax.set_ylabel("Photon count", color=COUNT_AXIS_COLOR)
    count_ax.set_yscale("log")
    rmse_ax.set_ylabel("RMSE (m)", color=RMSE_AXIS_COLOR)
    count_ax.tick_params(axis="y", colors=COUNT_AXIS_COLOR)
    rmse_ax.tick_params(axis="y", colors=RMSE_AXIS_COLOR)
    count_ax.spines["left"].set_color(COUNT_AXIS_COLOR)
    rmse_ax.spines["right"].set_color(RMSE_AXIS_COLOR)
    count_ax.grid(True, color="#d8d8d8", linewidth=0.6, alpha=0.8)


def _depth_summary_line_style(label: str, metric: str) -> dict[str, object]:
    if metric == "count":
        color = COUNT_AXIS_COLOR
        linewidth = 1.65
    elif metric == "rmse":
        color = RMSE_AXIS_COLOR
        linewidth = 1.5
    else:
        raise ValueError(f"Unknown depth-summary metric: {metric}")
    return {
        "color": color,
        "linestyle": "--" if label == "Manual" else "-",
        "linewidth": linewidth,
    }


def _plot_indices(count: int, *, max_points: int, seed: int) -> np.ndarray:
    if max_points <= 0 or count <= max_points:
        return np.arange(count)
    rng = np.random.default_rng(seed)
    return np.sort(rng.choice(count, size=max_points, replace=False))


def _panel_title(dataset: ComparisonDataset) -> str:
    return dataset.label


def _stats_text(dataset: ComparisonDataset) -> str:
    if dataset.valid_count == 0:
        return "n=0 photons\nRMSE=nan m\nMAE=nan m\nBias=nan m"
    residuals = dataset.residuals
    rmse = float(np.sqrt(np.nanmean(residuals**2)))
    mae = float(np.nanmean(np.abs(residuals)))
    bias = float(np.nanmean(residuals))
    return f"n={dataset.valid_count:,} photons\nRMSE={rmse:.2f} m\nMAE={mae:.2f} m\nBias={bias:+.2f} m"


def _figure_title(location: str, lidar_date_range: str) -> str:
    return (
        f"{location} - ICESat-2 Bathymetry QA/QC\n"
        f"ICESat-2 (2018-2025) and Lidar DEM ({lidar_date_range})"
    )


def infer_plot_metadata(*paths: str | Path) -> tuple[str, str]:
    haystack = " ".join(str(path).lower() for path in paths)
    for key, metadata in LOCATION_DATE_RANGES.items():
        if key in haystack:
            return metadata
    return "Location", "Date to go here"


def _shared_reference_bin_edges(
    datasets: Sequence[ComparisonDataset],
    *,
    bin_width: float = DEFAULT_RMSE_BIN_WIDTH_M,
) -> np.ndarray:
    values = [
        dataset.dem_elevation[np.isfinite(dataset.dem_elevation)]
        for dataset in datasets
    ]
    populated = [value for value in values if value.size]
    if not populated:
        return np.asarray([0.0, bin_width], dtype=float)
    combined = np.concatenate(populated)
    low = float(np.nanpercentile(combined, 0.5))
    high = float(np.nanpercentile(combined, 99.5))
    if (
        not math.isfinite(low)
        or not math.isfinite(high)
        or math.isclose(low, high)
    ):
        low = float(np.nanmin(combined))
        high = float(np.nanmax(combined))
    start = math.floor(low / bin_width) * bin_width
    stop = math.ceil(high / bin_width) * bin_width
    if math.isclose(start, stop):
        stop = start + bin_width
    return np.arange(start, stop + bin_width * 0.5, bin_width, dtype=float)


def binned_rmse_by_reference(
    dem_elevation: np.ndarray,
    photon_elevation: np.ndarray,
    *,
    bin_width: float = DEFAULT_RMSE_BIN_WIDTH_M,
    edges: np.ndarray | None = None,
    include_empty: bool = False,
) -> tuple[np.ndarray, np.ndarray]:
    if bin_width <= 0:
        raise ValueError("bin_width must be positive")
    if dem_elevation.shape != photon_elevation.shape:
        raise ValueError(
            "dem_elevation and photon_elevation must have matching shapes"
        )
    finite = np.isfinite(dem_elevation) & np.isfinite(photon_elevation)
    if not np.any(finite):
        return np.asarray([], dtype=float), np.asarray([], dtype=float)

    reference = dem_elevation[finite]
    residuals = photon_elevation[finite] - reference
    if edges is None:
        start = math.floor(float(np.nanmin(reference)) / bin_width) * bin_width
        stop = math.ceil(float(np.nanmax(reference)) / bin_width) * bin_width
        if math.isclose(start, stop):
            stop = start + bin_width
        edges = np.arange(start, stop + bin_width * 0.5, bin_width, dtype=float)
    squared_error_sum, _ = np.histogram(
        reference, bins=edges, weights=residuals**2
    )
    counts, _ = np.histogram(reference, bins=edges)
    populated = counts > 0
    centers = (edges[:-1] + edges[1:]) / 2.0
    rmse = np.full(centers.shape, np.nan, dtype=float)
    rmse[populated] = np.sqrt(squared_error_sum[populated] / counts[populated])
    if include_empty:
        return centers, rmse
    return centers[populated], rmse[populated]


def binned_photon_counts_by_reference(
    dem_elevation: np.ndarray,
    *,
    bin_width: float = DEFAULT_RMSE_BIN_WIDTH_M,
    edges: np.ndarray | None = None,
    include_empty: bool = False,
) -> tuple[np.ndarray, np.ndarray]:
    if bin_width <= 0:
        raise ValueError("bin_width must be positive")
    finite = dem_elevation[np.isfinite(dem_elevation)]
    if finite.size == 0:
        return np.asarray([], dtype=float), np.asarray([], dtype=np.int64)
    if edges is None:
        start = math.floor(float(np.nanmin(finite)) / bin_width) * bin_width
        stop = math.ceil(float(np.nanmax(finite)) / bin_width) * bin_width
        if math.isclose(start, stop):
            stop = start + bin_width
        edges = np.arange(start, stop + bin_width * 0.5, bin_width, dtype=float)
    counts, _ = np.histogram(finite, bins=edges)
    centers = (edges[:-1] + edges[1:]) / 2.0
    if include_empty:
        return centers, counts
    populated = counts > 0
    return centers[populated], counts[populated]


if __name__ == "__main__":
    raise SystemExit(main())
