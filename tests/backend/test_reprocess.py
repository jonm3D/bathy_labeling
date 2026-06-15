from __future__ import annotations

import shutil
from pathlib import Path

import h5py
import numpy as np

from bathy_labeler.backend.reprocess import LABEL_TO_CLASS_PH, ReprocessSession

from tests.backend.test_hdf5_store import write_atl24_like_file


def make_session(tmp_path: Path) -> ReprocessSession:
    input_dir = tmp_path / "ATL24_inputs"
    output_dir = tmp_path / "ATL24_inputs_labeled"
    write_atl24_like_file(input_dir / "Guam" / "ATL24_sample.h5")
    write_atl24_like_file(input_dir / "Guam" / "ATL24_sample_manual.h5")
    return ReprocessSession(input_dir=input_dir, output_dir=output_dir)


def write_manual_output(session: ReprocessSession, source_relative_path: str, beam: str, class_ph: np.ndarray) -> Path:
    assert session.input_dir is not None
    assert session.output_dir is not None
    source_path = session.input_dir / source_relative_path
    output_path = session.output_dir / Path(source_relative_path).parent / f"{Path(source_relative_path).stem}_{beam}_manual.h5"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source_path, output_path)
    with h5py.File(output_path, "r+") as h5:
        h5[beam]["class_ph"][:] = class_ph
    return output_path


def add_confidence_datasets(path: Path) -> None:
    with h5py.File(path, "r+") as h5:
        for beam in ("gt1l", "gt1r"):
            count = int(h5[beam]["x_atc"].shape[0])
            h5[beam].create_dataset("confidence", data=np.full(count, 0.25, dtype=np.float32))
            h5[beam].create_dataset("low_confidence_flag", data=np.ones(count, dtype=np.int8))


def test_configuring_session_scans_original_h5_files_only(tmp_path: Path) -> None:
    session = make_session(tmp_path)

    manifest = session.manifest()
    sources = session.sources_payload()

    assert manifest["mode"] == "reprocess"
    assert manifest["input_dir"].endswith("ATL24_inputs")
    assert manifest["output_dir"].endswith("ATL24_inputs_labeled")
    assert sources["count"] == 1
    assert sources["sources"][0]["source_relative_path"] == "Guam/ATL24_sample.h5"
    assert sources["sources"][0]["file_name"] == "ATL24_sample.h5"
    assert sources["sources"][0]["beams"] == ["gt1l", "gt1r"]
    assert sources["sources"][0]["status"] == "unclassified"
    assert sources["sources"][0]["beam_count"] == 2
    assert sources["sources"][0]["completed_beam_count"] == 0
    assert sources["sources"][0]["beam_statuses"] == {"gt1l": "unclassified", "gt1r": "unclassified"}


def test_sources_payload_reports_partial_and_complete_output_status(tmp_path: Path) -> None:
    session = make_session(tmp_path)
    payload = session.read_beam("Guam/ATL24_sample.h5", "gt1l")
    gt1l_classes = np.full(len(payload["labels"]), 40, dtype=np.int16)
    gt1r_classes = np.full(len(payload["labels"]), 41, dtype=np.int16)

    write_manual_output(session, "Guam/ATL24_sample.h5", "gt1l", gt1l_classes)
    partial = session.sources_payload()["sources"][0]

    assert partial["status"] == "partial"
    assert partial["beam_count"] == 2
    assert partial["completed_beam_count"] == 1
    assert partial["beam_statuses"] == {"gt1l": "complete", "gt1r": "unclassified"}

    write_manual_output(session, "Guam/ATL24_sample.h5", "gt1r", gt1r_classes)
    complete = session.sources_payload()["sources"][0]

    assert complete["status"] == "complete"
    assert complete["completed_beam_count"] == 2
    assert complete["beam_statuses"] == {"gt1l": "complete", "gt1r": "complete"}


