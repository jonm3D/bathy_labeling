from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

BEAM_NAMES = ("gt1l", "gt1r", "gt2l", "gt2r", "gt3l", "gt3r")
REQUIRED_DATASETS = ("lon_ph", "lat_ph", "x_atc", "ortho_h", "surface_h", "index_ph", "night_flag")
OPTIONAL_DATASETS = ("class_ph",)
FINAL_LABELS = ("surface", "bathy", "land", "noise", "ambiguous")
LABEL_SOURCES = ("manual", "auto")

BeamStrength = Literal["strong", "weak"]
DayNight = Literal["day", "night"]
SegmentStatus = Literal["unlabeled", "draft", "complete", "stale", "conflict"]
FinalLabel = Literal["surface", "bathy", "land", "noise", "ambiguous"]
LabelSource = Literal["manual", "auto"]


@dataclass(frozen=True)
class WarningRecord:
    source_relative_path: str
    beam: str | None
    message: str

    def to_dict(self) -> dict[str, str | None]:
        return {
            "source_relative_path": self.source_relative_path,
            "beam": self.beam,
            "message": self.message,
        }


@dataclass(frozen=True)
class SourceFile:
    path: Path
    relative_path: str
    stable_source_file_id: str
    source_label: str | None
    size_bytes: int
    modified_ns: int


@dataclass(frozen=True)
class SegmentSummary:
    segment_id: str
    inventory_version: str
    segment_config_version: str
    stable_source_file_id: str
    source_relative_path: str
    source_label: str | None
    file_name: str
    beam: str
    x_atc_start_m: int
    x_atc_end_m: int
    context_x_atc_start_m: int
    context_x_atc_end_m: int
    photon_count: int
    day_night: DayNight
    beam_strength: BeamStrength
    status: SegmentStatus = "unlabeled"

    def to_dict(self) -> dict[str, int | str | None]:
        return {
            "segment_id": self.segment_id,
            "inventory_version": self.inventory_version,
            "segment_config_version": self.segment_config_version,
            "stable_source_file_id": self.stable_source_file_id,
            "source_relative_path": self.source_relative_path,
            "source_label": self.source_label,
            "file_name": self.file_name,
            "beam": self.beam,
            "x_atc_start_m": self.x_atc_start_m,
            "x_atc_end_m": self.x_atc_end_m,
            "context_x_atc_start_m": self.context_x_atc_start_m,
            "context_x_atc_end_m": self.context_x_atc_end_m,
            "photon_count": self.photon_count,
            "day_night": self.day_night,
            "beam_strength": self.beam_strength,
            "status": self.status,
        }


@dataclass(frozen=True)
class PhotonTable:
    source_row: list[int]
    index_ph: list[int]
    lat: list[float]
    lon: list[float]
    x_atc_m: list[float]
    ortho_h_m: list[float]
    surface_h_m: list[float]
    night_flag: list[int]
    atl24_class_ph: list[int | None]

    @property
    def count(self) -> int:
        return len(self.source_row)

    def to_dict(self) -> dict[str, list[int] | list[float]]:
        return {
            "source_row": self.source_row,
            "index_ph": self.index_ph,
            "lat": self.lat,
            "lon": self.lon,
            "x_atc_m": self.x_atc_m,
            "ortho_h_m": self.ortho_h_m,
            "surface_h_m": self.surface_h_m,
            "night_flag": self.night_flag,
            "atl24_class_ph": self.atl24_class_ph,
        }


@dataclass(frozen=True)
class SegmentPayload:
    segment: SegmentSummary
    assigned: PhotonTable
    context: PhotonTable

    def to_dict(self) -> dict[str, object]:
        return {
            "segment": self.segment.to_dict(),
            "assigned": self.assigned.to_dict(),
            "context": self.context.to_dict(),
        }
