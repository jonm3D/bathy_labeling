from __future__ import annotations

import hashlib
import math
from pathlib import Path
from typing import Any

import h5py
import numpy as np

from bathy_labeler.backend.models import (
    BEAM_NAMES,
    OPTIONAL_DATASETS,
    REQUIRED_DATASETS,
    BeamStrength,
    DayNight,
    PhotonTable,
    SegmentPayload,
    SegmentSummary,
    SourceFile,
    WarningRecord,
)

INVENTORY_VERSION = "atl24-labeler-inventory-v1"
SEGMENT_CONFIG_VERSION = "segment-10km-context-1km-v1"
DEFAULT_SEGMENT_LENGTH_M = 10_000
DEFAULT_CONTEXT_MARGIN_M = 1_000


class Atl24Store:
    def __init__(
        self,
        source_root: Path,
        project_root: Path,
        segments: list[SegmentSummary],
        sources: dict[str, SourceFile],
        warnings: list[WarningRecord],
    ) -> None:
        self.source_root = source_root
        self.project_root = project_root
        self.segments = segments
        self.warnings = warnings
        self._sources = sources
        self._segments_by_id = {segment.segment_id: segment for segment in segments}

    @classmethod
    def from_folder(
        cls,
        source_root: str | Path,
        project_root: str | Path,
        segment_length_m: int = DEFAULT_SEGMENT_LENGTH_M,
        context_margin_m: int = DEFAULT_CONTEXT_MARGIN_M,
    ) -> "Atl24Store":
        root = Path(source_root).expanduser().resolve()
        project = Path(project_root).expanduser().resolve()
        if segment_length_m <= 0:
            raise ValueError("segment_length_m must be positive")
        if context_margin_m < 0:
            raise ValueError("context_margin_m must be non-negative")
        if not root.exists():
            raise FileNotFoundError(f"Source folder does not exist: {root}")
        if not root.is_dir():
            raise NotADirectoryError(f"Source path is not a folder: {root}")

        sources: dict[str, SourceFile] = {}
        segments: list[SegmentSummary] = []
        warnings: list[WarningRecord] = []

        for path in sorted(root.rglob("*.h5"), key=lambda item: item.relative_to(root).as_posix()):
            relative_path = path.relative_to(root).as_posix()
            source = _source_file(root, path)
            sources[relative_path] = source
            try:
                with h5py.File(path, "r") as h5:
                    sc_orient = _read_sc_orient(h5)
                    if sc_orient == 2:
                        warnings.append(
                            WarningRecord(
                                source_relative_path=relative_path,
                                beam=None,
                                message="ATL24 transition orientation is outside v1 and was rejected.",
                            )
                        )
                        continue
                    for beam_name in BEAM_NAMES:
                        if beam_name not in h5:
                            continue
                        missing = [name for name in REQUIRED_DATASETS if name not in h5[beam_name]]
                        if missing:
                            warnings.append(
                                WarningRecord(
                                    source_relative_path=relative_path,
                                    beam=beam_name,
                                    message=f"Missing datasets: {', '.join(missing)}",
                                )
                            )
                            continue
                        _validate_beam_lengths(h5[beam_name])
                        segments.extend(
                            _segments_for_beam(
                                h5=h5,
                                source=source,
                                beam_name=beam_name,
                                sc_orient=sc_orient,
                                segment_length_m=segment_length_m,
                                context_margin_m=context_margin_m,
                            )
                        )
            except OSError as exc:
                warnings.append(WarningRecord(relative_path, None, f"Unable to read HDF5 file: {exc}"))

        return cls(
            source_root=root,
            project_root=project,
            segments=sorted(segments, key=_segment_sort_key),
            sources=sources,
            warnings=warnings,
        )

    @property
    def total_photons(self) -> int:
        return sum(segment.photon_count for segment in self.segments)

    def manifest(self) -> dict[str, Any]:
        return {
            "inventory_version": INVENTORY_VERSION,
            "segment_config_version": SEGMENT_CONFIG_VERSION,
            "source_root": str(self.source_root),
            "project_root": str(self.project_root),
            "segment_count": len(self.segments),
            "total_segment_photons": self.total_photons,
            "warnings": [warning.to_dict() for warning in self.warnings],
        }

    def read_segment(self, segment_id: str) -> SegmentPayload:
        segment = self._segments_by_id.get(segment_id)
        if segment is None:
            raise KeyError(f"Unknown segment_id: {segment_id}")
        source = self._sources[segment.source_relative_path]
        with h5py.File(source.path, "r") as h5:
            group = h5[segment.beam]
            assigned = _read_photons_for_bounds(
                group,
                start_m=segment.x_atc_start_m,
                end_m=segment.x_atc_end_m,
            )
            context = _read_photons_for_bounds(
                group,
                start_m=segment.context_x_atc_start_m,
                end_m=segment.context_x_atc_end_m,
            )
        return SegmentPayload(segment=segment, assigned=assigned, context=context)


