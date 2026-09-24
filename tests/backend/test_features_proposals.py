from __future__ import annotations

from pathlib import Path

import h5py
import numpy as np

from bathy_labeler.backend.atl24_h5 import read_photon_rows
from bathy_labeler.backend.features import build_feature_table
from bathy_labeler.backend.models import PhotonTable
from bathy_labeler.backend.proposals import generate_seeded_proposal

from tests.backend.atl24_fixtures import write_atl24_like_file


def read_gt1l_photons(tmp_path: Path) -> PhotonTable:
    path = tmp_path / "ATL24_sample.h5"
    write_atl24_like_file(path)
    with h5py.File(path, "r") as h5:
        group = h5["gt1l"]
        return read_photon_rows(group, np.arange(group["x_atc"].shape[0]))


def test_feature_table_is_keyed_and_contains_reusable_v1_features(tmp_path: Path):
    photons = read_gt1l_photons(tmp_path)

    table = build_feature_table(photons, photons, beam_strength="weak")

    assert table.count == photons.count
    assert table.feature_config_hash
    first = table.rows[0]
    assert first["source_row"] == 0
    assert first["index_ph"] == 10_000
    assert first["night_flag"] == 1.0
    assert first["beam_strength"] == 0.0
    assert first["ortho_h_m"] == 1.5
    assert first["surface_h_m"] == 0.25
    assert first["dz_to_surface_m"] == 1.25
    for name in (
        "ellip_density_a50_max",
        "ellip_density_a100_mean",
        "ellip_density_a500_contrast",
        "hist_w50_n",
        "hist_w100_dz_peak1_m",
        "hist_w500_z_quantile",
    ):
        assert name in first


def test_seeded_proposal_does_not_invent_unseeded_semantic_classes(tmp_path: Path):
    photons = read_gt1l_photons(tmp_path)
    seeds = [
        {"source_row": photons.source_row[0], "label": "surface", "label_source": "manual"},
    ]

    proposal = generate_seeded_proposal(photons, photons, "weak", seeds)

    labels = {row["label"] for row in proposal.rows}
    assert labels <= {"surface", "no_label"}
    assert proposal.rows[0] == {
        "source_row": photons.source_row[0],
        "label": "surface",
        "label_source": "manual",
    }
    assert proposal.rows[-1]["label"] == "no_label"
    assert proposal.rows[-1]["label_source"] == "auto"


def test_seeded_proposal_keeps_seeded_photons_fixed_and_uses_seeded_classes(tmp_path: Path):
    photons = read_gt1l_photons(tmp_path)
    seeds = [
        {"source_row": photons.source_row[0], "label": "surface", "label_source": "manual"},
        {"source_row": photons.source_row[-1], "label": "bathy", "label_source": "manual"},
    ]

    proposal = generate_seeded_proposal(photons, photons, "weak", seeds)

    assert proposal.rows[0]["label"] == "surface"
    assert proposal.rows[0]["label_source"] == "manual"
    assert proposal.rows[-1]["label"] == "bathy"
    assert proposal.rows[-1]["label_source"] == "manual"
    labels = {row["label"] for row in proposal.rows}
    assert labels <= {"surface", "bathy", "no_label"}
    assert proposal.metadata["per_class_seed_counts"] == {"bathy": 1, "surface": 1}
    assert proposal.metadata["proposal_class_counts"]["surface"] >= 1
    assert proposal.metadata["proposal_class_counts"]["bathy"] >= 1
