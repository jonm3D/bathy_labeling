from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import h5py
import pytest

from bathy_labeler.backend.reprocess import LABEL_TO_CLASS_PH, ReprocessSession
from tests.backend.test_hdf5_store import write_atl24_like_file

SOURCE_NAME = "ATL24_20240102000000_01230701_001_01.h5"
SOURCE_RELATIVE = f"Guam/{SOURCE_NAME}"


def make_session(tmp_path: Path) -> ReprocessSession:
    input_dir = tmp_path / "ATL24_inputs"
    output_dir = tmp_path / "ATL24_inputs_labeled"
    write_atl24_like_file(input_dir / SOURCE_RELATIVE)
    write_atl24_like_file(input_dir / "Guam" / "ATL24_sample_manual.h5")
    return ReprocessSession(input_dir=input_dir, output_dir=output_dir)


def test_configuring_session_scans_original_h5_files_only(
    tmp_path: Path,
) -> None:
    session = make_session(tmp_path)

    source = session.sources_payload()["sources"][0]

    assert source["source_relative_path"] == SOURCE_RELATIVE
    assert source["beams"] == ["gt1l", "gt1r"]
    assert source["status"] == "unclassified"
    assert source["beam_statuses"] == {
        "gt1l": "unclassified",
        "gt1r": "unclassified",
    }


def test_full_beam_payload_uses_original_atl24_classifications(
    tmp_path: Path,
) -> None:
    session = make_session(tmp_path)

    payload = session.read_beam(SOURCE_RELATIVE, "gt1l")

    assert payload["beam"]["photon_count"] == 150
    assert payload["photons"]["source_row"][:3] == [0, 1, 2]
    assert payload["labels"][0]["label"] == "surface"
    assert payload["labels"][20]["label"] == "bathy"
    assert payload["labels"][-1]["label"] == "no_label"
    assert payload["label_origin"] == "atl24_original"


def test_save_writes_qgis_ready_geopackage_and_reloads_labels(
    tmp_path: Path,
) -> None:
    session = make_session(tmp_path)
    payload = session.read_beam(SOURCE_RELATIVE, "gt1l")
    labels = [dict(row) for row in payload["labels"]]
    labels[0] = {
        "source_row": 0,
        "label": "bathy",
        "label_source": "manual",
    }

    result = session.save_source(SOURCE_RELATIVE, {"gt1l": labels})

    output_path = Path(result["outputs"][0]["output_path"])
    assert output_path.name == "20240102_rgt1234_cycle007_spot6.gpkg"
    assert set(gpd.list_layers(output_path)["name"]) == {
        "photons",
        "bathymetry",
    }
    photons = gpd.read_file(output_path, layer="photons")
    assert photons["photon_id"].iloc[0] == ("20240102_1234_007_6_00000000")
    assert photons["class_manual"].iloc[0] == 40
    assert photons["atl24_class"].iloc[0] == 41
    assert photons["atl24_confidence"].iloc[0] == pytest.approx(0.5)
    assert len(gpd.read_file(output_path, layer="bathymetry")) == 61
    assert result["source_status"]["beam_statuses"] == {
        "gt1l": "complete",
        "gt1r": "unclassified",
    }

    reloaded = session.read_beam(SOURCE_RELATIVE, "gt1l")
    assert reloaded["label_origin"] == "manual_output"
    assert reloaded["labels"][0] == {
        "source_row": 0,
        "label": "bathy",
        "label_source": "auto",
    }


def test_save_archives_existing_geopackage_before_replacing(
    tmp_path: Path,
) -> None:
    session = make_session(tmp_path)
    labels = session.read_beam(SOURCE_RELATIVE, "gt1l")["labels"]
    first = session.save_source(SOURCE_RELATIVE, {"gt1l": labels})
    output_path = Path(first["outputs"][0]["output_path"])
    labels = [dict(row) for row in labels]
    labels[0] = {
        "source_row": 0,
        "label": "bathy",
        "label_source": "manual",
    }

    second = session.save_source(SOURCE_RELATIVE, {"gt1l": labels})

    backup_path = Path(second["backups"][0]["backup_path"])
    assert backup_path.exists()
    assert backup_path.name == output_path.name
    assert (
        gpd.read_file(backup_path, layer="photons")["class_manual"].iloc[0]
        == 41
    )
    assert (
        gpd.read_file(output_path, layer="photons")["class_manual"].iloc[0]
        == 40
    )


def test_invalid_geopackage_is_reported(tmp_path: Path) -> None:
    session = make_session(tmp_path)
    labels = session.read_beam(SOURCE_RELATIVE, "gt1l")["labels"]
    result = session.save_source(SOURCE_RELATIVE, {"gt1l": labels})
    output_path = Path(result["outputs"][0]["output_path"])
    output_path.write_text("not a GeoPackage")

    source = session.sources_payload()["sources"][0]

    assert source["beam_statuses"]["gt1l"] == "invalid"
    with pytest.raises((ValueError, OSError)):
        session.read_beam(SOURCE_RELATIVE, "gt1l")


def test_save_rejects_incomplete_or_unsupported_labels(tmp_path: Path) -> None:
    session = make_session(tmp_path)
    labels = session.read_beam(SOURCE_RELATIVE, "gt1l")["labels"]
    with pytest.raises(ValueError, match="complete beam"):
        session.save_source(SOURCE_RELATIVE, {"gt1l": labels[:-1]})
    labels = [dict(row) for row in labels]
    labels[0]["label"] = "land"
    with pytest.raises(ValueError, match="Invalid label"):
        session.save_source(SOURCE_RELATIVE, {"gt1l": labels})


def test_save_multiple_beams_creates_one_geopackage_per_track(
    tmp_path: Path,
) -> None:
    session = make_session(tmp_path)
    left = session.read_beam(SOURCE_RELATIVE, "gt1l")["labels"]
    right = session.read_beam(SOURCE_RELATIVE, "gt1r")["labels"]

    result = session.save_source(
        SOURCE_RELATIVE,
        {"gt1l": left, "gt1r": right},
    )

    outputs = {
        item["beam"]: Path(item["output_path"]) for item in result["outputs"]
    }
    assert outputs["gt1l"].name.endswith("spot6.gpkg")
    assert outputs["gt1r"].name.endswith("spot5.gpkg")


def test_malformed_beam_does_not_hide_other_valid_beams(
    tmp_path: Path,
) -> None:
    session = make_session(tmp_path)
    assert session.input_dir is not None
    source_path = session.input_dir / SOURCE_RELATIVE
    with h5py.File(source_path, "r+") as h5:
        del h5["gt1r"]["night_flag"]
        h5["gt1r"].create_dataset("night_flag", data=[0])

    session.configure(session.input_dir, session.output_dir)

    assert session.sources_payload()["sources"][0]["beams"] == ["gt1l"]


def test_label_to_class_mapping_matches_atl24_codes() -> None:
    assert LABEL_TO_CLASS_PH == {
        "surface": 41,
        "bathy": 40,
        "no_label": 0,
    }
