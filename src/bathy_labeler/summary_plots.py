from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import cmcrameri.cm as cmc
import contextily as cx
import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import rasterio
from matplotlib.colors import TwoSlopeNorm
from matplotlib.lines import Line2D
from matplotlib.patches import Patch
from matplotlib.ticker import FuncFormatter, MaxNLocator
from matplotlib_scalebar.scalebar import ScaleBar
from pyproj import CRS, Transformer
from rasterio.enums import Resampling

WGS84 = CRS.from_epsg(4326)
TILE_HEADERS = {
    "User-Agent": "bathy-labeler/0.1 (local scientific visualization)",
    "Referer": "http://localhost/",
}


@dataclass(frozen=True)
class SummaryPlotResult:
    map_path: Path
    histogram_path: Path
    track_count: int
    photon_count: int


@dataclass(frozen=True)
class BathymetryCollection:
    photons: gpd.GeoDataFrame
    track_count: int
    saved_track_count: int

    @property
    def photon_count(self) -> int:
        return len(self.photons)


def collect_manual_bathymetry(
    classified_dir: str | Path,
) -> BathymetryCollection:
    root = Path(classified_dir).expanduser().resolve()
    if not root.is_dir():
        raise NotADirectoryError(f"Classified track folder does not exist: {root}")
    paths = sorted(root.glob("*.gpkg"))
    parts: list[gpd.GeoDataFrame] = []
    track_count = 0
    for path in paths:
        frame = gpd.read_file(path, layer="bathymetry")
        missing = sorted(
            {"elevation_m", "class_manual", "geometry"} - set(frame.columns)
        )
        if missing:
            raise ValueError(
                f"Missing classified fields in {path.name}: {', '.join(missing)}"
            )
        if frame.empty:
            continue
        if frame.crs is None:
            raise ValueError(f"Bathymetry layer has no CRS: {path}")
        frame = frame.loc[frame["class_manual"] == 40].copy()
        if frame.empty:
            continue
        frame["source_track"] = path.stem
        parts.append(frame.to_crs(WGS84))
        track_count += 1
    if not parts:
        raise ValueError(f"No manually labeled bathymetry found in {root}")
    photons = gpd.GeoDataFrame(
        pd.concat(parts, ignore_index=True),
        geometry="geometry",
        crs=WGS84,
    )
    photons["elevation_m"] = pd.to_numeric(photons["elevation_m"], errors="coerce")
    photons = photons.loc[
        np.isfinite(photons["elevation_m"])
        & np.isfinite(photons.geometry.x)
        & np.isfinite(photons.geometry.y)
    ].copy()
    return BathymetryCollection(
        photons=photons,
        track_count=track_count,
        saved_track_count=len(paths),
    )


def create_site_summary_plots(
    *,
    site_name: str,
    site_slug: str,
    aoi_path: str | Path,
    classified_dir: str | Path,
    output_dir: str | Path,
    dem_path: str | Path | None = None,
    dem_legend_label: str | None = None,
    map_extent_factor: float = 1.1,
    add_osm: bool = True,
    dpi: int = 300,
) -> SummaryPlotResult:
    aoi_file = Path(aoi_path).expanduser().resolve()
    if not aoi_file.exists():
        raise FileNotFoundError(f"AOI does not exist: {aoi_file}")
    aoi = gpd.read_file(aoi_file)
    if aoi.empty or aoi.crs is None:
        raise ValueError(f"AOI must contain projected geometry and a CRS: {aoi_file}")
    bathymetry = collect_manual_bathymetry(classified_dir)

    dem_file = None if dem_path is None else Path(dem_path).expanduser().resolve()
    dem = None
    dem_extent = None
    if dem_file is not None:
        if not dem_file.exists():
            raise FileNotFoundError(f"Reference DEM does not exist: {dem_file}")
        dem, dem_extent, plot_crs = _read_dem_for_plot(dem_file)
    else:
        plot_crs = _local_utm_crs(aoi)

    output_root = Path(output_dir).expanduser().resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    map_path = output_root / f"{site_slug}_bathymetry_map.png"
    histogram_path = output_root / f"{site_slug}_bathymetry_histogram.png"

    aoi_projected = aoi.to_crs(plot_crs)
    bathy_projected = bathymetry.photons.to_crs(plot_crs)
    norm = _elevation_norm(bathymetry.photons["elevation_m"].to_numpy(dtype=float), dem)
    _plot_map(
        site_name=site_name,
        aoi=aoi_projected,
        bathymetry=bathy_projected,
        norm=norm,
        output_path=map_path,
        plot_crs=plot_crs,
        track_count=bathymetry.track_count,
        photon_count=bathymetry.photon_count,
        dem=dem,
        dem_extent=dem_extent,
        dem_legend_label=dem_legend_label,
        map_extent_factor=map_extent_factor,
        add_osm=add_osm,
        dpi=dpi,
    )
    _plot_vertical_histogram(
        site_name=site_name,
        elevations=bathymetry.photons["elevation_m"].to_numpy(dtype=float),
        norm=norm,
        output_path=histogram_path,
        track_count=bathymetry.track_count,
        photon_count=bathymetry.photon_count,
        dpi=dpi,
    )
    return SummaryPlotResult(
        map_path=map_path,
        histogram_path=histogram_path,
        track_count=bathymetry.track_count,
        photon_count=bathymetry.photon_count,
    )


