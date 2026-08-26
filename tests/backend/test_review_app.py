from __future__ import annotations

from fastapi.testclient import TestClient

from bathy_labeler.backend.app import create_review_app
from bathy_labeler.backend.review import SlideRuleReviewSession
from tests.backend.test_review import write_review_inputs


def test_review_app_exposes_sources_tracks_and_annotation_save(
    tmp_path,
) -> None:
    session = SlideRuleReviewSession(write_review_inputs(tmp_path))
    client = TestClient(create_review_app(session))

    manifest = client.get("/manifest")
    assert manifest.status_code == 200
    assert manifest.json()["mode"] == "review"

    sources = client.get("/review/sources")
    assert sources.status_code == 200
    source = sources.json()["sources"][0]
    track = client.get(
        "/review/track",
        params={"source": "test_site", "track": source["beams"][0]},
    )
    assert track.status_code == 200
    assert track.json()["beam"]["photon_count"] == 2

    labels = track.json()["labels"]
    labels[0]["label"] = "bathy"
    labels[0]["label_source"] = "manual"
    saved = client.put(
        "/review/track/labels",
        json={
            "source": "test_site",
            "track": source["beams"][0],
            "labels": labels,
        },
    )
    assert saved.status_code == 200
    assert saved.json()["status"] == "saved"
    assert saved.json()["source_status"]["annotated_track_count"] == 1

    assert client.post("/reprocess/save", json={}).status_code == 404
