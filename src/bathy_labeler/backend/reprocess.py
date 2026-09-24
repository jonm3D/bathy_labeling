from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import geopandas as gpd
import h5py
import numpy as np

from bathy_labeler.backend.classified_output import (
    build_classified_frame,
    canonical_photon_id,
    labeled_utc_now,
    output_is_valid,
    read_manual_classes,
    write_classified_geopackage,
)
from bathy_labeler.backend.dem import sample_dem_along_track
from bathy_labeler.backend.atl24_h5 import (
    beam_strength,
    read_photon_rows,
    read_sc_orient,
    validate_beam_lengths,
)
from bathy_labeler.backend.models import (
    BEAM_NAMES,
    LABEL_TO_CLASS_PH,
    REQUIRED_DATASETS,
    PhotonTable,
    labels_from_atl24_classes,
)
from bathy_labeler.backend.proposals import generate_seeded_proposal

BeamOutputStatus = Literal["complete", "unclassified", "invalid"]
FileOutputStatus = Literal["complete", "partial", "unclassified", "invalid"]
LabelOrigin = Literal["manual_output", "atl24_original"]


@dataclass(frozen=True)
class ReprocessSource:
    path: Path
    relative_path: str
    beams: tuple[str, ...]

    def to_dict(
        self, status: dict[str, object] | None = None
    ) -> dict[str, object]:
        payload: dict[str, object] = {
            "source_relative_path": self.relative_path,
            "file_name": self.path.name,
            "source_label": source_label_for_relative_path(self.relative_path),
            "beams": list(self.beams),
        }
        if status is not None:
            payload.update(status)
        return payload


