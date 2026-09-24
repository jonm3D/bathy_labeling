from __future__ import annotations

import json
from pathlib import Path

import geopandas as gpd
import pandas as pd
import pytest
from shapely.geometry import Point, box

from bathy_labeler.backend.review import SlideRuleReviewSession


def write_review_inputs(tmp_path: Path) -> Path:
    parquet_path = tmp_path / "site.parquet"
    aoi_path = tmp_path / "site.gpkg"
    points = [
        Point(-0.30, 0),
        Point(0.00, 0),
        Point(0.05, 0),
        Point(0.30, 0),
        Point(0.40, 0),
        Point(0.50, 0),
    ]
    frame = gpd.GeoDataFrame(
        {
            "x_atc": [0, 1000, 2000, 3000, 4001, 1000],
            "ortho_h": [1.0, 1.1, -2.0, -2.1, 0.8, 0.0],
            "surface_h": [1.0] * 6,
            "night_flag": [0, 0, 0, 0, 0, 1],
            "class_ph": [0, 41, 40, 0, 0, 0],
            "rgt": [123, 123, 123, 123, 123, 999],
            "cycle": [7, 7, 7, 7, 7, 7],
            "spot": [1, 1, 1, 1, 1, 2],
        },
        geometry=points,
        crs="EPSG:4326",
    )
    frame.index = pd.DatetimeIndex(
        pd.date_range("2024-01-02T00:00:00", periods=6, freq="1ms"),
        name="time_ns",
    )
    frame.to_parquet(parquet_path)
    gpd.GeoDataFrame(
        {"name": ["AOI"]},
        geometry=[box(-0.1, -0.1, 0.1, 0.1)],
        crs="EPSG:4326",
    ).to_file(aoi_path)
    config = {
        "context_margin_m": 1000,
        "output_dir": "classified",
        "sites": [
            {
                "id": "test_site",
                "name": "Test Site",
                "parquet": parquet_path.name,
                "aoi": aoi_path.name,
                "site_marker": {
                    "label": "Test wreck",
                    "longitude": -0.02,
                    "latitude": 0.01,
                },
            }
        ],
    }
    config_path = tmp_path / "review.json"
    config_path.write_text(json.dumps(config))
    return config_path


def write_atl03_review_inputs(tmp_path: Path) -> Path:
    parquet_path = tmp_path / "atl03.parquet"
    aoi_path = tmp_path / "atl03_aoi.gpkg"
    frame = gpd.GeoDataFrame(
        {
            "x_atc": [0, 1000, 2000, 3000],
            "height": [12.04, -27.76, -37.36, -39.96],
            "geoid": [-29.0] * 4,
            "geoid_free2mean": [0.04] * 4,
            "ortho_h": [41.0, 1.2, -8.4, -11.0],
            "rgt": [469] * 4,
            "cycle": [27] * 4,
            "spot": [6] * 4,
            "ph_index": [100, 101, 102, 103],
            "atl03_cnf": [0, 1, 0, -2],
            "solar_elevation": [58.0] * 4,
        },
        geometry=[
            Point(-0.30, 0),
            Point(0.00, 0),
            Point(0.05, 0),
            Point(0.30, 0),
        ],
        crs="EPSG:4326",
    )
    frame.index = pd.DatetimeIndex(
        pd.date_range("2025-04-16T15:40:31", periods=4, freq="100us"),
        name="time_ns",
    )
    frame.to_parquet(parquet_path)
    gpd.GeoDataFrame(
        {"name": ["ATL03 AOI"]},
        geometry=[box(-0.1, -0.1, 0.1, 0.1)],
        crs="EPSG:4326",
    ).to_file(aoi_path)
    config_path = tmp_path / "atl03_review.json"
    config_path.write_text(
        json.dumps(
            {
                "context_margin_m": 1000,
                "output_dir": "classified",
                "sites": [
                    {
                        "id": "army_tanks",
                        "name": "Army Tanks",
                        "product": "atl03",
                        "parquet": parquet_path.name,
                        "aoi": aoi_path.name,
                    }
                ],
            }
        )
    )
    return config_path


def test_review_groups_sliderule_rows_and_applies_along_track_context(
    tmp_path: Path,
) -> None:
    session = SlideRuleReviewSession(write_review_inputs(tmp_path))

    sources = session.sources_payload()["sources"]
    assert len(sources) == 1
    source = sources[0]
    assert source["beams"] == ["rgt_0123_cycle_007_spot_1"]
    assert source["aoi_photon_count"] == 2
    assert source["track_closest_distances_m"][source["beams"][0]] == pytest.approx(
        2485.86, abs=1.0
    )

    payload = session.read_track("test_site", source["beams"][0])
    assert payload["assigned"]["source_row"] == [1, 2]
    assert payload["context"]["source_row"] == [0, 1, 2, 3]
    assert payload["beam"]["rgt"] == 123
    assert payload["beam"]["cycle"] == 7
    assert payload["beam"]["spot"] == 1
    assert payload["labels"][0]["label"] == "surface"
    assert payload["labels"][1]["label"] == "bathy"
    assert payload["aoi_geometry"]["type"] == "Polygon"
    assert payload["site_marker"] == {
        "label": "Test wreck",
        "longitude": -0.02,
        "latitude": 0.01,
    }


