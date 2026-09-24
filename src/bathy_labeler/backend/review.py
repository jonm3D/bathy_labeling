from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import geopandas as gpd
import numpy as np
import pandas as pd
from pyproj import Geod
from shapely.geometry import mapping

from bathy_labeler.backend.classified_output import (
    build_classified_frame,
    canonical_photon_id,
    labeled_utc_now,
    read_manual_classes,
    write_classified_geopackage,
)
from bathy_labeler.backend.models import (
    FINAL_LABELS,
    LABEL_SOURCES,
    LABEL_TO_CLASS_PH,
    PhotonTable,
    label_from_class_ph,
    labels_from_atl24_classes,
)

BASE_REQUIRED_COLUMNS = {
    "geometry",
    "x_atc",
    "rgt",
    "cycle",
    "spot",
}

PRODUCT_REQUIRED_COLUMNS = {
    "atl24": {"ortho_h", "surface_h", "night_flag", "class_ph"},
    "atl03": {
        "height",
        "geoid",
        "geoid_free2mean",
    },
}

WGS84_GEOD = Geod(ellps="WGS84")


@dataclass(frozen=True)
class ReviewTrack:
    key: str
    rgt: int
    cycle: int
    spot: int
    closest_distance_m: float | None
    assigned_rows: tuple[int, ...]
    context_rows: tuple[int, ...]


@dataclass(frozen=True)
class ReviewSource:
    source_id: str
    name: str
    parquet_path: Path
    aoi_path: Path
    product: str
    source_label: str
    height_axis_label: str
    tracks: tuple[ReviewTrack, ...]
    aoi_geometry: dict[str, Any]
    site_marker: dict[str, float | str] | None
    review_note: str | None
    priority_tracks: tuple[str, ...]
    track_notes: dict[str, str]