class ReprocessSession:
    def __init__(
        self,
        input_dir: str | Path | None = None,
        output_dir: str | Path | None = None,
    ) -> None:
        self.input_dir: Path | None = None
        self.output_dir: Path | None = None
        self.suggested_output_dir: Path | None = None
        self._sources: dict[str, ReprocessSource] = {}
        if input_dir is not None:
            self.configure(input_dir=input_dir, output_dir=output_dir)

    @property
    def configured(self) -> bool:
        return self.input_dir is not None

    def configure(
        self,
        input_dir: str | Path,
        output_dir: str | Path | None = None,
    ) -> dict[str, object]:
        root = Path(input_dir).expanduser().resolve()
        if not root.exists():
            raise FileNotFoundError(f"Input folder does not exist: {root}")
        if not root.is_dir():
            raise NotADirectoryError(f"Input path is not a folder: {root}")
        self.input_dir = root
        self.output_dir = (
            Path(output_dir).expanduser().resolve()
            if output_dir is not None
            else None
        )
        self.suggested_output_dir = root.with_name(f"{root.name}_labeled")
        self._sources = self._scan_sources(root)
        return self.manifest()

    def manifest(self) -> dict[str, object]:
        return {
            "mode": "reprocess",
            "configured": self.configured,
            "input_dir": (
                None if self.input_dir is None else str(self.input_dir)
            ),
            "output_dir": (
                None if self.output_dir is None else str(self.output_dir)
            ),
            "suggested_output_dir": (
                None
                if self.suggested_output_dir is None
                else str(self.suggested_output_dir)
            ),
            "source_count": len(self._sources),
        }

    def sources_payload(self) -> dict[str, object]:
        self._require_configured()
        sources = [
            self._source_payload(source)
            for source in sorted(
                self._sources.values(),
                key=lambda source: source.relative_path,
            )
        ]
        return {"count": len(sources), "sources": sources}

    def read_beam(
        self, source_relative_path: str, beam: str
    ) -> dict[str, object]:
        source = self._source(source_relative_path)
        with h5py.File(source.path, "r") as h5:
            group = self._beam_group(h5, source_relative_path, beam)
            photons = _read_all_photons(group)
            beam_payload = _beam_payload(source, beam, group, h5)
            labels, label_origin, manual_output_path = self._labels_for_beam(
                source, beam, photons, h5
            )
            return {
                "source": source.to_dict(self._status_for_source(source, h5)),
                "beam": beam_payload,
                "photons": photons.to_dict(),
                "labels": labels,
                "label_origin": label_origin,
                "manual_output_path": (
                    None
                    if manual_output_path is None
                    else str(manual_output_path)
                ),
            }

    def propose(
        self,
        source_relative_path: str,
        beam: str,
        seeds: list[dict[str, Any]],
    ) -> dict[str, object]:
        source = self._source(source_relative_path)
        with h5py.File(source.path, "r") as h5:
            group = self._beam_group(h5, source_relative_path, beam)
            photons = _read_all_photons(group)
            sc_orient = read_sc_orient(h5)
            result = generate_seeded_proposal(
                assigned=photons,
                context=photons,
                beam_strength=beam_strength(beam, sc_orient),
                seeds=seeds,
            )
        return {"rows": result.rows, "metadata": result.metadata}

    def reset_beam(
        self, source_relative_path: str, beam: str
    ) -> dict[str, object]:
        payload = self.read_beam(source_relative_path, beam)
        return {
            "rows": payload["labels"],
            "metadata": {"source": source_relative_path, "beam": beam},
        }

    def sample_dem(
        self,
        source_relative_path: str,
        beam: str,
        dem_path: str | Path,
    ) -> dict[str, object]:
        source = self._source(source_relative_path)
        with h5py.File(source.path, "r") as h5:
            group = self._beam_group(h5, source_relative_path, beam)
            photons = _read_all_photons(group)
        return {
            "source": source_relative_path,
            "beam": beam,
            "dem": sample_dem_along_track(
                dem_path=dem_path,
                lon=photons.lon,
                lat=photons.lat,
                x_atc_m=photons.x_atc_m,
            ),
        }

    def save_source(
        self,
        source_relative_path: str,
        beam_labels: dict[str, list[dict[str, Any]]],
    ) -> dict[str, object]:
        self._require_configured()
        if self.output_dir is None:
            raise ValueError("Output folder is required before saving")
        if not beam_labels:
            raise ValueError("At least one beam is required before saving")
        source = self._source(source_relative_path)
        prepared = self._prepared_beam_outputs(source, beam_labels)
        outputs: list[dict[str, str]] = []
        backups: list[dict[str, str]] = []
        for beam, class_values in prepared:
            output, backup = self._write_prepared_beam_output(
                self.output_dir, source, beam, class_values
            )
            outputs.append(output)
            if backup is not None:
                backups.append(backup)
        return {
            "source": source_relative_path,
            "outputs": outputs,
            "output_paths": [output["output_path"] for output in outputs],
            "backups": backups,
            "backup_paths": [backup["backup_path"] for backup in backups],
            "written_beams": sorted(beam_labels),
            "source_status": self._source_payload(source),
        }

    def _scan_sources(self, root: Path) -> dict[str, ReprocessSource]:
        sources: dict[str, ReprocessSource] = {}
        for path in sorted(
            root.rglob("*.h5"),
            key=lambda item: item.relative_to(root).as_posix(),
        ):
            if path.name.endswith("_manual.h5"):
                continue
            beams = _valid_beams(path)
            if not beams:
                continue
            relative_path = path.relative_to(root).as_posix()
            sources[relative_path] = ReprocessSource(
                path=path,
                relative_path=relative_path,
                beams=tuple(beams),
            )
        return sources

    def _source(self, source_relative_path: str) -> ReprocessSource:
        self._require_configured()
        source = self._sources.get(source_relative_path)
        if source is None:
            raise KeyError(f"Unknown source: {source_relative_path}")
        return source

    def _beam_group(
        self,
        h5: h5py.File,
        source_relative_path: str,
        beam: str,
    ) -> h5py.Group:
        if beam not in BEAM_NAMES or beam not in h5:
            raise KeyError(f"Unknown beam for {source_relative_path}: {beam}")
        group = h5[beam]
        missing = [name for name in REQUIRED_DATASETS if name not in group]
        if missing:
            raise ValueError(
                f"Missing datasets for {source_relative_path}/{beam}: "
                f"{', '.join(missing)}"
            )
        validate_beam_lengths(group)
        return group

    def _source_payload(self, source: ReprocessSource) -> dict[str, object]:
        with h5py.File(source.path, "r") as h5:
            return source.to_dict(self._status_for_source(source, h5))

    def _status_for_source(
        self, source: ReprocessSource, h5: h5py.File
    ) -> dict[str, object]:
        beam_statuses: dict[str, BeamOutputStatus] = {}
        for beam in source.beams:
            if self.output_dir is None:
                beam_statuses[beam] = "unclassified"
                continue
            output_path = _output_path(self.output_dir, source, beam, h5)
            if not output_path.exists():
                beam_statuses[beam] = "unclassified"
                continue
            group = self._beam_group(h5, source.relative_path, beam)
            expected_ids = _h5_photon_ids(
                *_h5_track_identity(source.path, beam, h5),
                int(group["x_atc"].shape[0]),
            )
            beam_statuses[beam] = (
                "complete" if output_is_valid(output_path, expected_ids) else "invalid"
            )
        completed = sum(
            status == "complete" for status in beam_statuses.values()
        )
        invalid = sum(status == "invalid" for status in beam_statuses.values())
        total = len(source.beams)
        status: FileOutputStatus
        if invalid > 0:
            status = "invalid"
        elif completed == 0:
            status = "unclassified"
        elif completed == total:
            status = "complete"
        else:
            status = "partial"
        return {
            "status": status,
            "beam_statuses": beam_statuses,
            "beam_count": total,
            "completed_beam_count": completed,
            "invalid_beam_count": invalid,
        }

    def _labels_for_beam(
        self,
        source: ReprocessSource,
        beam: str,
        photons: PhotonTable,
        h5: h5py.File,
    ) -> tuple[list[dict[str, int | str]], LabelOrigin, Path | None]:
        manual_path = (
            None
            if self.output_dir is None
            else _output_path(self.output_dir, source, beam, h5)
        )
        if manual_path is None or not manual_path.exists():
            return (
                labels_from_atl24_classes(
                    photons.source_row,
                    photons.atl24_class_ph,
                ),
                "atl24_original",
                None,
            )
        expected_ids = _h5_photon_ids(
            *_h5_track_identity(source.path, beam, h5), len(photons.source_row)
        )
        try:
            class_ph = read_manual_classes(manual_path, expected_ids)
        except (OSError, RuntimeError, ValueError) as exc:
            raise ValueError(
                f"Invalid classified GeoPackage: {manual_path}"
            ) from exc
        return (
            labels_from_atl24_classes(photons.source_row, class_ph),
            "manual_output",
            manual_path,
        )

    def _require_configured(self) -> None:
        if self.input_dir is None:
            raise RuntimeError("Reprocess session is not configured")

    def _prepared_beam_outputs(
        self,
        source: ReprocessSource,
        beam_labels: dict[str, list[dict[str, Any]]],
    ) -> list[tuple[str, np.ndarray]]:
        prepared: list[tuple[str, np.ndarray]] = []
        with h5py.File(source.path, "r") as h5:
            for beam in sorted(beam_labels):
                group = self._beam_group(h5, source.relative_path, beam)
                prepared.append(
                    (beam, _class_values_for_group(group, beam_labels[beam]))
                )
        return prepared

    def _write_prepared_beam_output(
        self,
        output_dir: Path,
        source: ReprocessSource,
        beam: str,
        class_values: np.ndarray,
    ) -> tuple[dict[str, str], dict[str, str] | None]:
        with h5py.File(source.path, "r") as h5:
            output_path = _output_path(output_dir, source, beam, h5)
            group = self._beam_group(h5, source.relative_path, beam)
            frame = _classified_h5_frame(
                source.path,
                beam,
                h5,
                group,
                class_values,
                time_labeled_utc=labeled_utc_now(),
            )
        backup_path = write_classified_geopackage(output_path, frame)
        output = {"beam": beam, "output_path": str(output_path)}
        backup = None
        if backup_path is not None:
            backup = {"beam": beam, "backup_path": str(backup_path)}
        return output, backup


