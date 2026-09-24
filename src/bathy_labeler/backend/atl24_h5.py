from __future__ import annotations

import h5py
import numpy as np

from bathy_labeler.backend.models import (
    OPTIONAL_DATASETS,
    REQUIRED_DATASETS,
    BeamStrength,
    PhotonTable,
)


def read_sc_orient(h5: h5py.File) -> int:
    if "orbit_info" not in h5 or "sc_orient" not in h5["orbit_info"]:
        return 1
    value = np.asarray(h5["orbit_info"]["sc_orient"][()]).reshape(-1)
    if value.size == 0:
        return 1
    return int(value[0])


def beam_strength(beam_name: str, sc_orient: int) -> BeamStrength:
    side = beam_name[-1]
    if sc_orient == 1:
        return "strong" if side == "r" else "weak"
    if sc_orient == 0:
        return "strong" if side == "l" else "weak"
    raise ValueError("transition orientation is not supported")


def read_photon_rows(h5_group: h5py.Group, rows: np.ndarray) -> PhotonTable:
    return PhotonTable(
        source_row=rows.astype(int).tolist(),
        index_ph=np.asarray(h5_group["index_ph"][rows]).astype(np.int64).astype(int).tolist(),
        lat=np.asarray(h5_group["lat_ph"][rows]).astype(float).tolist(),
        lon=np.asarray(h5_group["lon_ph"][rows]).astype(float).tolist(),
        x_atc_m=np.asarray(h5_group["x_atc"][rows]).astype(float).tolist(),
        ortho_h_m=np.asarray(h5_group["ortho_h"][rows]).astype(float).tolist(),
        surface_h_m=np.asarray(h5_group["surface_h"][rows]).astype(float).tolist(),
        night_flag=np.asarray(h5_group["night_flag"][rows]).astype(np.int8).astype(int).tolist(),
        atl24_class_ph=_optional_int_rows(h5_group, "class_ph", rows),
    )


def validate_beam_lengths(group: h5py.Group) -> None:
    lengths = {name: _dataset_length(group[name]) for name in REQUIRED_DATASETS}
    lengths.update({name: _dataset_length(group[name]) for name in OPTIONAL_DATASETS if name in group})
    if len(set(lengths.values())) != 1:
        raise ValueError(f"Dataset lengths do not match: {lengths}")


def _dataset_length(dataset: h5py.Dataset) -> int:
    if len(dataset.shape) != 1:
        raise ValueError(f"Dataset must be one-dimensional: {dataset.name}")
    return int(dataset.shape[0])


def _optional_int_rows(h5_group: h5py.Group, name: str, rows: np.ndarray) -> list[int | None]:
    if name not in h5_group:
        return [None for _ in rows]
    return np.asarray(h5_group[name][rows]).astype(np.int64).astype(int).tolist()
