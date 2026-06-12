from __future__ import annotations

from pathlib import Path

from bathy_labeler.backend.features import build_feature_table
from bathy_labeler.backend.hdf5_store import Atl24Store
from bathy_labeler.backend.proposals import generate_seeded_proposal

from tests.backend.test_hdf5_store import write_atl24_like_file


def make_payload(tmp_path: Path):
    source_root = tmp_path / "sources"
    project_root = tmp_path / "project"
    write_atl24_like_file(source_root / "Guam" / "ATL24_sample.h5")
    store = Atl24Store.from_folder(source_root=source_root, project_root=project_root)
    return store.read_segment(store.segments[0].segment_id)


def test_feature_table_is_keyed_and_contains_reusable_v1_features(tmp_path: Path):
    payload = make_payload(tmp_path)

    table = build_feature_table(payload.assigned, payload.context, beam_strength=payload.segment.beam_strength)

    assert table.count == payload.assigned.count
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
    payload = make_payload(tmp_path)
    seeds = [
        {"source_row": payload.assigned.source_row[0], "label": "surface", "label_source": "manual"},
    ]

    proposal = generate_seeded_proposal(payload.assigned, payload.context, payload.segment.beam_strength, seeds)

    labels = {row["label"] for row in proposal.rows}
    assert labels <= {"surface", "noise"}
    assert proposal.rows[0] == {
        "source_row": payload.assigned.source_row[0],
        "label": "surface",
        "label_source": "manual",
    }
    assert proposal.rows[-1]["label"] == "noise"
    assert proposal.rows[-1]["label_source"] == "auto"


def test_seeded_proposal_keeps_seeded_photons_fixed_and_uses_seeded_classes(tmp_path: Path):
    payload = make_payload(tmp_path)
    seeds = [
        {"source_row": payload.assigned.source_row[0], "label": "surface", "label_source": "manual"},
        {"source_row": payload.assigned.source_row[-1], "label": "bathy", "label_source": "manual"},
    ]

    proposal = generate_seeded_proposal(payload.assigned, payload.context, payload.segment.beam_strength, seeds)

    assert proposal.rows[0]["label"] == "surface"
    assert proposal.rows[0]["label_source"] == "manual"
    assert proposal.rows[-1]["label"] == "bathy"
    assert proposal.rows[-1]["label_source"] == "manual"
    labels = {row["label"] for row in proposal.rows}
    assert labels <= {"surface", "bathy", "noise"}
    assert "land" not in labels
    assert "ambiguous" not in labels
    assert proposal.metadata["per_class_seed_counts"] == {"bathy": 1, "surface": 1}
    assert proposal.metadata["proposal_class_counts"]["surface"] >= 1
    assert proposal.metadata["proposal_class_counts"]["bathy"] >= 1