def _output_path(
    output_dir: Path, source: ReprocessSource, beam: str, h5: h5py.File
) -> Path:
    date, rgt, cycle, spot = _h5_track_identity(source.path, beam, h5)
    filename = f"{date}_rgt{rgt:04d}_cycle{cycle:03d}_spot{spot}.gpkg"
    return output_dir / Path(source.relative_path).parent / filename


def source_label_for_relative_path(relative_path: str) -> str | None:
    parent = Path(relative_path).parent.as_posix()
    return None if parent == "." else parent.split("/", 1)[0]


def _valid_beams(path: Path) -> list[str]:
    try:
        with h5py.File(path, "r") as h5:
            if read_sc_orient(h5) == 2:
                return []
            beams = []
            for beam in BEAM_NAMES:
                if beam not in h5:
                    continue
                group = h5[beam]
                if not all(name in group for name in REQUIRED_DATASETS):
                    continue
                try:
                    validate_beam_lengths(group)
                except ValueError:
                    continue
                beams.append(beam)
            return beams
    except (OSError, ValueError):
        return []


def _read_all_photons(group: h5py.Group) -> PhotonTable:
    count = int(group["x_atc"].shape[0])
    return read_photon_rows(group, np.arange(count, dtype=np.int64))


def _classified_h5_frame(
    source_path: Path,
    beam: str,
    h5: h5py.File,
    group: h5py.Group,
    class_values: np.ndarray,
    *,
    time_labeled_utc: str,
) -> gpd.GeoDataFrame:
    count = int(group["x_atc"].shape[0])
    if class_values.shape != (count,):
        raise ValueError(
            f"class_manual length mismatch: expected {count}, "
            f"found {class_values.shape}"
        )
    if "class_ph" not in group:
        raise ValueError(
            f"ATL24 source beam has no class_ph: {source_path}/{beam}"
        )
    data: dict[str, object] = {}
    for name, item in group.items():
        if not isinstance(item, h5py.Dataset) or item.shape != (count,):
            continue
        data[name] = np.asarray(item[:])
    data["beam"] = np.full(count, beam, dtype=object)
    source = gpd.GeoDataFrame(
        data,
        geometry=gpd.points_from_xy(data["lon_ph"], data["lat_ph"]),
        crs="EPSG:4326",
    )
    date, rgt, cycle, spot = _h5_track_identity(source_path, beam, h5)
    return build_classified_frame(
        source,
        acquisition_dates=[date] * count,
        track_indices=list(range(count)),
        rgt=rgt,
        cycle=cycle,
        spot=spot,
        class_manual=class_values.tolist(),
        time_labeled_utc=time_labeled_utc,
    )


