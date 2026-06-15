from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from bathy_labeler.backend.app import create_reprocess_app
from bathy_labeler.backend.reprocess import ReprocessSession

from tests.backend.test_hdf5_store import write_atl24_like_file


def make_client(tmp_path: Path, **app_kwargs: object) -> tuple[TestClient, Path, Path]:
    input_dir = tmp_path / "inputs"
    output_dir = tmp_path / "outputs"
    write_atl24_like_file(input_dir / "ATL24_sample.h5")
    session = ReprocessSession()
    return TestClient(create_reprocess_app(session=session, **app_kwargs)), input_dir, output_dir


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


def test_reprocess_directory_picker_endpoint_uses_injected_native_picker(tmp_path: Path) -> None:
    calls: list[tuple[str, str | None]] = []

    def picker(title: str, initial_dir: str | None) -> str | None:
        calls.append((title, initial_dir))
        return str(tmp_path / "selected")

    client, input_dir, _output_dir = make_client(tmp_path, directory_picker=picker)

    response = client.post(
        "/reprocess/select-directory",
        json={"title": "Choose ATL24 folder", "initial_dir": str(input_dir)},
    )

    assert response.status_code == 200
    assert response.json() == {"path": str(tmp_path / "selected")}
    assert calls == [("Choose ATL24 folder", str(input_dir))]


def test_reprocess_directory_picker_endpoint_reports_cancelled_selection(tmp_path: Path) -> None:
    def picker(_title: str, _initial_dir: str | None) -> str | None:
        return None

    client, _input_dir, _output_dir = make_client(tmp_path, directory_picker=picker)

    response = client.post("/reprocess/select-directory", json={})

    assert response.status_code == 200
    assert response.json() == {"path": None}
