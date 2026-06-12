from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Any

import numpy as np

from bathy_labeler.backend.features import build_feature_table
from bathy_labeler.backend.models import FINAL_LABELS, BeamStrength, PhotonTable

ALGORITHM_NAME = "seeded-centroid"
ALGORITHM_VERSION = "v1"
CENTROID_FEATURES = ["ortho_h_m", "dz_to_surface_m", "hist_w100_z_quantile", "hist_w500_z_quantile"]


@dataclass(frozen=True)
class ProposalResult:
    rows: list[dict[str, int | str]]
    metadata: dict[str, Any]


def generate_seeded_proposal(
    assigned: PhotonTable,
    context: PhotonTable,
    beam_strength: BeamStrength,
    seeds: list[dict[str, Any]],
) -> ProposalResult:
    seed_by_row = _seed_by_row(seeds)
    feature_table = build_feature_table(assigned, context, beam_strength)
    matrix = _scaled_matrix(feature_table.matrix(CENTROID_FEATURES))
    row_positions = {source_row: index for index, source_row in enumerate(assigned.source_row)}
    seeded_non_noise = sorted(
        {label for label in seed_by_row.values() if label != "noise"}
    )
    centroids = _centroids(matrix, row_positions, seed_by_row, seeded_non_noise)

    rows: list[dict[str, int | str]] = []
    for position, source_row in enumerate(assigned.source_row):
        if source_row in seed_by_row:
            rows.append({"source_row": int(source_row), "label": seed_by_row[source_row], "label_source": "manual"})
            continue
        label = "noise"
        if len(centroids) >= 2:
            label = _nearest_centroid_label(matrix[position], centroids)
        rows.append({"source_row": int(source_row), "label": label, "label_source": "auto"})

    proposal_counts = Counter(str(row["label"]) for row in rows)
    seed_counts = Counter(seed_by_row.values())
    metadata = {
        "algorithm_name": ALGORITHM_NAME,
        "algorithm_version": ALGORITHM_VERSION,
        "feature_config_hash": feature_table.feature_config_hash,
        "feature_names": CENTROID_FEATURES,
        "pca": None,
        "per_class_seed_counts": dict(sorted(seed_counts.items())),
        "proposal_class_counts": dict(sorted(proposal_counts.items())),
    }
    return ProposalResult(rows=rows, metadata=metadata)


def _seed_by_row(seeds: list[dict[str, Any]]) -> dict[int, str]:
    seed_by_row: dict[int, str] = {}
    for seed in seeds:
        label = str(seed["label"])
        if label not in FINAL_LABELS:
            continue
        seed_by_row[int(seed["source_row"])] = label
    return seed_by_row


def _scaled_matrix(matrix: np.ndarray) -> np.ndarray:
    if matrix.size == 0:
        return matrix
    finite = np.where(np.isfinite(matrix), matrix, np.nan)
    means = np.nanmean(finite, axis=0)
    means = np.where(np.isfinite(means), means, 0.0)
    filled = np.where(np.isfinite(matrix), matrix, means)
    std = np.nanstd(filled, axis=0)
    std = np.where(std > 0, std, 1.0)
    return (filled - means) / std


def _centroids(
    matrix: np.ndarray,
    row_positions: dict[int, int],
    seed_by_row: dict[int, str],
    seeded_labels: list[str],
) -> dict[str, np.ndarray]:
    centroids: dict[str, np.ndarray] = {}
    for label in seeded_labels:
        positions = [
            row_positions[source_row]
            for source_row, seed_label in seed_by_row.items()
            if seed_label == label and source_row in row_positions
        ]
        if positions:
            centroids[label] = np.mean(matrix[positions], axis=0)
    return centroids


def _nearest_centroid_label(vector: np.ndarray, centroids: dict[str, np.ndarray]) -> str:
    best_label = "noise"
    best_distance = float("inf")
    for label, centroid in sorted(centroids.items()):
        distance = float(np.linalg.norm(vector - centroid))
        if distance < best_distance:
            best_distance = distance
            best_label = label
    return best_label
