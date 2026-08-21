from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import h5py
import numpy as np
import pytest

pytest.importorskip("rasterio")
pytest.importorskip("pyproj")

import rasterio
from pyproj import Transformer
from rasterio.transform import from_origin


SCRIPT_PATH = (
    Path(__file__).resolve().parents[2]
    / "scripts"
    / "plot_bathy_dem_comparison.py"
)
SPEC = importlib.util.spec_from_file_location(
    "plot_bathy_dem_comparison", SCRIPT_PATH
)
assert SPEC is not None and SPEC.loader is not None
comparison = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = comparison
SPEC.loader.exec_module(comparison)


def write_atl24_like_file(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with h5py.File(path, "w") as h5:
        for beam in ("gt1l", "gt1r"):
            group = h5.create_group(beam)
            count = 150
            x_atc = np.arange(count, dtype=float)
            class_ph = np.zeros(count, dtype=np.int16)
            class_ph[20:80] = 40
            group.create_dataset("lon_ph", data=-144.8 + x_atc * 0.00001)
            group.create_dataset("lat_ph", data=13.4 + x_atc * 0.00001)
            group.create_dataset("x_atc", data=x_atc)
            group.create_dataset("ortho_h", data=np.linspace(2.0, -8.0, count))
            group.create_dataset("surface_h", data=np.full(count, 0.25))
            group.create_dataset(
                "index_ph", data=np.arange(count, dtype=np.int64)
            )
            group.create_dataset("class_ph", data=class_ph)
            group.create_dataset(
                "night_flag", data=np.zeros(count, dtype=np.int8)
            )


def test_original_h5_reads_all_valid_beams(tmp_path: Path) -> None:
    source_dir = tmp_path / "original"
    write_atl24_like_file(source_dir / "ATL24_sample.h5")

    photons = comparison.collect_bathy_photons(source_dir)

    assert photons.photon_count == 120
    assert photons.beam_count == 2
    assert photons.file_count == 1


def test_manual_h5_reads_only_beam_named_in_manual_filename(
    tmp_path: Path,
) -> None:
    source_dir = tmp_path / "relabeled"
    manual_path = source_dir / "ATL24_sample_gt1l_manual.h5"
    write_atl24_like_file(manual_path)
    with h5py.File(manual_path, "r+") as h5:
        h5["gt1r"]["class_ph"][:] = 40

    photons = comparison.collect_bathy_photons(source_dir)

    assert photons.photon_count == 60
    assert photons.beam_count == 1
    assert photons.file_count == 1
    assert photons.sources == ["ATL24_sample_gt1l_manual.h5/gt1l"]


def test_manual_h5_collection_ignores_archived_backups(tmp_path: Path) -> None:
    source_dir = tmp_path / "relabeled"
    current = source_dir / "ATL24_sample_gt1l_manual.h5"
    backup = (
        source_dir
        / ".bathy_labeler_backups"
        / "ATL24_sample_gt1l_manual"
        / "timestamp"
        / current.name
    )
    write_atl24_like_file(current)
    write_atl24_like_file(backup)
    with h5py.File(current, "r+") as h5:
        h5["gt1l"]["class_ph"][:] = 41

    photons = comparison.collect_bathy_photons(source_dir)

    assert photons.photon_count == 0
    assert photons.file_count == 1
    assert photons.sources == ["ATL24_sample_gt1l_manual.h5/gt1l"]


def test_dem_sampling_transforms_lonlat_to_dem_crs_and_drops_invalid_samples(
    tmp_path: Path,
) -> None:
    dem_path = tmp_path / "reference_dem.tif"
    data = np.asarray(
        [
            [0.0, 1.0, 2.0],
            [10.0, 11.0, 12.0],
            [20.0, 21.0, -9999.0],
        ],
        dtype=np.float32,
    )
    with rasterio.open(
        dem_path,
        "w",
        driver="GTiff",
        width=data.shape[1],
        height=data.shape[0],
        count=1,
        dtype=data.dtype,
        crs="EPSG:3857",
        transform=from_origin(-150.0, 150.0, 100.0, 100.0),
        nodata=-9999.0,
    ) as dataset:
        dataset.write(data, 1)

    transformer = Transformer.from_crs("EPSG:3857", "EPSG:4326", always_xy=True)
    lon, lat = transformer.transform(
        [0.0, 100.0, 100.0, 10_000.0], [0.0, 0.0, -100.0, 10_000.0]
    )
    photons = comparison.PhotonCollection(
        lon=np.asarray(lon, dtype=float),
        lat=np.asarray(lat, dtype=float),
        elevation=np.asarray([11.2, 12.4, 99.0, -3.0], dtype=float),
        file_count=1,
        beam_count=1,
        sources=["synthetic/gt1l"],
        warnings=[],
    )

    sampled = comparison.build_comparison_dataset(
        "Synthetic", photons, dem_path
    )

    assert sampled.dem_elevation.tolist() == [11.0, 12.0]
    assert sampled.photon_elevation.tolist() == [11.2, 12.4]
    assert sampled.valid_count == 2
    assert sampled.bathy_count == 4
    assert sampled.invalid_dem_count == 2


def test_panel_title_and_stats_use_clean_qa_labels() -> None:
    dataset = comparison.ComparisonDataset(
        label="Manual",
        dem_elevation=np.asarray([0.0, -1.0, -2.0], dtype=float),
        photon_elevation=np.asarray([0.2, -1.1, -2.3], dtype=float),
        bathy_count=12_742,
        valid_count=12_653,
        invalid_dem_count=89,
        file_count=22,
        beam_count=22,
        warnings=[],
    )

    title = comparison._panel_title(dataset)
    stats = comparison._stats_text(dataset)

    assert title == "Manual"
    assert stats.splitlines() == [
        "n=12,653 photons",
        "RMSE=0.22 m",
        "MAE=0.20 m",
        "Bias=-0.07 m",
    ]


def test_figure_title_includes_location_and_lidar_dates() -> None:
    assert comparison._figure_title("Duck", "2019-06-18 to 2019-06-25") == (
        "Duck - ICESat-2 Bathymetry QA/QC\n"
        "ICESat-2 (2018-2025) and Lidar DEM (2019-06-18 to 2019-06-25)"
    )


def test_binned_rmse_uses_one_meter_reference_bins() -> None:
    dem_elevation = np.asarray([-1.9, -1.6, -1.1, -0.9, -0.2], dtype=float)
    photon_elevation = dem_elevation + np.asarray(
        [1.0, -2.0, 2.0, 4.0, 10.0], dtype=float
    )

    centers, rmse = comparison.binned_rmse_by_reference(
        dem_elevation,
        photon_elevation,
    )

    assert centers.tolist() == [-1.5, -0.5]
    np.testing.assert_allclose(rmse, [np.sqrt(3.0), np.sqrt(58.0)])


def test_binned_photon_counts_use_one_meter_reference_bins() -> None:
    dem_elevation = np.asarray([-1.9, -1.6, -1.1, -0.9, -0.2], dtype=float)

    centers, counts = comparison.binned_photon_counts_by_reference(
        dem_elevation
    )

    assert centers.tolist() == [-1.5, -0.5]
    assert counts.tolist() == [3, 2]


def test_binned_depth_series_can_keep_empty_bins_for_line_plots() -> None:
    dem_elevation = np.asarray([-2.9, -2.6, -0.2], dtype=float)
    photon_elevation = dem_elevation + np.asarray(
        [1.0, -2.0, 10.0], dtype=float
    )

    centers, rmse = comparison.binned_rmse_by_reference(
        dem_elevation,
        photon_elevation,
        include_empty=True,
    )
    count_centers, counts = comparison.binned_photon_counts_by_reference(
        dem_elevation,
        include_empty=True,
    )

    assert centers.tolist() == [-2.5, -1.5, -0.5]
    assert count_centers.tolist() == centers.tolist()
    np.testing.assert_allclose(rmse[[0, 2]], [np.sqrt(2.5), 10.0])
    assert np.isnan(rmse[1])
    assert counts.tolist() == [2, 0, 1]


def test_shared_reference_bin_edges_ignore_extreme_depth_tails() -> None:
    core = np.linspace(-10.0, 0.0, 1_000)
    dataset = comparison.ComparisonDataset(
        label="ATL24",
        dem_elevation=np.concatenate(
            [np.asarray([-30.0]), core, np.asarray([7.0])]
        ),
        photon_elevation=np.concatenate(
            [np.asarray([-30.0]), core, np.asarray([7.0])]
        ),
        bathy_count=1_002,
        valid_count=1_002,
        invalid_dem_count=0,
        file_count=1,
        beam_count=1,
        warnings=[],
    )

    edges = comparison._shared_reference_bin_edges([dataset])

    assert edges[0] > -30.0
    assert edges[-1] < 7.0


def test_depth_summary_uses_log_scale_for_photon_count_axis() -> None:
    comparison._configure_plot_cache()
    plt = comparison._plotting_module()
    fig, count_ax = plt.subplots()
    rmse_ax = count_ax.twinx()

    try:
        comparison._format_depth_summary_axes(
            count_ax, rmse_ax, title="Depth summary"
        )

        assert count_ax.get_yscale() == "log"
        assert rmse_ax.get_yscale() == "linear"
    finally:
        plt.close(fig)


def test_depth_summary_line_style_maps_metric_to_color_and_source_to_line_style() -> (
    None
):
    assert comparison._depth_summary_line_style("ATL24", "count") == {
        "color": comparison.COUNT_AXIS_COLOR,
        "linestyle": "-",
        "linewidth": 1.65,
    }
    assert (
        comparison._depth_summary_line_style("Manual", "count")["linestyle"]
        == "--"
    )
    assert comparison._depth_summary_line_style("ATL24", "rmse") == {
        "color": comparison.RMSE_AXIS_COLOR,
        "linestyle": "-",
        "linewidth": 1.5,
    }
    assert (
        comparison._depth_summary_line_style("Manual", "rmse")["linestyle"]
        == "--"
    )


def test_plot_site_figures_writes_scatter_and_depth_summary_svgs(
    tmp_path: Path,
) -> None:
    atl24 = comparison.ComparisonDataset(
        label="ATL24",
        dem_elevation=np.asarray([-2.0, -1.5, -1.0], dtype=float),
        photon_elevation=np.asarray([-2.1, -1.4, -0.7], dtype=float),
        bathy_count=3,
        valid_count=3,
        invalid_dem_count=0,
        file_count=1,
        beam_count=1,
        warnings=[],
    )
    manual = comparison.ComparisonDataset(
        label="Manual",
        dem_elevation=np.asarray([-2.0, -1.5, -1.0], dtype=float),
        photon_elevation=np.asarray([-2.0, -1.45, -1.1], dtype=float),
        bathy_count=3,
        valid_count=3,
        invalid_dem_count=0,
        file_count=1,
        beam_count=1,
        warnings=[],
    )
    output_path = tmp_path / "comparison.svg"

    result = comparison.plot_site_figures(atl24, manual, output_path)

    assert result == {
        "scatter": output_path.resolve(),
        "depth_summary": (tmp_path / "comparison_Depth_Summary.svg").resolve(),
    }
    scatter_text = result["scatter"].read_text(encoding="utf-8")
    depth_summary_text = result["depth_summary"].read_text(encoding="utf-8")

    assert scatter_text.lstrip().startswith("<?xml")
    assert "<text" in scatter_text
    assert "ICESat-2 Bathymetry QA/QC" in scatter_text
    assert "Photons per hexbin" in scatter_text
    assert "Photon count" not in scatter_text
    assert ">RMSE (m)<" not in scatter_text
    assert "Photon count" in depth_summary_text
    assert "RMSE (m)" in depth_summary_text
    assert "Depth Bin Statistics" not in depth_summary_text
    assert (
        "Bathymetry Photon Count and RMSE by Reference Depth"
        not in depth_summary_text
    )
    assert "ATL24 photons" in depth_summary_text
    assert "Manual RMSE" in depth_summary_text


def test_cli_help_explains_both_figures_are_always_generated() -> None:
    help_text = " ".join(comparison.build_parser().format_help().split())

    assert (
        "Both the 1:1 comparison and depth-summary figures are always generated."
        in help_text
    )


def test_cli_main_writes_scatter_and_depth_summary_from_one_script_call(
    tmp_path: Path,
) -> None:
    original_dir = tmp_path / "original"
    relabeled_dir = tmp_path / "relabeled"
    dem_path = tmp_path / "reference_dem.tif"
    output_path = tmp_path / "comparison.svg"
    write_atl24_like_file(original_dir / "ATL24_sample.h5")
    write_atl24_like_file(relabeled_dir / "ATL24_sample_gt1l_manual.h5")
    dem = np.linspace(2.0, -12.0, 10_000, dtype=np.float32).reshape(100, 100)
    with rasterio.open(
        dem_path,
        "w",
        driver="GTiff",
        width=dem.shape[1],
        height=dem.shape[0],
        count=1,
        dtype=dem.dtype,
        crs="EPSG:4326",
        transform=from_origin(-145.0, 14.0, 0.01, 0.01),
    ) as dataset:
        dataset.write(dem, 1)

    exit_code = comparison.main(
        [
            str(original_dir),
            str(relabeled_dir),
            str(dem_path),
            str(output_path),
            "--location",
            "Synthetic",
            "--lidar-date-range",
            "2020-01-01 to 2020-01-02",
        ]
    )

    assert exit_code == 0
    assert output_path.exists()
    assert (tmp_path / "comparison_Depth_Summary.svg").exists()
