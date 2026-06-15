from __future__ import annotations

import shutil
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Literal

import h5py
import numpy as np

from bathy_labeler.backend.dem import sample_dem_along_track
from bathy_labeler.backend.hdf5_store import (
    _beam_strength,
    _read_photon_rows,
    _read_sc_orient,
    _validate_beam_lengths,
)
from bathy_labeler.backend.models import (
    BEAM_NAMES,
    REQUIRED_DATASETS,
    FinalLabel,
    PhotonTable,
)
from bathy_labeler.backend.proposals import generate_seeded_proposal

LABEL_TO_CLASS_PH: dict[FinalLabel, int] = {
    "surface": 41,
    "bathy": 40,
    "no_label": 0,
}

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
                source, beam, photons
            )
            return {
                "source": self._source_payload(source),
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
            sc_orient = _read_sc_orient(h5)
            result = generate_seeded_proposal(
                assigned=photons,
                context=photons,
                beam_strength=_beam_strength(beam, sc_orient),
                seeds=seeds,
                residual_label="no_label",
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
                source=source,
                source_relative_path=source_relative_path,
                beam=beam,
                class_values=class_values,
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

    def source_status(self, source_relative_path: str) -> dict[str, object]:
        source = self._source(source_relative_path)
        return self._source_payload(source)

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
        _validate_beam_lengths(group)
        return group

    def _output_path(self, source_relative_path: str, beam: str) -> Path:
        if self.output_dir is None:
            raise ValueError("Output folder is required before saving")
        relative = Path(source_relative_path)
        return (
            self.output_dir
            / relative.parent
            / f"{relative.stem}_{beam}_manual.h5"
        )

    def _manual_output_path(
        self, source_relative_path: str, beam: str
    ) -> Path | None:
        if self.output_dir is None:
            return None
        relative = Path(source_relative_path)
        return (
            self.output_dir
            / relative.parent
            / f"{relative.stem}_{beam}_manual.h5"
        )

    def _source_payload(self, source: ReprocessSource) -> dict[str, object]:
        return source.to_dict(self._status_for_source(source))

    def _status_for_source(self, source: ReprocessSource) -> dict[str, object]:
        beam_statuses: dict[str, BeamOutputStatus] = {}
        with h5py.File(source.path, "r") as h5:
            for beam in source.beams:
                output_path = self._manual_output_path(
                    source.relative_path, beam
                )
                if output_path is None or not output_path.exists():
                    beam_statuses[beam] = "unclassified"
                    continue
                group = self._beam_group(h5, source.relative_path, beam)
                expected_count = int(group["x_atc"].shape[0])
                is_valid = _manual_output_has_valid_class_ph(
                    output_path,
                    source.relative_path,
                    beam,
                    expected_count,
                )
                if not is_valid:
                    beam_statuses[beam] = "invalid"
                else:
                    beam_statuses[beam] = "complete"
        completed = sum(
            status == "complete" for status in beam_statuses.values()
        )
        invalid = sum(status == "invalid" for status in beam_statuses.values())
        total = len(source.beams)
        if invalid > 0:
            status: FileOutputStatus = "invalid"
        elif completed == 0:
            status: FileOutputStatus = "unclassified"
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
    ) -> tuple[list[dict[str, int | str]], LabelOrigin, Path | None]:
        manual_path = self._manual_output_path(source.relative_path, beam)
        if manual_path is None or not manual_path.exists():
            return (
                labels_from_atl24_classes(
                    photons.source_row,
                    photons.atl24_class_ph,
                ),
                "atl24_original",
                None,
            )
        class_ph = _read_manual_class_ph(
            manual_path,
            source.relative_path,
            beam,
            expected_count=len(photons.source_row),
        )
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
        source: ReprocessSource,
        source_relative_path: str,
        beam: str,
        class_values: np.ndarray,
    ) -> tuple[dict[str, str], dict[str, str] | None]:
        output_path = self._output_path(source_relative_path, beam)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        backup_path = self._backup_existing_output(
            output_path, source_relative_path, beam
        )
        tmp_path = _temporary_output_path(output_path)
        try:
            shutil.copy2(source.path, tmp_path)
            _write_beam_class_values(
                tmp_path=tmp_path,
                source_relative_path=source_relative_path,
                beam=beam,
                class_values=class_values,
                beam_group=self._beam_group,
            )
            tmp_path.replace(output_path)
        except Exception:
            if tmp_path.exists():
                tmp_path.unlink()
            raise
        output = {"beam": beam, "output_path": str(output_path)}
        backup = None
        if backup_path is not None:
            backup = {"beam": beam, "backup_path": str(backup_path)}
        return output, backup

    def _backup_existing_output(
        self,
        output_path: Path,
        source_relative_path: str,
        beam: str,
    ) -> Path | None:
        if not output_path.exists():
            return None
        backup_path = self._backup_path(output_path, source_relative_path, beam)
        backup_path.parent.mkdir(parents=True, exist_ok=False)
        shutil.copy2(output_path, backup_path)
        return backup_path

    def _backup_path(
        self,
        output_path: Path,
        source_relative_path: str,
        beam: str,
    ) -> Path:
        if self.output_dir is None:
            raise ValueError("Output folder is required before saving")
        relative = Path(source_relative_path)
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        return (
            self.output_dir
            / ".bathy_labeler_backups"
            / relative.parent
            / f"{relative.stem}_{beam}_manual"
            / timestamp
            / output_path.name
        )


