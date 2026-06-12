from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from bathy_labeler.backend.hdf5_store import Atl24Store
from bathy_labeler.backend.labels import LabelSidecarStore, LabelValidationError

from tests.backend.test_hdf5_store import write_atl24_like_file


def make_payload(tmp_path: Path):
    source_root = tmp_path / "sources"
    project_root = tmp_path / "project"
    write_atl24_like_file(source_root / "Guam" / "ATL24_sample.h5")
    store = Atl24Store.from_folder(source_root=source_root, project_root=project_root)
    return project_root, store.read_segment(store.segments[0].segment_id)


def make_labels(source_rows: list[int], label: str = "noise", label_source: str = "auto"):
    return [
        {"source_row": source_row, "label": label, "label_source": label_source}
        for source_row in source_rows
    ]


def read_csv_rows(path: Path):
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def test_save_complete_sidecar_writes_required_rows_and_metadata(tmp_path: Path):
    project_root, payload = make_payload(tmp_path)
    sidecars = LabelSidecarStore(project_root)

    saved = sidecars.save(payload.segment, payload.assigned, make_labels(payload.assigned.source_row))

    assert saved.status == "complete"
    assert saved.csv_path.exists()
    assert saved.metadata_path.exists()
    rows = read_csv_rows(saved.csv_path)
    assert rows[0] == {
        "source_row": "0",
        "index_ph": "10000",
        "lat": "13.4",
        "lon": "-144.8",
        "ortho_h_m": "1.5",
        "label": "noise",
        "label_source": "auto",
    }
    assert [int(row["source_row"]) for row in rows] == sorted(payload.assigned.source_row)

    metadata = json.loads(saved.metadata_path.read_text(encoding="utf-8"))
    assert metadata["segment_id"] == payload.segment.segment_id
    assert metadata["row_key_count"] == payload.assigned.count
    assert metadata["row_key_checksum"]
    assert metadata["final_label_counts"] == {"noise": payload.assigned.count}
    assert metadata["manual_count"] == 0
    assert metadata["auto_count"] == payload.assigned.count
    assert sidecars.status_for(payload.segment, payload.assigned) == "complete"


def test_incomplete_or_invalid_sidecars_are_rejected(tmp_path: Path):
    project_root, payload = make_payload(tmp_path)
    sidecars = LabelSidecarStore(project_root)

    with pytest.raises(LabelValidationError, match="exactly one row"):
        sidecars.save(payload.segment, payload.assigned, make_labels(payload.assigned.source_row[:-1]))

    bad_labels = make_labels(payload.assigned.source_row)
    bad_labels[0]["label"] = "maybe"
    with pytest.raises(LabelValidationError, match="Invalid label"):
        sidecars.save(payload.segment, payload.assigned, bad_labels)


def test_replacing_complete_sidecar_archives_previous_and_updates_manual_source(tmp_path: Path):
    project_root, payload = make_payload(tmp_path)
    sidecars = LabelSidecarStore(project_root)
    source_rows = payload.assigned.source_row
    sidecars.save(payload.segment, payload.assigned, make_labels(source_rows, label="noise", label_source="auto"))

    revised = make_labels(source_rows, label="noise", label_source="auto")
    revised[0] = {"source_row": source_rows[0], "label": "bathy", "label_source": "manual"}
    saved = sidecars.save(payload.segment, payload.assigned, revised)

    rows = read_csv_rows(saved.csv_path)
    assert rows[0]["label"] == "bathy"
    assert rows[0]["label_source"] == "manual"
    archive_root = project_root / "labels" / "archive" / payload.segment.segment_id
    archived_csvs = list(archive_root.glob("*/labels.csv"))
    archived_jsons = list(archive_root.glob("*/labels.json"))
    assert len(archived_csvs) == 1
    assert len(archived_jsons) == 1
    assert read_csv_rows(archived_csvs[0])[0]["label"] == "noise"


def test_status_is_stale_when_row_key_checksum_does_not_match(tmp_path: Path):
    project_root, payload = make_payload(tmp_path)
    sidecars = LabelSidecarStore(project_root)
    sidecars.save(payload.segment, payload.assigned, make_labels(payload.assigned.source_row))

    shifted = payload.assigned.__class__(
        source_row=payload.assigned.source_row,
        index_ph=[value + 1 for value in payload.assigned.index_ph],
        lat=payload.assigned.lat,
        lon=payload.assigned.lon,
        x_atc_m=payload.assigned.x_atc_m,
        ortho_h_m=payload.assigned.ortho_h_m,
        surface_h_m=payload.assigned.surface_h_m,
        night_flag=payload.assigned.night_flag,
        atl24_class_ph=payload.assigned.atl24_class_ph,
    )

    assert sidecars.status_for(payload.segment, shifted) == "stale"