class SlideRuleReviewSession:
    """Review and annotate SlideRule photon GeoParquet inside supplied AOIs."""

    def __init__(self, config_path: str | Path) -> None:
        self.config_path = Path(config_path).expanduser().resolve()
        if not self.config_path.exists():
            raise FileNotFoundError(f"Review config does not exist: {self.config_path}")
        config = json.loads(self.config_path.read_text())
        self.context_margin_m = float(config.get("context_margin_m", 1000.0))
        if self.context_margin_m < 0:
            raise ValueError("context_margin_m must be non-negative")
        sites = config.get("sites")
        if not isinstance(sites, list) or not sites:
            raise ValueError("Review config requires a non-empty sites list")
        self.output_dir = self._resolve_path(config["output_dir"])

        self._frames: dict[str, gpd.GeoDataFrame] = {}
        self._sources: dict[str, ReviewSource] = {}
        for site in sites:
            source = self._load_source(site)
            if source.source_id in self._sources:
                raise ValueError(f"Duplicate review site id: {source.source_id}")
            self._sources[source.source_id] = source

    def manifest(self) -> dict[str, object]:
        products = {source.product for source in self._sources.values()}
        return {
            "mode": "review",
            "configured": True,
            "review_config": str(self.config_path),
            "context_margin_m": self.context_margin_m,
            "output_dir": str(self.output_dir),
            "source_count": len(self._sources),
            "source_product": (next(iter(products)) if len(products) == 1 else "mixed"),
        }

    def sources_payload(self) -> dict[str, object]:
        sources = [self._source_payload(source) for source in self._sources.values()]
        return {"count": len(sources), "sources": sources}

    def read_track(self, source_id: str, track_key: str) -> dict[str, object]:
        source = self._source(source_id)
        track = next(
            (candidate for candidate in source.tracks if candidate.key == track_key),
            None,
        )
        if track is None:
            raise KeyError(f"Unknown track for {source_id}: {track_key}")

        frame = self._frames[source_id]
        assigned = _photon_table(frame, track.assigned_rows)
        context = _photon_table(frame, track.context_rows)
        x_assigned = np.asarray(assigned.x_atc_m, dtype=float)
        x_context = np.asarray(context.x_atc_m, dtype=float)
        night = np.asarray(assigned.night_flag, dtype=np.int8)
        day_night = (
            "night"
            if night.size and int(np.count_nonzero(night)) >= night.size / 2
            else "day"
        )
        beam = {
            "source_relative_path": source.source_id,
            "file_name": source.name,
            "beam": track.key,
            "rgt": track.rgt,
            "cycle": track.cycle,
            "spot": track.spot,
            "photon_count": assigned.count,
            "context_photon_count": context.count,
            "day_night": day_night,
            "beam_strength": "strong" if track.spot % 2 == 1 else "weak",
            "x_atc_start_m": float(np.min(x_assigned)),
            "x_atc_end_m": float(np.max(x_assigned)),
            "context_x_atc_start_m": float(np.min(x_context)),
            "context_x_atc_end_m": float(np.max(x_context)),
        }
        labels, label_origin, annotation_path = self._labels_for_track(
            source, track, assigned
        )
        return {
            "source": self._source_payload(source),
            "beam": beam,
            "assigned": assigned.to_dict(),
            "context": context.to_dict(),
            "labels": labels,
            "label_origin": label_origin,
            "manual_output_path": (
                None if annotation_path is None else str(annotation_path)
            ),
            "aoi_geometry": source.aoi_geometry,
            "site_marker": source.site_marker,
        }

    def save_track(
        self,
        source_id: str,
        track_key: str,
        labels: list[dict[str, Any]],
    ) -> dict[str, object]:
        source = self._source(source_id)
        track = next(
            (candidate for candidate in source.tracks if candidate.key == track_key),
            None,
        )
        if track is None:
            raise KeyError(f"Unknown track for {source_id}: {track_key}")
        validated = _validate_annotation_rows(labels, track.assigned_rows)
        output_path = self._output_path(source, track)
        output_frame = self._classified_frame(
            source,
            track,
            validated,
            time_labeled_utc=labeled_utc_now(),
        )
        backup_path = write_classified_geopackage(output_path, output_frame)
        return {
            "status": "saved",
            "source": source.source_id,
            "track": track.key,
            "output_path": str(output_path),
            "backup_path": (None if backup_path is None else str(backup_path)),
            "labels": validated,
            "source_status": self._source_payload(source),
        }

    def _load_source(self, site: Any) -> ReviewSource:
        if not isinstance(site, dict):
            raise ValueError("Each review site must be an object")
        name = str(site["name"])
        source_id = str(site.get("id") or _slug(name))
        product = str(site.get("product", "atl24")).lower()
        if product not in PRODUCT_REQUIRED_COLUMNS:
            raise ValueError("SlideRule review product must be atl03 or atl24")
        parquet_path = self._resolve_path(site["parquet"])
        aoi_path = self._resolve_path(site["aoi"])
        for path in (parquet_path, aoi_path):
            if not path.exists():
                raise FileNotFoundError(f"Review input does not exist: {path}")

        frame = gpd.read_parquet(parquet_path)
        if frame.index.name != "time_ns":
            raise ValueError(
                f"SlideRule GeoParquet requires a time_ns index: {parquet_path}"
            )
        frame = frame.reset_index()
        required = BASE_REQUIRED_COLUMNS | PRODUCT_REQUIRED_COLUMNS[product]
        missing = sorted(required - set(frame.columns))
        if missing:
            raise ValueError(
                f"Missing SlideRule fields in {parquet_path.name}: "
                f"{', '.join(missing)}"
            )
        if frame.crs is None:
            raise ValueError(f"SlideRule GeoParquet has no CRS: {parquet_path}")
        frame["_source_row"] = np.arange(len(frame), dtype=np.int64)
        ordered = frame.sort_values(["rgt", "cycle", "spot", "time_ns", "_source_row"])
        ordered_indices = ordered.groupby(
            ["rgt", "cycle", "spot"], sort=False
        ).cumcount()
        frame["_track_index"] = np.zeros(len(frame), dtype=np.int64)
        frame.loc[ordered.index, "_track_index"] = ordered_indices.to_numpy(
            dtype=np.int64
        )
        if product == "atl24":
            frame["_review_height"] = pd.to_numeric(frame["ortho_h"], errors="coerce")
            frame["_review_surface_h"] = pd.to_numeric(
                frame["surface_h"], errors="coerce"
            )
            frame["_review_night"] = frame["night_flag"]
            frame["_review_class_ph"] = frame["class_ph"]
            default_source_label = "SlideRule ATL24"
            default_height_axis_label = "ortho_h (m)"
        else:
            frame["_review_height"] = (
                pd.to_numeric(frame["height"], errors="coerce")
                - pd.to_numeric(frame["geoid"], errors="coerce")
                - pd.to_numeric(frame["geoid_free2mean"], errors="coerce")
            )
            frame["_review_surface_h"] = np.nan
            if "night_flag" in frame:
                frame["_review_night"] = frame["night_flag"]
            elif "solar_elevation" in frame:
                solar_elevation = pd.to_numeric(
                    frame["solar_elevation"], errors="coerce"
                )
                frame["_review_night"] = (solar_elevation < 0).astype(np.int8)
            else:
                frame["_review_night"] = np.zeros(len(frame), dtype=np.int8)
            frame["_review_class_ph"] = pd.Series(
                pd.NA, index=frame.index, dtype="Int16"
            )
            default_source_label = "SlideRule ATL03"
            default_height_axis_label = "ortho_h (m, EGM2008 mean tide)"
        source_label = str(site.get("source_label", default_source_label))
        height_axis_label = str(
            site.get("height_axis_label", default_height_axis_label)
        )
        site_marker = _site_marker(site.get("site_marker"))
        review_note = _optional_note(site.get("review_note"), "review_note")
        priority_tracks = _track_key_list(site.get("priority_tracks", []))
        track_notes = _track_note_mapping(site.get("track_notes", {}))
        geographic = frame.to_crs("EPSG:4326")
        frame["_review_lon"] = geographic.geometry.x
        frame["_review_lat"] = geographic.geometry.y

        aoi = gpd.read_file(aoi_path)
        if aoi.empty:
            raise ValueError(f"AOI contains no geometry: {aoi_path}")
        if aoi.crs is None:
            raise ValueError(f"AOI has no CRS: {aoi_path}")
        aoi_in_data_crs = aoi.to_crs(frame.crs).geometry.union_all()
        aoi_wgs84 = aoi.to_crs("EPSG:4326").geometry.union_all()
        inside = frame.geometry.intersects(aoi_in_data_crs)
        tracks = self._build_tracks(frame, inside, site_marker)
        available_tracks = {track.key for track in tracks}
        unknown_priorities = sorted(set(priority_tracks) - available_tracks)
        unknown_notes = sorted(set(track_notes) - available_tracks)
        if unknown_priorities or unknown_notes:
            unknown = ", ".join(unknown_priorities + unknown_notes)
            raise ValueError(f"Review notes reference unknown tracks for {source_id}: {unknown}")
        self._frames[source_id] = frame
        return ReviewSource(
            source_id=source_id,
            name=name,
            parquet_path=parquet_path,
            aoi_path=aoi_path,
            product=product,
            source_label=source_label,
            height_axis_label=height_axis_label,
            tracks=tracks,
            aoi_geometry=mapping(aoi_wgs84),
            site_marker=site_marker,
            review_note=review_note,
            priority_tracks=priority_tracks,
            track_notes=track_notes,
        )

    def _build_tracks(
        self,
        frame: gpd.GeoDataFrame,
        inside: pd.Series,
        site_marker: dict[str, float | str] | None,
    ) -> tuple[ReviewTrack, ...]:
        assigned = frame.loc[inside].copy()
        assigned = assigned.dropna(subset=["rgt", "cycle", "spot", "x_atc"])
        tracks: list[ReviewTrack] = []
        for group_key, assigned_group in assigned.groupby(
            ["rgt", "cycle", "spot"], sort=True
        ):
            rgt, cycle, spot = (int(value) for value in group_key)
            x_inside = pd.to_numeric(assigned_group["x_atc"], errors="coerce")
            x_inside = x_inside[np.isfinite(x_inside)]
            if x_inside.empty:
                continue
            same_track = (
                (frame["rgt"] == rgt)
                & (frame["cycle"] == cycle)
                & (frame["spot"] == spot)
            )
            x_all = pd.to_numeric(frame["x_atc"], errors="coerce")
            context = frame.loc[
                same_track
                & x_all.between(
                    float(x_inside.min()) - self.context_margin_m,
                    float(x_inside.max()) + self.context_margin_m,
                    inclusive="both",
                )
            ]
            assigned_rows = tuple(
                int(value)
                for value in assigned_group.sort_values("x_atc")["_source_row"]
            )
            context_rows = tuple(
                int(value) for value in context.sort_values("x_atc")["_source_row"]
            )
            tracks.append(
                ReviewTrack(
                    key=_track_key(rgt, cycle, spot),
                    rgt=rgt,
                    cycle=cycle,
                    spot=spot,
                    closest_distance_m=_closest_distance_m(
                        assigned_group, site_marker
                    ),
                    assigned_rows=assigned_rows,
                    context_rows=context_rows,
                )
            )
        return tuple(tracks)

    def _source_payload(self, source: ReviewSource) -> dict[str, object]:
        priority_index = {
            track_key: index for index, track_key in enumerate(source.priority_tracks)
        }
        ordered_tracks = sorted(
            source.tracks,
            key=lambda track: (
                0 if track.key in priority_index else 1,
                priority_index.get(track.key, float("inf")),
                (
                    float("inf")
                    if track.closest_distance_m is None
                    else track.closest_distance_m
                ),
                track.key,
            ),
        )
        assigned_count = sum(len(track.assigned_rows) for track in source.tracks)
        context_count = sum(len(track.context_rows) for track in source.tracks)
        statuses = {
            track.key: (
                "annotated"
                if self._output_path(source, track).exists()
                else "unlabeled"
            )
            for track in ordered_tracks
        }
        return {
            "source_relative_path": source.source_id,
            "file_name": source.name,
            "source_label": source.source_label,
            "product": source.product,
            "height_axis_label": source.height_axis_label,
            "review_note": source.review_note,
            "priority_tracks": list(source.priority_tracks),
            "track_notes": source.track_notes,
            "beams": [track.key for track in ordered_tracks],
            "beam_count": len(source.tracks),
            "aoi_photon_count": assigned_count,
            "context_photon_count": context_count,
            "track_photon_counts": {
                track.key: len(track.assigned_rows) for track in ordered_tracks
            },
            "track_closest_distances_m": {
                track.key: track.closest_distance_m for track in ordered_tracks
            },
            "track_statuses": statuses,
            "annotated_track_count": sum(
                status == "annotated" for status in statuses.values()
            ),
        }

    def _labels_for_track(
        self,
        source: ReviewSource,
        track: ReviewTrack,
        photons: PhotonTable,
    ) -> tuple[list[dict[str, int | str]], str, Path | None]:
        path = self._output_path(source, track)
        if not path.exists():
            return (
                labels_from_atl24_classes(photons.source_row, photons.atl24_class_ph),
                ("atl24_original" if source.product == "atl24" else "raw_unclassified"),
                None,
            )
        frame = self._frames[source.source_id]
        expected_ids = self._photon_ids(frame, track.assigned_rows)
        try:
            class_manual = read_manual_classes(path, expected_ids)
        except (OSError, RuntimeError, ValueError) as exc:
            raise ValueError(f"Invalid classified GeoPackage: {path}") from exc
        labels = [
            {
                "source_row": source_row,
                "label": label_from_class_ph(class_ph),
                "label_source": "manual",
            }
            for source_row, class_ph in zip(track.assigned_rows, class_manual)
        ]
        return labels, "manual_output", path

    def _output_path(self, source: ReviewSource, track: ReviewTrack) -> Path:
        frame = self._frames[source.source_id]
        rows = frame.iloc[list(track.assigned_rows)]
        acquisition_date = (
            pd.to_datetime(rows["time_ns"], utc=True).min().strftime("%Y%m%d")
        )
        filename = (
            f"{acquisition_date}_rgt{track.rgt:04d}_"
            f"cycle{track.cycle:03d}_spot{track.spot}.gpkg"
        )
        return self.output_dir / source.source_id / filename

    def _classified_frame(
        self,
        source: ReviewSource,
        track: ReviewTrack,
        labels: list[dict[str, int | str]],
        *,
        time_labeled_utc: str,
    ) -> gpd.GeoDataFrame:
        frame = self._frames[source.source_id]
        rows = frame.iloc[list(track.assigned_rows)].copy()
        rows = rows.sort_values("_track_index")
        manual_by_row = {
            int(row["source_row"]): LABEL_TO_CLASS_PH[str(row["label"])]
            for row in labels
        }
        timestamps = pd.to_datetime(rows["time_ns"], utc=True)
        height_column = "ortho_h" if source.product == "atl24" else "_review_height"
        source_class_column = "class_ph" if source.product == "atl24" else None
        return build_classified_frame(
            rows,
            acquisition_dates=timestamps.dt.strftime("%Y%m%d").tolist(),
            track_indices=rows["_track_index"].astype(int).tolist(),
            rgt=track.rgt,
            cycle=track.cycle,
            spot=track.spot,
            class_manual=[manual_by_row[int(value)] for value in rows["_source_row"]],
            time_labeled_utc=time_labeled_utc,
            time_utc=[_timestamp_text(value) for value in timestamps],
            source_product=source.product,
            height_column=height_column,
            source_class_column=source_class_column,
        )

    def _photon_ids(
        self,
        frame: gpd.GeoDataFrame,
        source_rows: tuple[int, ...],
    ) -> list[str]:
        rows = frame.iloc[list(source_rows)]
        timestamps = pd.to_datetime(rows["time_ns"], utc=True)
        return [
            canonical_photon_id(
                timestamp.strftime("%Y%m%d"),
                int(rgt),
                int(cycle),
                int(spot),
                int(track_index),
            )
            for timestamp, rgt, cycle, spot, track_index in zip(
                timestamps,
                rows["rgt"],
                rows["cycle"],
                rows["spot"],
                rows["_track_index"],
            )
        ]

    def _source(self, source_id: str) -> ReviewSource:
        source = self._sources.get(source_id)
        if source is None:
            raise KeyError(f"Unknown review site: {source_id}")
        return source

    def _resolve_path(self, value: Any) -> Path:
        path = Path(str(value)).expanduser()
        if not path.is_absolute():
            path = self.config_path.parent / path
        return path.resolve()