def _source_file(root: Path, path: Path) -> SourceFile:
    stat = path.stat()
    relative_path = path.relative_to(root).as_posix()
    parent = path.parent.relative_to(root).as_posix()
    source_label = None if parent == "." else parent.split("/", 1)[0]
    return SourceFile(
        path=path,
        relative_path=relative_path,
        stable_source_file_id=_stable_source_file_id(path, relative_path),
        source_label=source_label,
        size_bytes=stat.st_size,
        modified_ns=stat.st_mtime_ns,
    )


def _stable_source_file_id(path: Path, relative_path: str) -> str:
    digest = hashlib.sha1(f"{path.name}|{relative_path}".encode("utf-8")).hexdigest()[:16]
    return f"{path.stem}-{digest}"


def _read_sc_orient(h5: h5py.File) -> int:
    if "orbit_info" not in h5 or "sc_orient" not in h5["orbit_info"]:
        return 1
    value = np.asarray(h5["orbit_info"]["sc_orient"][()]).reshape(-1)
    if value.size == 0:
        return 1
    return int(value[0])


def _segments_for_beam(
    h5: h5py.File,
    source: SourceFile,
    beam_name: str,
    sc_orient: int,
    segment_length_m: int,
    context_margin_m: int,
) -> list[SegmentSummary]:
    group = h5[beam_name]
    x_atc = np.asarray(group["x_atc"][:]).astype(float)
    if x_atc.size == 0:
        return []
    finite_x = x_atc[np.isfinite(x_atc)]
    if finite_x.size == 0:
        return []

    start_m = int(math.floor(float(np.nanmin(finite_x))))
    track_end_m = int(math.ceil(float(np.nanmax(finite_x)) + _median_step_m(finite_x)))
    if track_end_m <= start_m:
        track_end_m = start_m + segment_length_m

    segments: list[SegmentSummary] = []
    current_start = start_m
    while current_start < track_end_m:
        current_end = min(current_start + segment_length_m, track_end_m)
        mask = (x_atc >= current_start) & (x_atc < current_end)
        photon_count = int(np.count_nonzero(mask))
        if photon_count > 0:
            night_flag = np.asarray(group["night_flag"][:]).astype(np.int8)
            segment_night = night_flag[mask]
            day_night: DayNight = "night" if int(np.count_nonzero(segment_night)) >= photon_count / 2 else "day"
            segment_id = _segment_id(
                source=source,
                beam_name=beam_name,
                start_m=current_start,
                end_m=current_end,
            )
            segments.append(
                SegmentSummary(
                    segment_id=segment_id,
                    inventory_version=INVENTORY_VERSION,
                    segment_config_version=SEGMENT_CONFIG_VERSION,
                    stable_source_file_id=source.stable_source_file_id,
                    source_relative_path=source.relative_path,
                    source_label=source.source_label,
                    file_name=source.path.name,
                    beam=beam_name,
                    x_atc_start_m=current_start,
                    x_atc_end_m=current_end,
                    context_x_atc_start_m=max(start_m, current_start - context_margin_m),
                    context_x_atc_end_m=min(track_end_m, current_end + context_margin_m),
                    photon_count=photon_count,
                    day_night=day_night,
                    beam_strength=_beam_strength(beam_name, sc_orient),
                )
            )
        current_start = current_end
    return segments


def _median_step_m(x_atc: np.ndarray) -> float:
    if x_atc.size < 2:
        return 1.0
    diffs = np.diff(np.sort(x_atc[np.isfinite(x_atc)]))
    positive = diffs[diffs > 0]
    if positive.size == 0:
        return 1.0
    return float(np.nanmedian(positive))


def _segment_id(source: SourceFile, beam_name: str, start_m: int, end_m: int) -> str:
    raw = (
        f"{INVENTORY_VERSION}|{SEGMENT_CONFIG_VERSION}|{source.stable_source_file_id}|"
        f"{source.relative_path}|{beam_name}|{start_m}|{end_m}"
    )
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]
    return f"{source.path.stem}_{beam_name}_xatc_{start_m}_{end_m}_{digest}"


def _beam_strength(beam_name: str, sc_orient: int) -> BeamStrength:
    side = beam_name[-1]
    if sc_orient == 1:
        return "strong" if side == "r" else "weak"
    if sc_orient == 0:
        return "strong" if side == "l" else "weak"
    raise ValueError("transition orientation is outside v1")


def _read_photons_for_bounds(h5_group: h5py.Group, start_m: int, end_m: int) -> PhotonTable:
    x_atc = np.asarray(h5_group["x_atc"][:]).astype(float)
    selected = np.flatnonzero((x_atc >= start_m) & (x_atc < end_m))
    return _read_photon_rows(h5_group, selected)


def _read_photon_rows(h5_group: h5py.Group, rows: np.ndarray) -> PhotonTable:
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


def _validate_beam_lengths(group: h5py.Group) -> None:
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


def _segment_sort_key(segment: SegmentSummary) -> tuple[str, str, int, int]:
    return (segment.source_relative_path, segment.beam, segment.x_atc_start_m, segment.x_atc_end_m)
