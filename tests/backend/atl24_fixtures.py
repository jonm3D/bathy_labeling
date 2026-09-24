from __future__ import annotations

from pathlib import Path

import h5py
import numpy as np


def write_atl24_like_file(
    path: Path, sc_orient: int = 1, scalar_orient: bool = False
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with h5py.File(path, "w") as h5:
        orbit_info = h5.create_group("orbit_info")
        orient_data = (
            np.asarray(sc_orient, dtype=np.int8)
            if scalar_orient
            else np.asarray([sc_orient], dtype=np.int8)
        )
        orbit_info.create_dataset("sc_orient", data=orient_data)
        h5.attrs["rgt"] = "1234"
        h5.attrs["cycle"] = "07"

        for beam in ("gt1l", "gt1r"):
            group = h5.create_group(beam)
            count = 150
            x_atc = np.arange(count, dtype=float) * 100.0
            lon = (
                -144.8
                + x_atc * 0.00001
                + (0.001 if beam.endswith("r") else 0.0)
            )
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
            group.create_dataset(
                "confidence", data=np.full(count, 0.5, dtype=np.float32)
            )
            group.create_dataset(
                "low_confidence_flag", data=np.zeros(count, dtype=np.int8)
            )