def test_review_priorities_and_notes_are_exposed_in_track_order(
    tmp_path: Path,
) -> None:
    config_path = write_review_inputs(tmp_path)
    frame = gpd.read_parquet(tmp_path / "site.parquet")
    frame.loc[frame["rgt"] == 999, "geometry"] = Point(0.02, 0)
    frame.to_parquet(tmp_path / "site.parquet")
    config = json.loads(config_path.read_text())
    site = config["sites"][0]
    priority = "rgt_0999_cycle_007_spot_2"
    site["review_note"] = "Site-level review note."
    site["priority_tracks"] = [priority]
    site["track_notes"] = {priority: "Inspect this one first."}
    config_path.write_text(json.dumps(config))

    source = SlideRuleReviewSession(config_path).sources_payload()["sources"][0]

    assert source["beams"][0] == priority
    assert source["review_note"] == "Site-level review note."
    assert source["priority_tracks"] == [priority]
    assert source["track_notes"] == {priority: "Inspect this one first."}


def test_review_annotations_save_to_geopackage_and_reload(
    tmp_path: Path,
) -> None:
    session = SlideRuleReviewSession(write_review_inputs(tmp_path))
    track = "rgt_0123_cycle_007_spot_1"
    labels = session.read_track("test_site", track)["labels"]
    labels[0] = {
        "source_row": 1,
        "label": "bathy",
        "label_source": "manual",
    }

    saved = session.save_track("test_site", track, labels)

    output_path = Path(saved["output_path"])
    assert output_path.exists()
    assert output_path.name == "20240102_rgt0123_cycle007_spot1.gpkg"
    assert set(gpd.list_layers(output_path)["name"]) == {
        "photons",
        "bathymetry",
    }
    photons = gpd.read_file(output_path, layer="photons")
    assert photons["photon_id"].tolist() == [
        "20240102_0123_007_1_00000001",
        "20240102_0123_007_1_00000002",
    ]
    assert photons["class_manual"].tolist() == [40, 40]
    assert photons["atl24_class"].tolist() == [41, 40]
    assert "atl24_night_flag" in photons
    assert len(gpd.read_file(output_path, layer="bathymetry")) == 2
    assert saved["source_status"]["annotated_track_count"] == 1
    reloaded = session.read_track("test_site", track)
    assert reloaded["label_origin"] == "manual_output"
    assert reloaded["labels"][0]["label"] == "bathy"
    assert reloaded["labels"][0]["label_source"] == "manual"


def test_atl03_review_uses_raw_height_and_writes_standard_geopackage(
    tmp_path: Path,
) -> None:
    session = SlideRuleReviewSession(write_atl03_review_inputs(tmp_path))
    assert session.manifest()["source_product"] == "atl03"
    source = session.sources_payload()["sources"][0]
    assert source["product"] == "atl03"
    assert source["source_label"] == "SlideRule ATL03"
    track = "rgt_0469_cycle_027_spot_6"

    payload = session.read_track("army_tanks", track)

    assert payload["label_origin"] == "raw_unclassified"
    assert payload["assigned"]["source_row"] == [1, 2]
    assert payload["assigned"]["ortho_h_m"] == pytest.approx([1.2, -8.4])
    assert payload["assigned"]["atl24_class_ph"] == [None, None]
    assert {row["label"] for row in payload["labels"]} == {"no_label"}

    labels = payload["labels"]
    labels[1] = {
        "source_row": 2,
        "label": "bathy",
        "label_source": "manual",
    }
    saved = session.save_track("army_tanks", track, labels)
    photons = gpd.read_file(saved["output_path"], layer="photons")

    assert photons["photon_id"].tolist() == [
        "20250416_0469_027_6_00000001",
        "20250416_0469_027_6_00000002",
    ]
    assert photons["elevation_m"].tolist() == pytest.approx([1.2, -8.4])
    assert photons["atl24_class"].isna().all()
    assert photons["atl03_height"].tolist() == pytest.approx(
        [-27.76, -37.36]
    )
    assert photons["atl03_geoid"].tolist() == [-29.0, -29.0]
    assert photons["atl03_geoid_free2mean"].tolist() == [0.04, 0.04]
    assert "atl03_cnf" in photons
    assert "atl03_atl03_cnf" not in photons
    assert len(gpd.read_file(saved["output_path"], layer="bathymetry")) == 1


def test_atl03_review_rejects_input_without_geoid_corrections(
    tmp_path: Path,
) -> None:
    config_path = write_atl03_review_inputs(tmp_path)
    parquet_path = tmp_path / "atl03.parquet"
    frame = gpd.read_parquet(parquet_path).drop(
        columns=["geoid", "geoid_free2mean", "ortho_h"]
    )
    frame.to_parquet(parquet_path)

    with pytest.raises(ValueError, match="geoid, geoid_free2mean"):
        SlideRuleReviewSession(config_path)


def test_review_rejects_invalid_site_marker(tmp_path: Path) -> None:
    config_path = write_review_inputs(tmp_path)
    config = json.loads(config_path.read_text())
    config["sites"][0]["site_marker"]["latitude"] = 120
    config_path.write_text(json.dumps(config))

    with pytest.raises(ValueError, match="latitude must be between -90 and 90"):
        SlideRuleReviewSession(config_path)


def test_review_rejects_labels_without_an_output_class(tmp_path: Path) -> None:
    session = SlideRuleReviewSession(write_review_inputs(tmp_path))
    track = session.sources_payload()["sources"][0]["beams"][0]
    payload = session.read_track("test_site", track)
    labels = [
        {"source_row": row, "label": "noise", "label_source": "manual"}
        for row in payload["assigned"]["source_row"]
    ]

    with pytest.raises(ValueError, match="Invalid label: noise"):
        session.save_track("test_site", track, labels)
