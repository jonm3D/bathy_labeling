from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from bathy_labeler.backend.app import create_app
from bathy_labeler.backend.hdf5_store import Atl24Store
from bathy_labeler.backend.labels import LabelSidecarStore

from tests.backend.test_hdf5_store import write_atl24_like_file


def make_client(tmp_path: Path) -> tuple[TestClient, Atl24Store, LabelSidecarStore]:
    source_root = tmp_path / "sources"
    project_root = tmp_path / "project"
    write_atl24_like_file(source_root / "Guam" / "ATL24_sample.h5")
    store = Atl24Store.from_folder(source_root=source_root, project_root=project_root)
    label_store = LabelSidecarStore(project_root)
    return TestClient(create_app(store=store, label_store=label_store)), store, label_store


def test_health_manifest_and_segments(tmp_path: Path):
    client, store, _ = make_client(tmp_path)

    health = client.get("/health")
    assert health.status_code == 200
    assert health.json()["status"] == "ok"
    assert health.json()["segment_count"] == len(store.segments)

    manifest = client.get("/manifest")
    assert manifest.status_code == 200
    assert manifest.json()["segment_count"] == len(store.segments)

    segments = client.get("/segments")
    assert segments.status_code == 200
    payload = segments.json()
    assert payload["count"] == len(store.segments)
    assert payload["segments"][0]["status"] == "unlabeled"


def test_segment_payload_and_empty_labels(tmp_path: Path):
    client, store, _ = make_client(tmp_path)
    segment_id = store.segments[0].segment_id

    response = client.get(f"/segments/{segment_id}")
    assert response.status_code == 200
    payload = response.json()
    assert payload["segment"]["segment_id"] == segment_id
    assert payload["assigned"]["source_row"][0] == 0
    assert payload["context"]["source_row"][-1] == 109

    labels = client.get(f"/segments/{segment_id}/labels")
    assert labels.status_code == 200
    assert labels.json() == {"status": "unlabeled", "rows": [], "metadata": {}}


def test_proposal_and_save_labels(tmp_path: Path):
    client, store, _ = make_client(tmp_path)
    segment_id = store.segments[0].segment_id
    first_row = store.read_segment(segment_id).assigned.source_row[0]
    last_row = store.read_segment(segment_id).assigned.source_row[-1]

    proposal = client.post(
        f"/segments/{segment_id}/proposal",
        json={
            "seeds": [
                {"source_row": first_row, "label": "surface", "label_source": "manual"},
                {"source_row": last_row, "label": "bathy", "label_source": "manual"},
            ]
        },
    )
    assert proposal.status_code == 200
    proposal_payload = proposal.json()
    assert proposal_payload["rows"][0]["label"] == "surface"
    assert proposal_payload["rows"][-1]["label"] == "bathy"

    saved = client.put(f"/segments/{segment_id}/labels", json={"labels": proposal_payload["rows"]})
    assert saved.status_code == 200
    saved_payload = saved.json()
    assert saved_payload["status"] == "complete"
    assert saved_payload["metadata"]["segment_id"] == segment_id

    labels = client.get(f"/segments/{segment_id}/labels")
    assert labels.status_code == 200
    assert labels.json()["status"] == "complete"
    assert len(labels.json()["rows"]) == store.segments[0].photon_count


def test_unknown_segment_returns_404(tmp_path: Path):
    client, _, _ = make_client(tmp_path)

    response = client.get("/segments/not-a-segment")

    assert response.status_code == 404
