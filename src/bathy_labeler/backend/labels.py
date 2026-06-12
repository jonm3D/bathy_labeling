from __future__ import annotations

import csv
import hashlib
import json
import shutil
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from bathy_labeler.backend.models import (
    FINAL_LABELS,
    LABEL_SOURCES,
    FinalLabel,
    LabelSource,
    PhotonTable,
    SegmentStatus,
    SegmentSummary,
)

CSV_FIELDS = ("source_row", "index_ph", "lat", "lon", "ortho_h_m", "label", "label_source")
SCHEMA_VERSION = "labels-v1"


class LabelValidationError(ValueError):
    pass


@dataclass(frozen=True)
class LabelSidecar:
    segment_id: str
    csv_path: Path
    metadata_path: Path
    status: SegmentStatus
    rows: list[dict[str, Any]]
    metadata: dict[str, Any]


class LabelSidecarStore:
    def __init__(self, project_root: str | Path) -> None:
        self.project_root = Path(project_root)
        self.labels_dir = self.project_root / "labels"
        self.archive_dir = self.labels_dir / "archive"

    def csv_path(self, segment_id: str) -> Path:
        return self.labels_dir / f"{segment_id}.labels.csv"

    def metadata_path(self, segment_id: str) -> Path:
        return self.labels_dir / f"{segment_id}.labels.json"

    def load(self, segment_id: str) -> LabelSidecar | None:
        csv_path = self.csv_path(segment_id)
        metadata_path = self.metadata_path(segment_id)
        if not csv_path.exists() and not metadata_path.exists():
            return None
        if not csv_path.exists() or not metadata_path.exists():
            return LabelSidecar(segment_id, csv_path, metadata_path, "draft", [], {})
        try:
            rows = _read_csv_rows(csv_path)
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, csv.Error):
            return LabelSidecar(segment_id, csv_path, metadata_path, "draft", [], {})
        status = "complete" if metadata.get("status") == "complete" else "draft"
        return LabelSidecar(segment_id, csv_path, metadata_path, status, rows, metadata)

    def status_for(self, segment: SegmentSummary, photons: PhotonTable) -> SegmentStatus:
        sidecar = self.load(segment.segment_id)
        if sidecar is None:
            return "unlabeled"
        if sidecar.status != "complete":
            return "draft"
        if sidecar.metadata.get("segment_id") != segment.segment_id:
            return "stale"
        if sidecar.metadata.get("stable_source_file_id") != segment.stable_source_file_id:
            return "stale"
        if sidecar.metadata.get("beam") != segment.beam:
            return "stale"
        if int(sidecar.metadata.get("row_key_count", -1)) != photons.count:
            return "stale"
        if sidecar.metadata.get("row_key_checksum") != row_key_checksum(photons):
            return "stale"
        if len(sidecar.rows) != photons.count:
            return "stale"
        return "complete"

    def save(
        self,
        segment: SegmentSummary,
        photons: PhotonTable,
        labels: list[dict[str, Any]],
    ) -> LabelSidecar:
        rows = _build_csv_rows(photons, labels)
        metadata = _metadata_for(segment, photons, rows, previous=self.load(segment.segment_id))

        self.labels_dir.mkdir(parents=True, exist_ok=True)
        csv_path = self.csv_path(segment.segment_id)
        metadata_path = self.metadata_path(segment.segment_id)
        if csv_path.exists() or metadata_path.exists():
            self._archive_current(segment.segment_id, csv_path, metadata_path)

        tmp_csv = csv_path.with_suffix(".csv.tmp")
        tmp_json = metadata_path.with_suffix(".json.tmp")
        _write_csv_rows(tmp_csv, rows)
        tmp_json.write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        tmp_csv.replace(csv_path)
        tmp_json.replace(metadata_path)
        return LabelSidecar(segment.segment_id, csv_path, metadata_path, "complete", rows, metadata)

    def _archive_current(self, segment_id: str, csv_path: Path, metadata_path: Path) -> None:
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        target = self.archive_dir / segment_id / timestamp
        target.mkdir(parents=True, exist_ok=False)
        if csv_path.exists():
            shutil.copy2(csv_path, target / "labels.csv")
        if metadata_path.exists():
            shutil.copy2(metadata_path, target / "labels.json")


def row_key_checksum(photons: PhotonTable) -> str:
    digest = hashlib.sha256()
    for source_row, index_ph in zip(photons.source_row, photons.index_ph, strict=True):
        digest.update(f"{int(source_row)}:{int(index_ph)}\n".encode("utf-8"))
    return digest.hexdigest()


def _build_csv_rows(photons: PhotonTable, labels: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if len(labels) != photons.count:
        raise LabelValidationError("A complete sidecar must contain exactly one row for every segment photon.")
    label_by_row: dict[int, dict[str, Any]] = {}
    for label_row in labels:
        source_row = int(label_row["source_row"])
        if source_row in label_by_row:
            raise LabelValidationError(f"Duplicate label row for source_row {source_row}.")
        label = str(label_row["label"])
        label_source = str(label_row["label_source"])
        if label not in FINAL_LABELS:
            raise LabelValidationError(f"Invalid label: {label}")
        if label_source not in LABEL_SOURCES:
            raise LabelValidationError(f"Invalid label_source: {label_source}")
        label_by_row[source_row] = {"label": label, "label_source": label_source}

    expected_rows = set(photons.source_row)
    if set(label_by_row) != expected_rows:
        raise LabelValidationError("A complete sidecar must contain exactly one row for every segment photon.")

    rows: list[dict[str, Any]] = []
    for index in sorted(range(photons.count), key=lambda item: photons.source_row[item]):
        source_row = int(photons.source_row[index])
        label_record = label_by_row[source_row]
        rows.append(
            {
                "source_row": source_row,
                "index_ph": int(photons.index_ph[index]),
                "lat": float(photons.lat[index]),
                "lon": float(photons.lon[index]),
                "ortho_h_m": float(photons.ortho_h_m[index]),
                "label": label_record["label"],
                "label_source": label_record["label_source"],
            }
        )
    return rows


def _metadata_for(
    segment: SegmentSummary,
    photons: PhotonTable,
    rows: list[dict[str, Any]],
    previous: LabelSidecar | None,
) -> dict[str, Any]:
    now = datetime.now(timezone.utc).isoformat()
    label_counts = Counter(str(row["label"]) for row in rows)
    source_counts = Counter(str(row["label_source"]) for row in rows)
    created = now
    if previous is not None and previous.metadata.get("created"):
        created = str(previous.metadata["created"])
    return {
        "schema_version": SCHEMA_VERSION,
        "segment_id": segment.segment_id,
        "stable_source_file_id": segment.stable_source_file_id,
        "source_relative_path": segment.source_relative_path,
        "source_label": segment.source_label,
        "beam": segment.beam,
        "x_atc_start_m": segment.x_atc_start_m,
        "x_atc_end_m": segment.x_atc_end_m,
        "context_x_atc_start_m": segment.context_x_atc_start_m,
        "context_x_atc_end_m": segment.context_x_atc_end_m,
        "segment_photon_count": photons.count,
        "row_key_count": photons.count,
        "row_key_checksum": row_key_checksum(photons),
        "row_sort": "source_row",
        "final_label_counts": dict(sorted(label_counts.items())),
        "manual_count": int(source_counts.get("manual", 0)),
        "auto_count": int(source_counts.get("auto", 0)),
        "created": created,
        "updated": now,
        "status": "complete",
    }


def _read_csv_rows(path: Path) -> list[dict[str, Any]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _write_csv_rows(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
