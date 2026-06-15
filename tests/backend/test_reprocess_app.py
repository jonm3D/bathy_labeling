from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from bathy_labeler.backend.app import create_reprocess_app
from bathy_labeler.backend.reprocess import ReprocessSession

from tests.backend.test_hdf5_store import write_atl24_like_file


def make_client(tmp_path: Path) -> tuple[TestClient, Path, Path]:
    input_dir = tmp_path / "inputs"
    output_dir = tmp_path / "outputs"
    write_atl24_like_file(input_dir / "ATL24_sample.h5")
    session = ReprocessSession()
    return TestClient(create_reprocess_app(session=session)), input_dir, output_dir


def test_reprocess_session_endpoints_configure_load_propose_reset_and_save(tmp_path: Path) -> None:
    client, input_dir, output_dir = make_client(tmp_path)

    configure = client.post(
        "/reprocess/session",
        json={"input_dir": str(input_dir), "output_dir": str(output_dir)},
    )
    assert configure.status_code == 200
    assert configure.json()["configured"]

    sources = client.get("/reprocess/sources")
    assert sources.status_code == 200
    source = sources.json()["sources"][0]
    assert source["source_relative_path"] == "ATL24_sample.h5"
    assert source["beams"] == ["gt1l", "gt1r"]

    beam = client.get("/reprocess/beam", params={"source": "ATL24_sample.h5", "beam": "gt1l"})
    assert beam.status_code == 200
    beam_payload = beam.json()
    assert beam_payload["beam"]["photon_count"] == 150
    assert beam_payload["labels"][0]["label"] == "surface"

    proposal = client.post(
        "/reprocess/proposal",
        json={
            "source": "ATL24_sample.h5",
            "beam": "gt1l",
            "seeds": [
                {"source_row": 0, "label": "surface", "label_source": "manual"},
                {"source_row": 149, "label": "bathy", "label_source": "manual"},
            ],
        },
    )
    assert proposal.status_code == 200
    assert proposal.json()["rows"][-1]["label_source"] == "manual"

    reset = client.post("/reprocess/reset", json={"source": "ATL24_sample.h5", "beam": "gt1l"})
    assert reset.status_code == 200
    assert reset.json()["rows"][149]["label"] == "noise"

    save = client.post(
        "/reprocess/save",
        json={
            "source": "ATL24_sample.h5",
            "beam_labels": {
                "gt1l": [
                    {"source_row": 0, "label": "bathy", "label_source": "manual"},
                    *beam_payload["labels"][1:],
                ]
            },
        },
    )
    assert save.status_code == 200
    assert Path(save.json()["output_path"]).name == "ATL24_sample_manual.h5"
