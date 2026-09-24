from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

BEAM_NAMES = ("gt1l", "gt1r", "gt2l", "gt2r", "gt3l", "gt3r")
REQUIRED_DATASETS = ("lon_ph", "lat_ph", "x_atc", "ortho_h", "surface_h", "index_ph", "night_flag")
OPTIONAL_DATASETS = ("class_ph",)
FINAL_LABELS = ("surface", "bathy", "no_label", "land", "noise", "ambiguous")
LABEL_SOURCES = ("manual", "auto")

BeamStrength = Literal["strong", "weak"]
FinalLabel = Literal["surface", "bathy", "no_label", "land", "noise", "ambiguous"]


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