def _track_key(rgt: int, cycle: int, spot: int) -> str:
    return f"rgt_{rgt:04d}_cycle_{cycle:03d}_spot_{spot}"


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")
    if not slug:
        raise ValueError(f"Could not derive a site id from name: {value!r}")
    return slug


def _optional_note(value: Any, field_name: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a string")
    note = value.strip()
    return note or None


def _track_key_list(value: Any) -> tuple[str, ...]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ValueError("priority_tracks must be a list of track-key strings")
    keys = tuple(item.strip() for item in value)
    if any(not item for item in keys) or len(keys) != len(set(keys)):
        raise ValueError("priority_tracks must contain unique, non-empty track keys")
    return keys


def _track_note_mapping(value: Any) -> dict[str, str]:
    if not isinstance(value, dict):
        raise ValueError("track_notes must be an object keyed by track key")
    notes: dict[str, str] = {}
    for key, note in value.items():
        if not isinstance(key, str) or not key.strip():
            raise ValueError("track_notes keys must be non-empty strings")
        parsed = _optional_note(note, f"track_notes[{key!r}]")
        if parsed is not None:
            notes[key.strip()] = parsed
    return notes


def _site_marker(value: Any) -> dict[str, float | str] | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ValueError("site_marker must be an object")
    try:
        longitude = float(value["longitude"])
        latitude = float(value["latitude"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(
            "site_marker requires numeric longitude and latitude"
        ) from exc
    if not np.isfinite(longitude) or not -180 <= longitude <= 180:
        raise ValueError("site_marker longitude must be between -180 and 180")
    if not np.isfinite(latitude) or not -90 <= latitude <= 90:
        raise ValueError("site_marker latitude must be between -90 and 90")
    label = str(value.get("label", "Site marker")).strip() or "Site marker"
    return {"label": label, "longitude": longitude, "latitude": latitude}


def _closest_distance_m(
    frame: gpd.GeoDataFrame,
    site_marker: dict[str, float | str] | None,
) -> float | None:
    if site_marker is None or frame.empty:
        return None
    longitude = pd.to_numeric(frame["_review_lon"], errors="coerce").to_numpy(
        dtype=float
    )
    latitude = pd.to_numeric(frame["_review_lat"], errors="coerce").to_numpy(
        dtype=float
    )
    valid = np.isfinite(longitude) & np.isfinite(latitude)
    if not np.any(valid):
        return None
    _, _, distance = WGS84_GEOD.inv(
        np.full(np.count_nonzero(valid), float(site_marker["longitude"])),
        np.full(np.count_nonzero(valid), float(site_marker["latitude"])),
        longitude[valid],
        latitude[valid],
    )
    return float(np.min(distance))


def _photon_table(frame: gpd.GeoDataFrame, source_rows: tuple[int, ...]) -> PhotonTable:
    rows = frame.iloc[list(source_rows)]
    source_row_values = [int(value) for value in rows["_source_row"]]
    if "index_ph" in rows:
        index_values = [
            _optional_int(value, fallback)
            for value, fallback in zip(rows["index_ph"], source_row_values)
        ]
    elif "ph_index" in rows:
        index_values = [
            _optional_int(value, fallback)
            for value, fallback in zip(rows["ph_index"], source_row_values)
        ]
    else:
        index_values = source_row_values.copy()
    return PhotonTable(
        source_row=source_row_values,
        index_ph=index_values,
        lat=[float(value) for value in rows["_review_lat"]],
        lon=[float(value) for value in rows["_review_lon"]],
        x_atc_m=[float(value) for value in rows["x_atc"]],
        ortho_h_m=[float(value) for value in rows["_review_height"]],
        surface_h_m=[_finite_float(value, 0.0) for value in rows["_review_surface_h"]],
        night_flag=[_optional_int(value, 0) for value in rows["_review_night"]],
        atl24_class_ph=[_nullable_int(value) for value in rows["_review_class_ph"]],
    )


def _finite_float(value: Any, fallback: float) -> float:
    number = float(value)
    return number if np.isfinite(number) else fallback


def _optional_int(value: Any, fallback: int) -> int:
    return fallback if pd.isna(value) else int(value)


def _nullable_int(value: Any) -> int | None:
    return None if pd.isna(value) else int(value)


def _timestamp_text(value: pd.Timestamp) -> str:
    return value.isoformat().replace("+00:00", "Z")


def _validate_annotation_rows(
    labels: list[dict[str, Any]], expected_rows: tuple[int, ...]
) -> list[dict[str, int | str]]:
    expected = set(expected_rows)
    if len(labels) != len(expected_rows):
        raise ValueError(
            f"Expected {len(expected_rows)} complete label rows; found {len(labels)}"
        )
    validated: list[dict[str, int | str]] = []
    seen: set[int] = set()
    for row in labels:
        source_row = int(row["source_row"])
        label = str(row["label"])
        label_source = str(row["label_source"])
        if source_row not in expected:
            raise ValueError(f"source_row is outside this AOI track: {source_row}")
        if source_row in seen:
            raise ValueError(f"Duplicate source_row: {source_row}")
        if label not in FINAL_LABELS:
            raise ValueError(f"Invalid label: {label}")
        if label_source not in LABEL_SOURCES:
            raise ValueError(f"Invalid label_source: {label_source}")
        seen.add(source_row)
        validated.append(
            {
                "source_row": source_row,
                "label": label,
                "label_source": label_source,
            }
        )
    if seen != expected:
        raise ValueError("Annotation rows do not match the AOI photon rows")
    return sorted(validated, key=lambda row: int(row["source_row"]))