def _h5_track_identity(
    source_path: Path,
    beam: str,
    h5: h5py.File,
) -> tuple[str, int, int, int]:
    match = re.match(r"^ATL24_(\d{8})\d{6}_", source_path.name)
    if match is None:
        raise ValueError(
            "ATL24 H5 filename must preserve its acquisition timestamp: "
            f"{source_path.name}"
        )
    try:
        rgt = int(h5.attrs["rgt"])
        cycle = int(h5.attrs["cycle"])
    except (KeyError, TypeError, ValueError, OverflowError) as exc:
        raise ValueError(
            f"ATL24 H5 requires integer root rgt and cycle attributes: {source_path}"
        ) from exc
    return match.group(1), rgt, cycle, _spot_number(beam, read_sc_orient(h5))


def _spot_number(beam: str, sc_orient: int) -> int:
    backward = {
        "gt1l": 1,
        "gt1r": 2,
        "gt2l": 3,
        "gt2r": 4,
        "gt3l": 5,
        "gt3r": 6,
    }
    forward = {
        "gt3r": 1,
        "gt3l": 2,
        "gt2r": 3,
        "gt2l": 4,
        "gt1r": 5,
        "gt1l": 6,
    }
    if sc_orient == 0:
        return backward[beam]
    if sc_orient == 1:
        return forward[beam]
    raise ValueError(f"Unsupported spacecraft orientation: {sc_orient}")


def _h5_photon_ids(
    date: str,
    rgt: int,
    cycle: int,
    spot: int,
    count: int,
) -> list[str]:
    return [
        canonical_photon_id(date, rgt, cycle, spot, index)
        for index in range(count)
    ]


def _beam_payload(
    source: ReprocessSource,
    beam: str,
    group: h5py.Group,
    h5: h5py.File,
) -> dict[str, object]:
    x_atc = np.asarray(group["x_atc"][:], dtype=float)
    night_flag = np.asarray(group["night_flag"][:], dtype=np.int8)
    photon_count = int(x_atc.size)
    day_night = (
        "night"
        if int(np.count_nonzero(night_flag)) >= photon_count / 2
        else "day"
    )
    finite_x = x_atc[np.isfinite(x_atc)]
    x_start = float(np.nanmin(finite_x)) if finite_x.size else 0.0
    x_end = float(np.nanmax(finite_x)) if finite_x.size else 0.0
    return {
        "source_relative_path": source.relative_path,
        "file_name": source.path.name,
        "beam": beam,
        "photon_count": photon_count,
        "day_night": day_night,
        "beam_strength": beam_strength(beam, read_sc_orient(h5)),
        "x_atc_start_m": x_start,
        "x_atc_end_m": x_end,
    }


def _class_values_for_group(
    group: h5py.Group,
    labels: list[dict[str, Any]],
) -> np.ndarray:
    count = int(group["x_atc"].shape[0])
    if len(labels) != count:
        raise ValueError(
            f"A complete beam must contain exactly {count} label rows; "
            f"found {len(labels)}"
        )
    if "class_ph" in group:
        values = np.asarray(group["class_ph"][:]).astype(np.int16)
    else:
        values = np.zeros(count, dtype=np.int16)
    seen_rows: set[int] = set()
    for row in labels:
        source_row = int(row["source_row"])
        if source_row < 0 or source_row >= count:
            raise ValueError(f"source_row out of bounds: {source_row}")
        if source_row in seen_rows:
            raise ValueError(f"Duplicate label row for source_row {source_row}")
        seen_rows.add(source_row)
        label = str(row["label"])
        if label not in LABEL_TO_CLASS_PH:
            raise ValueError(f"Invalid label: {label}")
        values[source_row] = LABEL_TO_CLASS_PH[label]  # type: ignore[index]
    return values.astype(np.int16)