def _plot_map(
    *,
    site_name: str,
    aoi: gpd.GeoDataFrame,
    bathymetry: gpd.GeoDataFrame,
    norm: TwoSlopeNorm,
    output_path: Path,
    plot_crs: CRS,
    track_count: int,
    photon_count: int,
    dem: np.ma.MaskedArray | None,
    dem_extent: tuple[float, float, float, float] | None,
    dem_legend_label: str | None,
    map_extent_factor: float,
    add_osm: bool,
    dpi: int,
) -> None:
    if map_extent_factor < 1.0:
        raise ValueError("map_extent_factor must be at least 1.0")
    fig, ax = plt.subplots(figsize=(8, 8), layout="constrained")
    bounds = aoi.total_bounds
    pad_fraction = (map_extent_factor - 1.0) / 2.0
    x_pad = max((bounds[2] - bounds[0]) * pad_fraction, 50.0)
    y_pad = max((bounds[3] - bounds[1]) * pad_fraction, 50.0)
    ax.set_xlim(bounds[0] - x_pad, bounds[2] + x_pad)
    ax.set_ylim(bounds[1] - y_pad, bounds[3] + y_pad)

    if add_osm:
        provider = cx.providers.CartoDB.Positron
        cx.add_basemap(
            ax,
            source=provider,
            crs=plot_crs,
            headers=TILE_HEADERS,
            attribution=provider.attribution,
            attribution_size=6,
            reset_extent=False,
            zorder=0,
        )

    cmap = cmc.bukavu.with_extremes(bad=(0, 0, 0, 0))
    if dem is not None and dem_extent is not None:
        ax.imshow(
            dem,
            extent=dem_extent,
            origin="upper",
            cmap=cmap,
            norm=norm,
            alpha=0.60,
            interpolation="bilinear",
            zorder=1,
        )

    ordered = bathymetry.sort_values("elevation_m", ascending=True)
    ax.scatter(
        ordered.geometry.x,
        ordered.geometry.y,
        c=ordered["elevation_m"],
        cmap=cmap,
        norm=norm,
        s=8,
        alpha=0.92,
        edgecolors="#171717",
        linewidths=0.15,
        zorder=3,
    )
    aoi.boundary.plot(ax=ax, color="#d7191c", linewidth=1.5, zorder=4)

    mappable = plt.cm.ScalarMappable(norm=norm, cmap=cmap)
    mappable.set_array([])
    colorbar = fig.colorbar(mappable, ax=ax, shrink=0.78, pad=0.02)
    colorbar.set_label("Elevation (m, EGM08)")

    legend_items = []
    if dem is not None:
        legend_items.append(
            Patch(
                facecolor=cmap(norm(-0.5 * norm.vmax)),
                edgecolor="none",
                alpha=0.60,
                label=dem_legend_label or "Reference DEM",
            )
        )
    legend_items.append(
        Line2D(
            [0],
            [0],
            marker="o",
            linestyle="none",
            markerfacecolor=cmap(norm(-0.5 * norm.vmax)),
            markeredgecolor="#171717",
            markeredgewidth=0.3,
            markersize=5,
            label="ICESat-2 bathymetry",
        )
    )
    ax.legend(handles=legend_items, loc="upper left", fontsize=8, framealpha=0.9)
    ax.text(
        0.98,
        0.98,
        f"{track_count:,} tracks with bathy\n{photon_count:,} bathy photons",
        transform=ax.transAxes,
        ha="right",
        va="top",
        fontsize=8,
        bbox={"facecolor": "white", "edgecolor": "none", "alpha": 0.85, "pad": 3},
        zorder=5,
    )
    ax.add_artist(
        ScaleBar(
            1,
            units="m",
            dimension="si-length",
            location="lower right",
            length_fraction=0.20,
            box_alpha=0.85,
            font_properties={"size": 7},
            rotation="horizontal-only",
        )
    )
    _format_geographic_axes(ax, plot_crs)
    ax.set_title(site_name)
    ax.set_xlabel("Longitude")
    ax.set_ylabel("Latitude")
    ax.set_aspect("equal")
    fig.savefig(output_path, dpi=dpi, facecolor="white")
    plt.close(fig)