def test_full_beam_payload_uses_original_atl24_classifications(tmp_path: Path) -> None:
    session = make_session(tmp_path)

    payload = session.read_beam("Guam/ATL24_sample.h5", "gt1l")

    assert payload["beam"]["beam"] == "gt1l"
    assert payload["beam"]["photon_count"] == 150
    assert payload["beam"]["x_atc_start_m"] == 0.0
    assert payload["beam"]["x_atc_end_m"] == 14900.0
    assert payload["photons"]["source_row"][:3] == [0, 1, 2]
    assert payload["photons"]["source_row"][-1] == 149
    assert payload["labels"][:3] == [
        {"source_row": 0, "label": "surface", "label_source": "auto"},
        {"source_row": 1, "label": "surface", "label_source": "auto"},
        {"source_row": 2, "label": "surface", "label_source": "auto"},
    ]
    assert payload["labels"][20] == {"source_row": 20, "label": "bathy", "label_source": "auto"}
    assert payload["labels"][-1] == {"source_row": 149, "label": "no_label", "label_source": "auto"}
    assert payload["label_origin"] == "atl24_original"
    assert payload["manual_output_path"] is None


def test_full_beam_payload_uses_existing_manual_output_classifications(tmp_path: Path) -> None:
    session = make_session(tmp_path)
    class_ph = np.zeros(150, dtype=np.int16)
    class_ph[0] = 40
    class_ph[1] = 41
    manual_path = write_manual_output(session, "Guam/ATL24_sample.h5", "gt1l", class_ph)

    payload = session.read_beam("Guam/ATL24_sample.h5", "gt1l")

    assert payload["label_origin"] == "manual_output"
    assert payload["manual_output_path"] == str(manual_path)
    assert payload["labels"][:3] == [
        {"source_row": 0, "label": "bathy", "label_source": "auto"},
        {"source_row": 1, "label": "surface", "label_source": "auto"},
        {"source_row": 2, "label": "no_label", "label_source": "auto"},
    ]


def test_manual_output_with_mismatched_class_length_fails_clearly(tmp_path: Path) -> None:
    session = make_session(tmp_path)
    manual_path = write_manual_output(session, "Guam/ATL24_sample.h5", "gt1l", np.zeros(150, dtype=np.int16))
    with h5py.File(manual_path, "r+") as h5:
        del h5["gt1l"]["class_ph"]
        h5["gt1l"].create_dataset("class_ph", data=np.zeros(149, dtype=np.int16))

    try:
        session.read_beam("Guam/ATL24_sample.h5", "gt1l")
    except ValueError as exc:
        assert "class_ph length" in str(exc)
        assert "gt1l" in str(exc)
    else:
        raise AssertionError("Expected mismatched manual output class_ph length to fail")


def test_save_creates_per_beam_manual_h5_and_rewrites_only_target_beam_classifications(tmp_path: Path) -> None:
    session = make_session(tmp_path)
    assert session.input_dir is not None
    add_confidence_datasets(session.input_dir / "Guam" / "ATL24_sample.h5")
    payload = session.read_beam("Guam/ATL24_sample.h5", "gt1l")
    labels = [
        {"source_row": row["source_row"], "label": "surface", "label_source": "auto"}
        for row in payload["labels"]
    ]
    labels[0] = {"source_row": 0, "label": "bathy", "label_source": "manual"}
    labels[1] = {"source_row": 1, "label": "no_label", "label_source": "manual"}
    labels[2] = {"source_row": 2, "label": "surface", "label_source": "manual"}

    result = session.save_source("Guam/ATL24_sample.h5", {"gt1l": labels})

    assert result["written_beams"] == ["gt1l"]
    assert len(result["outputs"]) == 1
    assert result["source_status"]["status"] == "partial"
    assert result["source_status"]["beam_statuses"] == {"gt1l": "complete", "gt1r": "unclassified"}
    output_path = Path(result["outputs"][0]["output_path"])
    assert result["outputs"][0]["beam"] == "gt1l"
    assert output_path.name == "ATL24_sample_gt1l_manual.h5"
    assert output_path.exists()
    with h5py.File(tmp_path / "ATL24_inputs" / "Guam" / "ATL24_sample.h5", "r") as original:
        with h5py.File(output_path, "r") as manual:
            assert manual.attrs["rgt"] == original.attrs["rgt"]
            assert manual["gt1l"]["class_ph"][:5].tolist() == [40, 0, 41, 41, 41]
            assert manual["gt1r"]["class_ph"][:].tolist() == original["gt1r"]["class_ph"][:].tolist()
            assert manual["gt1l"]["confidence"][:].tolist() == [1.0] * 150
            assert manual["gt1l"]["low_confidence_flag"][:].tolist() == [0] * 150
            assert manual["gt1r"]["confidence"][:].tolist() == original["gt1r"]["confidence"][:].tolist()
            assert manual["gt1r"]["low_confidence_flag"][:].tolist() == original["gt1r"]["low_confidence_flag"][:].tolist()


