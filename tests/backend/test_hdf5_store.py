from __future__ import annotations

from pathlib import Path

import h5py
import numpy as np

from bathy_labeler.backend.hdf5_store import Atl24Store


def write_atl24_like_file(path: Path, sc_orient: int = 1, scalar_orient: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with h5py.File(path, "w") as h5:
        orbit_info = h5.create_group("orbit_info")
        orient_data = np.asarray(sc_orient, dtype=np.int8) if scalar_orient else np.asarray([sc_orient], dtype=np.int8)
        orbit_info.create_dataset("sc_orient", data=orient_data)
        h5.attrs["rgt"] = "1234"
        h5.attrs["cycle"] = "07"

        for beam in ("gt1l", "gt1r"):
            group = h5.create_group(beam)
            count = 150
            x_atc = np.arange(count, dtype=float) * 100.0
            lon = -144.8 + x_atc * 0.00001 + (0.001 if beam.endswith("r") else 0.0)
            lat = 13.4 + x_atc * 0.000005
            ortho_h = np.linspace(1.5, -8.0, count)
            surface_h = np.full(count, 0.25)
            index_ph = np.arange(10_000, 10_000 + count, dtype=np.int64)
            class_ph = np.zeros(count, dtype=np.int16)
            class_ph[:20] = 41
            class_ph[20:80] = 40
            night_flag = np.concatenate(
                [np.ones(100, dtype=np.int8), np.zeros(50, dtype=np.int8)]
            )
            group.create_dataset("lon_ph", data=lon)
            group.create_dataset("lat_ph", data=lat)
            group.create_dataset("x_atc", data=x_atc)
            group.create_dataset("ortho_h", data=ortho_h)
            group.create_dataset("surface_h", data=surface_h)
            group.create_dataset("index_ph", data=index_ph)
            group.create_dataset("class_ph", data=class_ph)
            group.create_dataset("night_flag", data=night_flag)


def test_inventory_recursively_discovers_h5_files_and_generates_deterministic_segments(tmp_path: Path):
    source_root = tmp_path / "sources"
    project_root = tmp_path / "project"
    write_atl24_like_file(source_root / "Guam" / "ATL24_sample.h5")

    first = Atl24Store.from_folder(source_root=source_root, project_root=project_root)
    second = Atl24Store.from_folder(source_root=source_root, project_root=project_root)

    first_ids = [segment.segment_id for segment in first.segments]
    second_ids = [segment.segment_id for segment in second.segments]
    assert first_ids == second_ids
    assert len(first.segments) == 4
    assert all("file-0" not in segment.segment_id for segment in first.segments)
    assert {segment.source_label for segment in first.segments} == {"Guam"}

    first_segment = first.segments[0]
    assert first_segment.source_relative_path == "Guam/ATL24_sample.h5"
    assert first_segment.beam == "gt1l"
    assert first_segment.x_atc_start_m == 0
    assert first_segment.x_atc_end_m == 10_000
    assert first_segment.context_x_atc_start_m == 0
    assert first_segment.context_x_atc_end_m == 11_000
    assert first_segment.photon_count == 100
    assert first_segment.day_night == "night"
    assert first_segment.beam_strength == "weak"

    right_segment = next(
        segment for segment in first.segments if segment.beam == "gt1r" and segment.x_atc_start_m == 0
    )
    assert right_segment.beam_strength == "strong"


def test_segment_payload_contains_assigned_rows_and_context(tmp_path: Path):
    source_root = tmp_path / "sources"
    project_root = tmp_path / "project"
    write_atl24_like_file(source_root / "Guam" / "ATL24_sample.h5")
    store = Atl24Store.from_folder(source_root=source_root, project_root=project_root)

    segment = store.segments[0]
    payload = store.read_segment(segment.segment_id)

    assert payload.segment.segment_id == segment.segment_id
    assert payload.assigned.source_row[:3] == [0, 1, 2]
    assert payload.assigned.source_row[-1] == 99
    assert payload.assigned.index_ph[:2] == [10_000, 10_001]
    assert payload.assigned.lat[0] == 13.4
    assert payload.assigned.lon[0] == -144.8
    assert payload.assigned.ortho_h_m[0] == 1.5
    assert payload.assigned.surface_h_m[0] == 0.25
    assert payload.assigned.atl24_class_ph[:3] == [41, 41, 41]
    assert payload.assigned.atl24_class_ph[20] == 40
    assert payload.assigned.atl24_class_ph[-1] == 0
    assert payload.assigned.x_atc_m[0] == 0.0
    assert payload.context.source_row[0] == 0
    assert payload.context.source_row[-1] == 109


def test_transition_orientation_is_rejected(tmp_path: Path):
    source_root = tmp_path / "sources"
    project_root = tmp_path / "project"
    write_atl24_like_file(source_root / "ATL24_transition.h5", sc_orient=2)

    store = Atl24Store.from_folder(source_root=source_root, project_root=project_root)

    assert store.segments == []
    assert len(store.warnings) == 1
    assert "transition orientation" in store.warnings[0].message


def test_scalar_spacecraft_orientation_dataset_is_supported(tmp_path: Path):
    source_root = tmp_path / "sources"
    project_root = tmp_path / "project"
    write_atl24_like_file(source_root / "ATL24_scalar_orient.h5", sc_orient=1, scalar_orient=True)

    store = Atl24Store.from_folder(source_root=source_root, project_root=project_root)

    assert len(store.segments) == 4
    assert store.segments[0].beam_strength == "weak"