def source_label_for_relative_path(relative_path: str) -> str | None:
    parent = Path(relative_path).parent.as_posix()
    return None if parent == "." else parent.split("/", 1)[0]


def labels_from_atl24_classes(
    source_rows: list[int],
    atl24_class_ph: list[int | None],
) -> list[dict[str, int | str]]:
    return [
        {
            "source_row": int(source_row),
            "label": label_from_class_ph(class_ph),
            "label_source": "auto",
        }
        for source_row, class_ph in zip(source_rows, atl24_class_ph)
    ]


def label_from_class_ph(class_ph: int | None) -> FinalLabel:
    if class_ph == 41:
        return "surface"
    if class_ph == 40:
        return "bathy"
    return "no_label"


def _read_manual_class_ph(
    manual_path: Path,
    source_relative_path: str,
    beam: str,
    expected_count: int,
) -> list[int | None]:
    source_beam = f"{source_relative_path}/{beam}"
    try:
        with h5py.File(manual_path, "r") as h5:
            if beam not in h5:
                message = (
                    "Manual output missing beam for "
                    f"{source_beam}: {manual_path}"
                )
                raise ValueError(message)
            group = h5[beam]
            if "class_ph" not in group:
                raise ValueError(
                    f"Manual output missing class_ph for "
                    f"{source_beam}: {manual_path}"
                )
            class_ph = np.asarray(group["class_ph"][:])
    except OSError as exc:
        raise ValueError(
            f"Manual output is unreadable for {source_beam}: " f"{manual_path}"
        ) from exc
    if int(class_ph.shape[0]) != expected_count:
        raise ValueError(
            f"Manual output class_ph length mismatch for {source_beam}: "
            f"expected {expected_count}, found {int(class_ph.shape[0])}"
        )
    return [
        None if np.ma.is_masked(value) else int(value) for value in class_ph
    ]


def _manual_output_has_valid_class_ph(
    manual_path: Path,
    source_relative_path: str,
    beam: str,
    expected_count: int,
) -> bool:
    try:
        with h5py.File(manual_path, "r") as h5:
            if beam not in h5:
                return False
            group = h5[beam]
            if "class_ph" not in group:
                return False
            dataset = group["class_ph"]
            return dataset.shape == (expected_count,)
    except OSError:
        return False


