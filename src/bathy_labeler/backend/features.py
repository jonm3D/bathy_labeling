from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

import numpy as np

from bathy_labeler.backend.models import BeamStrength, PhotonTable

DENSITY_WINDOWS_M = (50, 100, 500)
HISTOGRAM_WINDOWS_M = (50, 100, 500)
FEATURE_CONFIG = {
    "version": "features-v1",
    "density_windows_m": DENSITY_WINDOWS_M,
    "histogram_windows_m": HISTOGRAM_WINDOWS_M,
    "histogram_bin_m": 1.0,
}


@dataclass(frozen=True)
class FeatureTable:
    rows: list[dict[str, float | int]]
    feature_names: list[str]
    feature_config_hash: str

    @property
    def count(self) -> int:
        return len(self.rows)

    def matrix(self, feature_names: list[str] | None = None) -> np.ndarray:
        names = self.feature_names if feature_names is None else feature_names
        values = [[float(row[name]) for name in names] for row in self.rows]
        return np.asarray(values, dtype=float)


def build_feature_table(assigned: PhotonTable, context: PhotonTable, beam_strength: BeamStrength) -> FeatureTable:
    rows: list[dict[str, float | int]] = []
    feature_names = _feature_names()
    context_x = np.asarray(context.x_atc_m, dtype=float)
    context_z = np.asarray(context.ortho_h_m, dtype=float)

    for index in range(assigned.count):
        x_i = float(assigned.x_atc_m[index])
        z_i = float(assigned.ortho_h_m[index])
        row: dict[str, float | int] = {
            "source_row": int(assigned.source_row[index]),
            "index_ph": int(assigned.index_ph[index]),
            "night_flag": float(assigned.night_flag[index]),
            "beam_strength": 1.0 if beam_strength == "strong" else 0.0,
            "ortho_h_m": z_i,
            "surface_h_m": float(assigned.surface_h_m[index]),
            "dz_to_surface_m": z_i - float(assigned.surface_h_m[index]),
        }
        row.update(_density_features(x_i, z_i, context_x, context_z))
        row.update(_histogram_features(x_i, z_i, context_x, context_z))
        rows.append(row)
    return FeatureTable(rows=rows, feature_names=feature_names, feature_config_hash=feature_config_hash())


def feature_config_hash() -> str:
    payload = json.dumps(FEATURE_CONFIG, sort_keys=True)
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()


def _feature_names() -> list[str]:
    names = ["night_flag", "beam_strength", "ortho_h_m", "surface_h_m", "dz_to_surface_m"]
    for window in DENSITY_WINDOWS_M:
        names.extend(
            [
                f"ellip_density_a{window}_max",
                f"ellip_density_a{window}_mean",
                f"ellip_density_a{window}_contrast",
                f"ellip_density_a{window}_best_minor_m",
                f"ellip_density_a{window}_best_slope",
            ]
        )
    for window in HISTOGRAM_WINDOWS_M:
        names.extend(
            [
                f"hist_w{window}_n",
                f"hist_w{window}_dz_peak1_m",
                f"hist_w{window}_dz_peak2_m",
                f"hist_w{window}_peak2_valid",
                f"hist_w{window}_peak1_frac",
                f"hist_w{window}_peak2_frac",
                f"hist_w{window}_peak_ratio",
                f"hist_w{window}_photon_bin_frac",
                f"hist_w{window}_z_quantile",
                f"hist_w{window}_mode_count",
            ]
        )
    return names


def _density_features(x_i: float, z_i: float, context_x: np.ndarray, context_z: np.ndarray) -> dict[str, float]:
    features: dict[str, float] = {}
    dx = context_x - x_i
    dz = context_z - z_i
    for window in DENSITY_WINDOWS_M:
        # Compact deterministic proxy for the full oriented ellipse bank: use a local vertical envelope
        # and report the same summary fields expected by the shared feature schema.
        mask = (np.abs(dx) <= window) & (np.abs(dz) <= 5.0)
        count = max(0, int(np.count_nonzero(mask)) - 1)
        area = max(1.0, float(2 * window * 10.0))
        density = count / area
        features[f"ellip_density_a{window}_max"] = density
        features[f"ellip_density_a{window}_mean"] = density
        features[f"ellip_density_a{window}_contrast"] = 1.0 if density > 0 else 0.0
        features[f"ellip_density_a{window}_best_minor_m"] = 5.0
        features[f"ellip_density_a{window}_best_slope"] = 0.0
    return features


def _histogram_features(x_i: float, z_i: float, context_x: np.ndarray, context_z: np.ndarray) -> dict[str, float]:
    features: dict[str, float] = {}
    for window in HISTOGRAM_WINDOWS_M:
        mask = np.abs(context_x - x_i) <= window / 2.0
        heights = context_z[mask]
        count = int(heights.size)
        if count == 0:
            features.update(_empty_histogram_features(window))
            continue
        bins = np.floor(heights).astype(int)
        unique_bins, bin_counts = np.unique(bins, return_counts=True)
        order = np.argsort(-bin_counts, kind="stable")
        peak1_bin = int(unique_bins[order[0]])
        peak1_count = int(bin_counts[order[0]])
        peak2_bin: int | None = None
        peak2_count = 0
        for position in order[1:]:
            candidate = int(unique_bins[position])
            if abs(candidate - peak1_bin) >= 2:
                peak2_bin = candidate
                peak2_count = int(bin_counts[position])
                break
        target_bin = int(np.floor(z_i))
        target_bin_count = int(bin_counts[unique_bins == target_bin][0]) if target_bin in set(unique_bins.tolist()) else 0
        mode_threshold = max(1.0, 0.05 * count)
        features.update(
            {
                f"hist_w{window}_n": float(count),
                f"hist_w{window}_dz_peak1_m": z_i - float(peak1_bin),
                f"hist_w{window}_dz_peak2_m": 0.0 if peak2_bin is None else z_i - float(peak2_bin),
                f"hist_w{window}_peak2_valid": 0.0 if peak2_bin is None else 1.0,
                f"hist_w{window}_peak1_frac": peak1_count / count,
                f"hist_w{window}_peak2_frac": peak2_count / count if peak2_bin is not None else 0.0,
                f"hist_w{window}_peak_ratio": peak2_count / max(peak1_count, 1),
                f"hist_w{window}_photon_bin_frac": target_bin_count / count,
                f"hist_w{window}_z_quantile": float(np.count_nonzero(heights <= z_i)) / count,
                f"hist_w{window}_mode_count": float(np.count_nonzero(bin_counts >= mode_threshold)),
            }
        )
    return features


def _empty_histogram_features(window: int) -> dict[str, float]:
    return {
        f"hist_w{window}_n": 0.0,
        f"hist_w{window}_dz_peak1_m": 0.0,
        f"hist_w{window}_dz_peak2_m": 0.0,
        f"hist_w{window}_peak2_valid": 0.0,
        f"hist_w{window}_peak1_frac": 0.0,
        f"hist_w{window}_peak2_frac": 0.0,
        f"hist_w{window}_peak_ratio": 0.0,
        f"hist_w{window}_photon_bin_frac": 0.0,
        f"hist_w{window}_z_quantile": 0.0,
        f"hist_w{window}_mode_count": 0.0,
    }