def _plot_vertical_histogram(
    *,
    site_name: str,
    elevations: np.ndarray,
    norm: TwoSlopeNorm,
    output_path: Path,
    track_count: int,
    photon_count: int,
    dpi: int,
) -> None:
    finite = elevations[np.isfinite(elevations)]
    lower = float(np.floor(finite.min()))
    edges = np.linspace(lower, 0.0, 31)
    counts, edges = np.histogram(finite, bins=edges)
    centers = (edges[:-1] + edges[1:]) / 2
    heights = np.diff(edges)

    fig, ax = plt.subplots(figsize=(4, 4), layout="constrained")
    ax.barh(
        centers,
        counts,
        height=heights * 0.92,
        color=cmc.bukavu(norm(centers)),
        edgecolor="none",
    )
    ax.axhline(0, color="#6b6b6b", linewidth=0.7)
    ax.set_ylim(lower, 0.0)
    ax.set_title(f"ICESat-2 depth distribution\n{site_name}")
    ax.set_xlabel("N points")
    ax.set_ylabel("Elevation (m, EGM08)")
    ax.xaxis.set_major_locator(MaxNLocator(nbins=5, integer=True))
    ax.grid(axis="x", color="#d4d4d4", linewidth=0.5)
    ax.set_axisbelow(True)
    span = -lower
    bottom_count = np.count_nonzero(finite <= lower + span / 3)
    top_count = np.count_nonzero(finite >= lower + 2 * span / 3)
    annotation_y = 0.96 if top_count <= bottom_count else 0.04
    annotation_va = "top" if top_count <= bottom_count else "bottom"
    ax.text(
        0.98,
        annotation_y,
        f"{track_count:,} tracks, {photon_count:,} points",
        transform=ax.transAxes,
        ha="right",
        va=annotation_va,
        fontsize=8,
    )
    fig.savefig(output_path, dpi=dpi, facecolor="white")
    plt.close(fig)


def _read_dem_for_plot(
    path: Path,
    max_dimension: int = 1600,
) -> tuple[np.ma.MaskedArray, tuple[float, float, float, float], CRS]:
    with rasterio.open(path) as dataset:
        if dataset.crs is None:
            raise ValueError(f"Reference DEM has no CRS: {path}")
        vertical_datum = dataset.tags().get("vertical_datum", "")
        if vertical_datum.casefold() not in {"egm08", "egm2008"}:
            raise ValueError(
                f"Reference DEM must be transformed to EGM2008 before plotting: {path}"
            )
        scale = max(dataset.width, dataset.height) / max_dimension
        if scale > 1:
            out_height = max(1, round(dataset.height / scale))
            out_width = max(1, round(dataset.width / scale))
        else:
            out_height = dataset.height
            out_width = dataset.width
        data = dataset.read(
            1,
            out_shape=(out_height, out_width),
            masked=True,
            resampling=Resampling.bilinear,
        )
        bounds = dataset.bounds
        extent = (bounds.left, bounds.right, bounds.bottom, bounds.top)
        plot_crs = _horizontal_crs(CRS.from_user_input(dataset.crs))
    return np.ma.masked_invalid(data), extent, plot_crs


def _elevation_norm(
    bathy_elevation: np.ndarray,
    dem: np.ma.MaskedArray | None,
) -> TwoSlopeNorm:
    values = [np.asarray(bathy_elevation, dtype=float)]
    if dem is not None:
        values.append(np.asarray(dem.compressed(), dtype=float))
    finite = np.concatenate([value[np.isfinite(value)] for value in values])
    if finite.size == 0:
        raise ValueError("No finite elevation values are available")
    limit = float(np.max(np.abs(finite)))
    if limit == 0:
        limit = 1.0
    return TwoSlopeNorm(vmin=-limit, vcenter=0.0, vmax=limit)


def _local_utm_crs(aoi: gpd.GeoDataFrame) -> CRS:
    estimated = aoi.to_crs(WGS84).estimate_utm_crs()
    if estimated is None:
        raise ValueError("Could not estimate a projected CRS for the AOI")
    return CRS.from_user_input(estimated)


def _horizontal_crs(crs: CRS) -> CRS:
    if not crs.is_compound:
        return crs
    for sub_crs in crs.sub_crs_list:
        if sub_crs.is_projected:
            return sub_crs
    raise ValueError(f"Compound DEM CRS has no projected horizontal component: {crs}")


def _format_geographic_axes(ax: plt.Axes, plot_crs: CRS) -> None:
    transformer = Transformer.from_crs(plot_crs, WGS84, always_xy=True)
    center_x = float(np.mean(ax.get_xlim()))
    center_y = float(np.mean(ax.get_ylim()))

    def longitude(value: float, _: int) -> str:
        lon, _lat = transformer.transform(value, center_y)
        return f"{lon:.3f}°"

    def latitude(value: float, _: int) -> str:
        _lon, lat = transformer.transform(center_x, value)
        return f"{lat:.3f}°"

    ax.xaxis.set_major_locator(MaxNLocator(nbins=5))
    ax.yaxis.set_major_locator(MaxNLocator(nbins=5))
    ax.xaxis.set_major_formatter(FuncFormatter(longitude))
    ax.yaxis.set_major_formatter(FuncFormatter(latitude))