def _valid_beams(path: Path) -> list[str]:
    try:
        with h5py.File(path, "r") as h5:
            if _read_sc_orient(h5) == 2:
                return []
            beams = []
            for beam in BEAM_NAMES:
                if beam not in h5:
                    continue
                group = h5[beam]
                if all(name in group for name in REQUIRED_DATASETS):
                    _validate_beam_lengths(group)
                    beams.append(beam)
            return beams
    except (OSError, ValueError):
        return []


def _read_all_photons(group: h5py.Group) -> PhotonTable:
    count = int(group["x_atc"].shape[0])
    return _read_photon_rows(group, np.arange(count, dtype=np.int64))


def _temporary_output_path(output_path: Path) -> Path:
    return output_path.with_name(f".{output_path.name}.{uuid.uuid4().hex}.tmp")


def _write_beam_class_values(
    tmp_path: Path,
    source_relative_path: str,
    beam: str,
    class_values: np.ndarray,
    beam_group: Callable[[h5py.File, str, str], h5py.Group],
) -> None:
    with h5py.File(tmp_path, "r+") as h5:
        group = beam_group(h5, source_relative_path, beam)
        photon_count = int(group["x_atc"].shape[0])
        if int(class_values.shape[0]) != photon_count:
            raise ValueError(
                f"class_ph length mismatch for {source_relative_path}/{beam}: "
                f"expected {photon_count}, found {int(class_values.shape[0])}"
            )
        if "class_ph" not in group:
            group.create_dataset("class_ph", data=class_values)
        elif group["class_ph"].shape != class_values.shape:
            del group["class_ph"]
            group.create_dataset("class_ph", data=class_values)
        else:
            group["class_ph"][:] = class_values
        _set_manual_confidence_values(group)
        _set_cleaner_metadata(h5, group, source_relative_path, beam)


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
        "beam_strength": _beam_strength(beam, _read_sc_orient(h5)),
        "x_atc_start_m": x_start,
        "x_atc_end_m": x_end,
    }


def _class_values_for_group(
    group: h5py.Group,
    labels: list[dict[str, Any]],
) -> np.ndarray:
    count = int(group["x_atc"].shape[0])
    if "class_ph" in group:
        values = np.asarray(group["class_ph"][:]).astype(np.int16)
    else:
        values = np.zeros(count, dtype=np.int16)
    for row in labels:
        source_row = int(row["source_row"])
        if source_row < 0 or source_row >= count:
            raise ValueError(f"source_row out of bounds: {source_row}")
        label = str(row["label"])
        if label not in LABEL_TO_CLASS_PH:
            raise ValueError(f"Invalid label: {label}")
        values[source_row] = LABEL_TO_CLASS_PH[label]  # type: ignore[index]
    return values.astype(np.int16)


def _set_manual_confidence_values(group: h5py.Group) -> None:
    _set_existing_dataset_constant(group, "confidence", 1)
    _set_existing_dataset_constant(group, "low_confidence_flag", 0)


def _set_cleaner_metadata(
    h5: h5py.File,
    group: h5py.Group,
    source_relative_path: str,
    beam: str,
) -> None:
    now = datetime.now(timezone.utc).isoformat()
    h5.attrs["bathy_labeler_tool"] = "ATL24 Bathymetry Cleaner"
    h5.attrs["bathy_labeler_source"] = source_relative_path
    h5.attrs["bathy_labeler_updated_utc"] = now
    group.attrs["bathy_labeler_cleaned_beam"] = beam
    group.attrs["bathy_labeler_updated_utc"] = now


def _set_existing_dataset_constant(
    group: h5py.Group,
    dataset_name: str,
    value: int,
) -> None:
    if dataset_name not in group:
        return
    dataset = group[dataset_name]
    photon_count = int(group["x_atc"].shape[0])
    if dataset.shape and int(dataset.shape[0]) != photon_count:
        raise ValueError(
            f"{dataset_name} length mismatch for beam {group.name}: "
            f"expected {photon_count}, found {int(dataset.shape[0])}"
        )
    dataset[...] = np.full(dataset.shape, value, dtype=dataset.dtype)