def test_save_multiple_beams_creates_one_manual_h5_per_beam(tmp_path: Path) -> None:
    session = make_session(tmp_path)
    gt1l_payload = session.read_beam("Guam/ATL24_sample.h5", "gt1l")
    gt1r_payload = session.read_beam("Guam/ATL24_sample.h5", "gt1r")
    gt1l_labels = [dict(row) for row in gt1l_payload["labels"]]
    gt1r_labels = [dict(row) for row in gt1r_payload["labels"]]
    gt1l_labels[0] = {"source_row": 0, "label": "bathy", "label_source": "manual"}
    gt1r_labels[0] = {"source_row": 0, "label": "no_label", "label_source": "manual"}

    result = session.save_source("Guam/ATL24_sample.h5", {"gt1l": gt1l_labels, "gt1r": gt1r_labels})

    outputs = {item["beam"]: Path(item["output_path"]) for item in result["outputs"]}
    assert sorted(outputs) == ["gt1l", "gt1r"]
    assert outputs["gt1l"].name == "ATL24_sample_gt1l_manual.h5"
    assert outputs["gt1r"].name == "ATL24_sample_gt1r_manual.h5"
    with h5py.File(tmp_path / "ATL24_inputs" / "Guam" / "ATL24_sample.h5", "r") as original:
        with h5py.File(outputs["gt1l"], "r") as gt1l_manual:
            assert gt1l_manual["gt1l"]["class_ph"][0] == 40
            assert gt1l_manual["gt1r"]["class_ph"][:].tolist() == original["gt1r"]["class_ph"][:].tolist()
        with h5py.File(outputs["gt1r"], "r") as gt1r_manual:
            assert gt1r_manual["gt1l"]["class_ph"][:].tolist() == original["gt1l"]["class_ph"][:].tolist()
            assert gt1r_manual["gt1r"]["class_ph"][0] == 0


def test_label_to_class_mapping_matches_atl24_codes() -> None:
    assert LABEL_TO_CLASS_PH == {
        "surface": 41,
        "bathy": 40,
        "no_label": 0,
    }


def test_full_beam_proposal_preserves_manual_seed_rows(tmp_path: Path) -> None:
    session = make_session(tmp_path)

    proposal = session.propose(
        "Guam/ATL24_sample.h5",
        "gt1l",
        seeds=[
            {"source_row": 0, "label": "surface", "label_source": "manual"},
            {"source_row": 149, "label": "bathy", "label_source": "manual"},
        ],
    )

    assert proposal["rows"][0] == {"source_row": 0, "label": "surface", "label_source": "manual"}
    assert proposal["rows"][-1] == {"source_row": 149, "label": "bathy", "label_source": "manual"}
    assert len(proposal["rows"]) == 150


def test_reset_returns_original_atl24_labels(tmp_path: Path) -> None:
    session = make_session(tmp_path)

    reset = session.reset_beam("Guam/ATL24_sample.h5", "gt1l")

    assert reset["rows"][0] == {"source_row": 0, "label": "surface", "label_source": "auto"}
    assert reset["rows"][20] == {"source_row": 20, "label": "bathy", "label_source": "auto"}
    assert reset["rows"][-1] == {"source_row": 149, "label": "no_label", "label_source": "auto"}


def test_full_beam_proposal_uses_no_label_for_default_residual_class(tmp_path: Path) -> None:
    session = make_session(tmp_path)

    proposal = session.propose(
        "Guam/ATL24_sample.h5",
        "gt1l",
        seeds=[{"source_row": 0, "label": "surface", "label_source": "manual"}],
    )

    labels = {row["label"] for row in proposal["rows"]}
    assert labels <= {"surface", "no_label"}
    assert proposal["rows"][-1]["label"] == "no_label"
